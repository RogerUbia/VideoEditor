import os
import json
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QSplitter, QStatusBar,
    QToolBar, QLabel, QPushButton, QFileDialog, QMessageBox,
    QInputDialog, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSettings, QSize
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent, QKeySequence

from .preview_panel import PreviewPanel
from .process_panel import ProcessPanel

# Optional panels — loaded when available (written later)
try:
    from .script_panel import ScriptPanel as _ScriptPanel
except ImportError:
    _ScriptPanel = None

try:
    from .timeline_panel import TimelinePanel as _TimelinePanel
except ImportError:
    _TimelinePanel = None

try:
    from .properties_panel import PropertiesPanel as _PropertiesPanel
except ImportError:
    _PropertiesPanel = None

_VIDEO_EXT = (".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v", ".flv")


class _Placeholder(QWidget):
    """Temporary panel shown until the real module is written."""
    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        lo = QVBoxLayout(self)
        lbl = QLabel(f"⬚  {name}")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #3A3A3A; font-size: 14px; font-weight: 600;")
        lo.addWidget(lbl)


class MainWindow(QMainWindow):
    project_loaded = pyqtSignal(dict)
    segment_selected = pyqtSignal(str)
    pipeline_started = pyqtSignal()
    pipeline_stopped = pyqtSignal()
    pipeline_finished = pyqtSignal(dict)

    def __init__(self, config: dict, api_key: str, base_dir: str = "", parent=None):
        super().__init__(parent)
        self.config = config
        self.api_key = api_key
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).parent.parent
        self.current_project: dict | None = None
        self.current_video_path: str | None = None
        self.pipeline_worker = None
        self.full_auto_mode = False

        self._build_ui()
        self._build_menu()
        self._build_toolbar()
        self._build_statusbar()
        self._wire_signals()
        self._restore_geometry()
        self.setAcceptDrops(True)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        self.setWindowTitle("VideoForge")
        self.setMinimumSize(1100, 650)
        self.resize(1600, 920)
        self._center()

        # Panels
        self.preview_panel = PreviewPanel(self)
        self.process_panel = ProcessPanel(self)

        if _ScriptPanel:
            self.script_panel = _ScriptPanel(
                self, api_key=self.api_key, config=self.config,
                base_dir=str(self.base_dir)
            )
        else:
            self.script_panel = _Placeholder("Script Panel", self)
        self.script_panel.setMinimumWidth(340)

        if _TimelinePanel:
            self.timeline_panel = _TimelinePanel(self)
        else:
            self.timeline_panel = _Placeholder("Timeline", self)
        self.timeline_panel.setFixedHeight(185)

        if _PropertiesPanel:
            self.properties_panel = _PropertiesPanel(
                self, config=self.config, api_key=self.api_key
            )
        else:
            self.properties_panel = _Placeholder("Properties", self)
        self.properties_panel.setMinimumWidth(240)

        # Layout
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Vertical outer splitter
        self.v_splitter = QSplitter(Qt.Orientation.Vertical)
        self.v_splitter.setHandleWidth(3)

        # Horizontal top splitter
        self.h_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.h_splitter.setHandleWidth(3)
        self.h_splitter.addWidget(self.script_panel)
        self.h_splitter.addWidget(self.preview_panel)
        self.h_splitter.addWidget(self.properties_panel)
        self.h_splitter.setStretchFactor(0, 3)
        self.h_splitter.setStretchFactor(1, 5)
        self.h_splitter.setStretchFactor(2, 2)

        # Bottom area
        bottom = QWidget()
        bottom_lo = QVBoxLayout(bottom)
        bottom_lo.setContentsMargins(0, 0, 0, 0)
        bottom_lo.setSpacing(0)
        bottom_lo.addWidget(self.timeline_panel)
        bottom_lo.addWidget(self.process_panel)
        self.process_panel.setMinimumHeight(90)
        self.process_panel.setMaximumHeight(230)

        self.v_splitter.addWidget(self.h_splitter)
        self.v_splitter.addWidget(bottom)
        self.v_splitter.setStretchFactor(0, 3)
        self.v_splitter.setStretchFactor(1, 1)

        root_layout.addWidget(self.v_splitter)

    def _build_menu(self):
        mb = self.menuBar()

        # ── File ──────────────────────────────────────────────────────────────
        fm = mb.addMenu("File")

        def act(title, shortcut, slot):
            a = QAction(title, self)
            if shortcut:
                a.setShortcut(shortcut)
            a.triggered.connect(slot)
            return a

        fm.addAction(act("New Project",   "Ctrl+N", self.new_project))
        fm.addAction(act("Open Project…", "Ctrl+O", self.open_project))
        fm.addAction(act("Save Project",  "Ctrl+S", self.save_project))
        fm.addSeparator()
        fm.addAction(act("Import Video…", "Ctrl+Shift+O", self.open_video))
        fm.addSeparator()
        fm.addAction(act("Quit", "Ctrl+Q", self.close))

        # ── Pipeline ──────────────────────────────────────────────────────────
        pm = mb.addMenu("Pipeline")
        pm.addAction(act("Run Full Pipeline",   "F5", self.run_full_pipeline))
        pm.addAction(act("Stop Pipeline",        "F6", self.stop_pipeline))
        pm.addSeparator()
        pm.addAction(act("Remove Silences…",    "",   self._run_silence_only))
        pm.addAction(act("Transcribe Audio…",   "",   self._run_transcribe_only))

        # ── Export ────────────────────────────────────────────────────────────
        em = mb.addMenu("Export")
        em.addAction(act("Export for YouTube…",   "", lambda: self._export("youtube")))
        em.addAction(act("Export for Instagram…", "", lambda: self._export("instagram")))

        # ── Help ──────────────────────────────────────────────────────────────
        hm = mb.addMenu("Help")
        hm.addAction(act("About VideoForge", "", self._show_about))

    def _build_toolbar(self):
        tb: QToolBar = self.addToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QSize(14, 14))
        tb.setObjectName("main_toolbar")

        def btn(label, slot, role=None, width=None):
            b = QPushButton(label)
            if role:
                b.setProperty("role", role)
            if width:
                b.setFixedWidth(width)
            b.clicked.connect(slot)
            return b

        tb.addWidget(btn("⊕  Import Video", self.open_video, "ghost", 120))
        tb.addSeparator()

        self.run_btn = btn("▶  Run Pipeline", self.run_full_pipeline, "primary", 130)
        tb.addWidget(self.run_btn)

        self.stop_btn = btn("⏹  Stop", self.stop_pipeline, "danger", 80)
        self.stop_btn.setEnabled(False)
        tb.addWidget(self.stop_btn)

        self.resume_btn = btn("▶▶  Resume", self._resume_pipeline, "success", 110)
        self.resume_btn.setVisible(False)
        self.resume_btn.setToolTip(
            "El pipeline está pausado en el Paso 5 (Validación).\n"
            "Revisa el guion en la tabla izquierda y pulsa Resume para continuar."
        )
        tb.addWidget(self.resume_btn)

        tb.addSeparator()

        mode_lbl = QLabel("Mode: ")
        mode_lbl.setStyleSheet("background:transparent; color:#888; padding:0 4px;")
        tb.addWidget(mode_lbl)

        self.auto_btn = QPushButton("Manual")
        self.auto_btn.setCheckable(True)
        self.auto_btn.setChecked(False)
        self.auto_btn.setFixedWidth(90)
        self.auto_btn.toggled.connect(self._on_mode_toggled)
        tb.addWidget(self.auto_btn)

        tb.addSeparator()
        tb.addWidget(btn("↑ YouTube",   lambda: self._export("youtube"),   width=100))
        tb.addWidget(btn("↑ Instagram", lambda: self._export("instagram"), width=110))

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        spacer.setStyleSheet("background:transparent;")
        tb.addWidget(spacer)

        self.project_lbl = QLabel("No project")
        self.project_lbl.setStyleSheet(
            "color:#555; font-size:12px; padding:0 10px; background:transparent;"
        )
        tb.addWidget(self.project_lbl)

    def _build_statusbar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_lbl = QLabel("Ready")
        sb.addWidget(self._status_lbl)
        self._video_info_lbl = QLabel("")
        self._video_info_lbl.setStyleSheet("color:#666; font-size:11px;")
        sb.addPermanentWidget(self._video_info_lbl)

    def _wire_signals(self):
        self.pipeline_started.connect(lambda: self.process_panel.set_pipeline_running(True))
        self.pipeline_stopped.connect(lambda: self.process_panel.set_pipeline_running(False))
        self.pipeline_finished.connect(lambda _: self.process_panel.set_pipeline_running(False))
        self.stop_btn.clicked.connect(self.stop_pipeline)
        # Forward segment selection to properties if available
        if _PropertiesPanel and hasattr(self.properties_panel, "load_segment"):
            self.segment_selected.connect(self.properties_panel.load_segment)

    # ── Geometry ──────────────────────────────────────────────────────────────

    def _center(self):
        geo = self.screen().availableGeometry()
        x = (geo.width() - self.width()) // 2
        y = (geo.height() - self.height()) // 2
        self.move(max(0, x), max(0, y))

    def _restore_geometry(self):
        s = QSettings("VideoForge", "VideoForge")
        if s.contains("geometry"):
            self.restoreGeometry(s.value("geometry"))
        if s.contains("v_splitter"):
            self.v_splitter.restoreState(s.value("v_splitter"))
        if s.contains("h_splitter"):
            self.h_splitter.restoreState(s.value("h_splitter"))

    def closeEvent(self, event):
        s = QSettings("VideoForge", "VideoForge")
        s.setValue("geometry",  self.saveGeometry())
        s.setValue("v_splitter", self.v_splitter.saveState())
        s.setValue("h_splitter", self.h_splitter.saveState())
        if self.pipeline_worker and self.pipeline_worker.isRunning():
            self.stop_pipeline()
            self.pipeline_worker.wait(3000)
        if hasattr(self.preview_panel, "player"):
            self.preview_panel.player.stop()
            self.preview_panel.player.wait(2000)
        super().closeEvent(event)

    # ── Drag & Drop ───────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls()]
            if any(p.lower().endswith(_VIDEO_EXT) for p in paths):
                event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(_VIDEO_EXT):
                self._load_video(path)
                return

    # ── Project management ────────────────────────────────────────────────────

    def new_project(self):
        name, ok = QInputDialog.getText(self, "New Project", "Project name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        self.current_project = {
            "project_name": name,
            "segments": [],
            "global_settings": {"target_platform": "youtube"},
            "pipeline_state": {},
        }
        self.project_lbl.setText(name)
        self.project_loaded.emit(self.current_project)
        self.process_panel.append_log("SUCCESS", f"Project created: {name}")

    def open_project(self):
        projects_dir = str(self.base_dir / self.config.get("projects_dir", "data/projects"))
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", projects_dir,
            "VideoForge Projects (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                self.current_project = json.load(f)
            name = self.current_project.get("project_name", "Unknown")
            self.project_lbl.setText(name)
            self.project_loaded.emit(self.current_project)
            if _ScriptPanel and hasattr(self.script_panel, "load_script"):
                self.script_panel.load_script(self.current_project)
            self.process_panel.append_log("SUCCESS", f"Project loaded: {name}")
        except Exception as exc:
            QMessageBox.critical(self, "Error loading project", str(exc))

    def save_project(self):
        if not self.current_project:
            QMessageBox.information(self, "No Project", "No project open.")
            return
        projects_dir = self.base_dir / self.config.get("projects_dir", "data/projects")
        projects_dir.mkdir(parents=True, exist_ok=True)
        if _ScriptPanel and hasattr(self.script_panel, "get_script"):
            self.current_project.update(self.script_panel.get_script())
        name = self.current_project.get("project_name", "project")
        out = projects_dir / f"{name}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(self.current_project, f, ensure_ascii=False, indent=2)
        self._status_lbl.setText(f"Saved: {out.name}")
        self.process_panel.append_log("SUCCESS", f"Saved: {out}")

    def open_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Video", "",
            "Video Files (*.mp4 *.avi *.mov *.mkv *.webm *.m4v *.flv);;All Files (*)"
        )
        if path:
            self._load_video(path)

    def _load_video(self, path: str):
        self.current_video_path = path
        self.preview_panel.load_video(path)
        size_mb = os.path.getsize(path) / 1024 / 1024
        name = os.path.basename(path)
        self._video_info_lbl.setText(f"{name}  ({size_mb:.1f} MB)")
        self._status_lbl.setText(f"Loaded: {name}")
        self.process_panel.append_log("INFO", f"Video imported: {path}")

    # ── Pipeline ──────────────────────────────────────────────────────────────

    def run_full_pipeline(self):
        if not self.current_video_path:
            QMessageBox.warning(self, "No Video", "Import a video file first.")
            return
        if not self.current_project:
            QMessageBox.warning(self, "No Project", "Create or open a project first.")
            return
        try:
            from core.pipeline import PipelineWorker
        except ImportError:
            QMessageBox.information(
                self, "Pipeline not ready",
                "The processing pipeline will be available after Phase 4 implementation."
            )
            return

        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        project = dict(self.current_project)
        if _ScriptPanel and hasattr(self.script_panel, "get_script"):
            project.update(self.script_panel.get_script())
        project["video_path"] = self.current_video_path
        project["base_dir"] = str(self.base_dir)

        mode = "full_auto" if self.full_auto_mode else "manual"
        self.pipeline_worker = PipelineWorker(
            project=project, config=self.config,
            api_key=self.api_key, mode=mode,
        )
        self.pipeline_worker.step_started.connect(self.process_panel.set_step)
        self.pipeline_worker.step_failed.connect(
            lambda _, msg: self.process_panel.append_log("ERROR", msg)
        )
        self.pipeline_worker.progress.connect(self.process_panel.set_progress)
        self.pipeline_worker.log_message.connect(self.process_panel.append_log)
        self.pipeline_worker.finished_all.connect(self._on_pipeline_done)
        self.pipeline_worker.awaiting_approval.connect(self._on_awaiting_approval)
        self.pipeline_worker.start()
        self.pipeline_started.emit()
        self.process_panel.append_log("STEP", f"Pipeline started [{mode}]")

    def _on_awaiting_approval(self):
        self.resume_btn.setVisible(True)
        self.resume_btn.setStyleSheet("")   # force style refresh
        self.process_panel.append_log(
            "WARNING",
            "⏸ Pipeline pausado — revisa el guion en la tabla izquierda "
            "y pulsa  ▶▶ Resume  en la barra de herramientas para continuar."
        )

    def _resume_pipeline(self):
        if self.pipeline_worker and self.pipeline_worker.isRunning():
            self.resume_btn.setVisible(False)
            self.pipeline_worker.resume()
            self.process_panel.append_log("INFO", "▶ Pipeline reanudado")

    def stop_pipeline(self):
        if self.pipeline_worker and self.pipeline_worker.isRunning():
            self.pipeline_worker.cancel()
            self.process_panel.append_log("WARNING", "Stop requested…")
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.resume_btn.setVisible(False)
        self.pipeline_stopped.emit()

    def _on_pipeline_done(self, outputs: dict):
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.pipeline_finished.emit(outputs)
        self.process_panel.append_log("SUCCESS", "Pipeline completed!")
        if outputs.get("output_video"):
            self._load_video(outputs["output_video"])

    def _on_mode_toggled(self, checked: bool):
        self.full_auto_mode = checked
        self.auto_btn.setText("Full Auto" if checked else "Manual")
        self.process_panel.append_log(
            "INFO", f"Mode → {'Full Auto' if checked else 'Manual'}"
        )

    def _run_silence_only(self):
        if not self.current_video_path:
            QMessageBox.warning(self, "No Video", "Import a video first.")
            return
        self.process_panel.append_log("INFO", "Standalone silence removal — coming in Phase 4")

    def _run_transcribe_only(self):
        if not self.current_video_path:
            QMessageBox.warning(self, "No Video", "Import a video first.")
            return
        self.process_panel.append_log("INFO", "Standalone transcription — coming in Phase 4")

    def _export(self, platform: str):
        output_dir = QFileDialog.getExistingDirectory(
            self, f"Export for {platform.title()}", ""
        )
        if output_dir:
            self.process_panel.append_log(
                "INFO", f"Export [{platform}] → {output_dir} (requires full pipeline)"
            )

    def _show_about(self):
        QMessageBox.about(
            self, "About VideoForge",
            "<h2>VideoForge 1.0</h2>"
            "<p>Professional AI-powered video editor.</p>"
            "<p><b>GUI:</b> PyQt6 · Dark theme<br>"
            "<b>Video:</b> FFmpeg · pydub<br>"
            "<b>AI:</b> Gemini 2.0 Flash · 8 specialized agents</p>",
        )

    def set_status(self, msg: str):
        self._status_lbl.setText(msg)
