import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QTabWidget,
    QLabel, QPushButton, QLineEdit, QTextEdit, QComboBox, QCheckBox,
    QSlider, QSpinBox, QDoubleSpinBox, QGroupBox, QScrollArea,
    QColorDialog, QFileDialog, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor


class PropertiesPanel(QWidget):
    segment_changed = pyqtSignal(dict)
    config_changed = pyqtSignal(dict)

    def __init__(self, parent=None, config: dict = None, api_key: str = ""):
        super().__init__(parent)
        self.config = config or {}
        self._current_segment = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(36)
        header.setStyleSheet("background-color: #141414; border-bottom: 1px solid #2D2D2D;")
        h_lo = QHBoxLayout(header)
        h_lo.setContentsMargins(10, 0, 10, 0)
        title = QLabel("PROPERTIES")
        title.setStyleSheet("color: #888888; font-size: 11px; font-weight: 700; letter-spacing: 1px; background: transparent;")
        h_lo.addWidget(title)
        layout.addWidget(header)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._make_segment_tab(), "Segment")
        self.tabs.addTab(self._make_video_tab(), "Video")
        self.tabs.addTab(self._make_audio_tab(), "Audio")
        self.tabs.addTab(self._make_export_tab(), "Export")
        self.tabs.addTab(self._make_api_tab(), "API")
        layout.addWidget(self.tabs)

    # ── Segment Tab ────────────────────────────────────────────────────────────

    def _make_segment_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        # Timing group
        timing_box = QGroupBox("Timing")
        timing_form = QFormLayout(timing_box)
        self.seg_start = QLineEdit("00:00:00.000")
        self.seg_end = QLineEdit("00:00:05.000")
        timing_form.addRow("Start:", self.seg_start)
        timing_form.addRow("End:", self.seg_end)
        layout.addWidget(timing_box)

        # Content group
        content_box = QGroupBox("Content")
        content_lo = QVBoxLayout(content_box)
        content_lo.addWidget(QLabel("Script content:"))
        self.seg_content = QTextEdit()
        self.seg_content.setFixedHeight(80)
        content_lo.addWidget(self.seg_content)
        content_lo.addWidget(QLabel("Editor notes:"))
        self.seg_notes = QTextEdit()
        self.seg_notes.setFixedHeight(50)
        content_lo.addWidget(self.seg_notes)
        layout.addWidget(content_box)

        # Video Effect group
        effect_box = QGroupBox("Video Effect")
        effect_form = QFormLayout(effect_box)
        self.seg_effect = QComboBox()
        self.seg_effect.addItems(["none", "zoom_in", "zoom_out", "shake", "blur", "vignette"])
        effect_form.addRow("Effect:", self.seg_effect)
        self.seg_intensity = QDoubleSpinBox()
        self.seg_intensity.setRange(0.1, 3.0)
        self.seg_intensity.setSingleStep(0.1)
        self.seg_intensity.setValue(1.0)
        effect_form.addRow("Intensity:", self.seg_intensity)
        layout.addWidget(effect_box)

        # Zoom group
        zoom_box = QGroupBox("Zoom")
        zoom_form = QFormLayout(zoom_box)
        self.seg_zoom_en = QCheckBox("Enable zoom")
        zoom_form.addRow(self.seg_zoom_en)
        self.seg_zoom_factor = QDoubleSpinBox()
        self.seg_zoom_factor.setRange(1.0, 2.0)
        self.seg_zoom_factor.setSingleStep(0.05)
        self.seg_zoom_factor.setValue(1.3)
        zoom_form.addRow("Factor:", self.seg_zoom_factor)
        layout.addWidget(zoom_box)

        # Transition group
        trans_box = QGroupBox("Transitions")
        trans_form = QFormLayout(trans_box)
        self.seg_trans_in = QComboBox()
        self.seg_trans_in.addItems(["none", "fade", "dissolve", "slide_up", "wipe_left", "wipe_right"])
        trans_form.addRow("Transition in:", self.seg_trans_in)
        self.seg_trans_out = QComboBox()
        self.seg_trans_out.addItems(["none", "fade", "dissolve"])
        trans_form.addRow("Transition out:", self.seg_trans_out)
        self.seg_trans_dur = QDoubleSpinBox()
        self.seg_trans_dur.setRange(0.1, 2.0)
        self.seg_trans_dur.setSingleStep(0.1)
        self.seg_trans_dur.setValue(0.5)
        trans_form.addRow("Duration (s):", self.seg_trans_dur)
        layout.addWidget(trans_box)

        # PiP group
        pip_box = QGroupBox("Picture-in-Picture (Bubble)")
        pip_lo = QFormLayout(pip_box)
        self.seg_pip_en = QCheckBox("Enable PiP")
        pip_lo.addRow(self.seg_pip_en)
        self.seg_pip_src = QLineEdit()
        self.seg_pip_src.setPlaceholderText("Video file path...")
        pip_browse = QPushButton("Browse…")
        pip_browse.clicked.connect(self._browse_pip)
        pip_src_row = QHBoxLayout()
        pip_src_row.addWidget(self.seg_pip_src)
        pip_src_row.addWidget(pip_browse)
        pip_src_widget = QWidget()
        pip_src_widget.setLayout(pip_src_row)
        pip_lo.addRow("Source:", pip_src_widget)
        self.seg_pip_pos = QComboBox()
        self.seg_pip_pos.addItems(["bottom_right", "bottom_left", "top_right", "top_left"])
        pip_lo.addRow("Position:", self.seg_pip_pos)
        self.seg_pip_size = QDoubleSpinBox()
        self.seg_pip_size.setRange(0.1, 0.5)
        self.seg_pip_size.setSingleStep(0.05)
        self.seg_pip_size.setValue(0.25)
        pip_lo.addRow("Size (%):", self.seg_pip_size)
        layout.addWidget(pip_box)

        # Text overlay group
        text_box = QGroupBox("Text Overlay")
        text_lo = QFormLayout(text_box)
        self.seg_text_en = QCheckBox("Enable text overlay")
        text_lo.addRow(self.seg_text_en)
        self.seg_text_content = QLineEdit()
        self.seg_text_content.setPlaceholderText("Overlay text...")
        text_lo.addRow("Text:", self.seg_text_content)
        self.seg_text_size = QSpinBox()
        self.seg_text_size.setRange(10, 120)
        self.seg_text_size.setValue(36)
        text_lo.addRow("Font size:", self.seg_text_size)
        self.seg_text_pos = QComboBox()
        self.seg_text_pos.addItems(["bottom_center", "top_center", "center"])
        text_lo.addRow("Position:", self.seg_text_pos)
        self.seg_text_anim = QComboBox()
        self.seg_text_anim.addItems(["none", "fade_in", "typewriter", "slide_up"])
        text_lo.addRow("Animation:", self.seg_text_anim)
        layout.addWidget(text_box)

        # Music group
        music_box = QGroupBox("Music / Sound")
        music_lo = QFormLayout(music_box)
        self.seg_music_en = QCheckBox("Enable music")
        music_lo.addRow(self.seg_music_en)
        self.seg_music_src = QLineEdit()
        self.seg_music_src.setPlaceholderText("Audio file path...")
        music_browse = QPushButton("Browse…")
        music_browse.clicked.connect(self._browse_music)
        music_src_row = QHBoxLayout()
        music_src_row.addWidget(self.seg_music_src)
        music_src_row.addWidget(music_browse)
        music_src_widget = QWidget()
        music_src_widget.setLayout(music_src_row)
        music_lo.addRow("Source:", music_src_widget)
        self.seg_music_vol_lbl = QLabel("-12 dB")
        self.seg_music_vol = QSlider(Qt.Orientation.Horizontal)
        self.seg_music_vol.setRange(-40, 0)
        self.seg_music_vol.setValue(-12)
        self.seg_music_vol.valueChanged.connect(
            lambda v: self.seg_music_vol_lbl.setText(f"{v} dB")
        )
        vol_row = QHBoxLayout()
        vol_row.addWidget(self.seg_music_vol)
        vol_row.addWidget(self.seg_music_vol_lbl)
        vol_widget = QWidget()
        vol_widget.setLayout(vol_row)
        music_lo.addRow("Volume:", vol_widget)
        layout.addWidget(music_box)

        # Apply button
        apply_btn = QPushButton("Apply to Segment")
        apply_btn.setProperty("role", "primary")
        apply_btn.clicked.connect(self._apply_segment)
        layout.addWidget(apply_btn)
        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    # ── Video Tab ─────────────────────────────────────────────────────────────

    def _make_video_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        form = QFormLayout()
        self.vid_resolution = QComboBox()
        self.vid_resolution.addItems(["1920x1080", "1280x720", "1080x1920", "1080x1080"])
        form.addRow("Resolution:", self.vid_resolution)
        self.vid_fps = QComboBox()
        self.vid_fps.addItems(["24", "25", "30", "50", "60"])
        self.vid_fps.setCurrentText("30")
        form.addRow("FPS:", self.vid_fps)
        self.vid_crf_lbl = QLabel("18")
        self.vid_crf = QSlider(Qt.Orientation.Horizontal)
        self.vid_crf.setRange(15, 35)
        self.vid_crf.setValue(18)
        self.vid_crf.valueChanged.connect(lambda v: self.vid_crf_lbl.setText(str(v)))
        crf_row = QHBoxLayout()
        crf_row.addWidget(self.vid_crf)
        crf_row.addWidget(self.vid_crf_lbl)
        crf_w = QWidget(); crf_w.setLayout(crf_row)
        form.addRow("Quality (CRF):", crf_w)
        self.vid_preset = QComboBox()
        self.vid_preset.addItems(["ultrafast", "fast", "medium", "slow"])
        self.vid_preset.setCurrentText("fast")
        form.addRow("Encode preset:", self.vid_preset)
        layout.addLayout(form)
        layout.addStretch()
        return w

    # ── Audio Tab ─────────────────────────────────────────────────────────────

    def _make_audio_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)

        silence_box = QGroupBox("Silence Detection")
        silence_form = QFormLayout(silence_box)

        self.sil_thresh_lbl = QLabel("-40 dB")
        self.sil_thresh = QSlider(Qt.Orientation.Horizontal)
        self.sil_thresh.setRange(-70, -20)
        self.sil_thresh.setValue(-40)
        self.sil_thresh.valueChanged.connect(
            lambda v: self.sil_thresh_lbl.setText(f"{v} dB")
        )
        th_row = QHBoxLayout()
        th_row.addWidget(self.sil_thresh)
        th_row.addWidget(self.sil_thresh_lbl)
        th_w = QWidget(); th_w.setLayout(th_row)
        silence_form.addRow("Threshold:", th_w)

        self.sil_dur_lbl = QLabel("500 ms")
        self.sil_dur = QSlider(Qt.Orientation.Horizontal)
        self.sil_dur.setRange(100, 2000)
        self.sil_dur.setValue(500)
        self.sil_dur.valueChanged.connect(
            lambda v: self.sil_dur_lbl.setText(f"{v} ms")
        )
        dur_row = QHBoxLayout()
        dur_row.addWidget(self.sil_dur)
        dur_row.addWidget(self.sil_dur_lbl)
        dur_w = QWidget(); dur_w.setLayout(dur_row)
        silence_form.addRow("Min duration:", dur_w)

        self.sil_margin_lbl = QLabel("100 ms")
        self.sil_margin = QSlider(Qt.Orientation.Horizontal)
        self.sil_margin.setRange(0, 500)
        self.sil_margin.setValue(100)
        self.sil_margin.valueChanged.connect(
            lambda v: self.sil_margin_lbl.setText(f"{v} ms")
        )
        mg_row = QHBoxLayout()
        mg_row.addWidget(self.sil_margin)
        mg_row.addWidget(self.sil_margin_lbl)
        mg_w = QWidget(); mg_w.setLayout(mg_row)
        silence_form.addRow("Margin:", mg_w)

        layout.addWidget(silence_box)
        layout.addStretch()
        return w

    # ── Export Tab ────────────────────────────────────────────────────────────

    def _make_export_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        form = QFormLayout()

        self.exp_platform = QComboBox()
        self.exp_platform.addItems(["YouTube", "Instagram"])
        form.addRow("Platform:", self.exp_platform)

        self.exp_burn_subs = QCheckBox("Burn subtitles into video")
        form.addRow(self.exp_burn_subs)

        self.exp_sub_lang = QComboBox()
        self.exp_sub_lang.addItems(["Catalan (CA)", "Spanish (ES)", "English (EN)"])
        self.exp_sub_lang.setCurrentText("English (EN)")
        form.addRow("Subtitle language to burn:", self.exp_sub_lang)

        sub_box = QGroupBox("Subtitle Style")
        sub_form = QFormLayout(sub_box)
        self.sub_font = QComboBox()
        self.sub_font.addItems(["Arial", "Helvetica", "Verdana", "Impact", "Georgia"])
        sub_form.addRow("Font:", self.sub_font)
        self.sub_size = QSpinBox()
        self.sub_size.setRange(12, 72)
        self.sub_size.setValue(28)
        sub_form.addRow("Size:", self.sub_size)

        layout.addLayout(form)
        layout.addWidget(sub_box)
        layout.addStretch()
        return w

    # ── API Tab ───────────────────────────────────────────────────────────────

    def _make_api_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        form = QFormLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Gemini API Key from aistudio.google.com")
        form.addRow("Gemini API Key:", self.api_key_input)

        self.api_model_main = QComboBox()
        self.api_model_main.addItems(["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"])
        form.addRow("Main model:", self.api_model_main)

        self.api_model_light = QComboBox()
        self.api_model_light.addItems(["gemini-1.5-flash-8b", "gemini-1.5-flash"])
        form.addRow("Light model:", self.api_model_light)

        layout.addLayout(form)

        save_btn = QPushButton("Save API Settings")
        save_btn.setProperty("role", "primary")
        save_btn.clicked.connect(self._save_api)
        layout.addWidget(save_btn)
        layout.addStretch()
        return w

    # ── Actions ───────────────────────────────────────────────────────────────

    def _browse_pip(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "PiP Video Source", "",
            "Video Files (*.mp4 *.avi *.mov *.mkv);;All Files (*)"
        )
        if path:
            self.seg_pip_src.setText(path)

    def _browse_music(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Music / Audio Source", "",
            "Audio Files (*.mp3 *.wav *.aac *.ogg *.m4a);;All Files (*)"
        )
        if path:
            self.seg_music_src.setText(path)

    def _apply_segment(self):
        if self._current_segment is None:
            return
        self._current_segment.update({
            "time_start": self.seg_start.text(),
            "time_end": self.seg_end.text(),
            "content": self.seg_content.toPlainText(),
            "notes": self.seg_notes.toPlainText(),
            "video_effect": {
                "type": self.seg_effect.currentText(),
                "intensity": self.seg_intensity.value(),
            },
            "zoom": {
                "enabled": self.seg_zoom_en.isChecked(),
                "factor": self.seg_zoom_factor.value(),
            },
            "transition_in": {
                "type": self.seg_trans_in.currentText(),
                "duration_s": self.seg_trans_dur.value(),
            },
            "transition_out": {
                "type": self.seg_trans_out.currentText(),
                "duration_s": self.seg_trans_dur.value(),
            },
            "pip": {
                "enabled": self.seg_pip_en.isChecked(),
                "source": self.seg_pip_src.text(),
                "position": self.seg_pip_pos.currentText(),
                "size_pct": self.seg_pip_size.value(),
            },
            "text_overlay": {
                "enabled": self.seg_text_en.isChecked(),
                "text": self.seg_text_content.text(),
                "font_size_pt": self.seg_text_size.value(),
                "position": self.seg_text_pos.currentText(),
                "animation": self.seg_text_anim.currentText(),
            },
            "music": {
                "enabled": self.seg_music_en.isChecked(),
                "file_path": self.seg_music_src.text(),
                "volume_db": self.seg_music_vol.value(),
            },
        })
        self.segment_changed.emit(self._current_segment)

    def _save_api(self):
        import os
        from pathlib import Path
        key = self.api_key_input.text().strip()
        if key:
            os.environ["GEMINI_API_KEY"] = key
            env_path = Path(__file__).parent.parent / ".env"
            lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
            new_lines = [f"GEMINI_API_KEY={key}" if l.startswith("GEMINI_API_KEY=") else l for l in lines]
            if not any(l.startswith("GEMINI_API_KEY=") for l in new_lines):
                new_lines.append(f"GEMINI_API_KEY={key}")
            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        self.config_changed.emit({"gemini_api_key": key})

    @pyqtSlot(str)
    def load_segment(self, segment_id: str):
        pass  # will be connected to script panel

    def load_segment_data(self, segment: dict):
        self._current_segment = segment
        self.seg_start.setText(segment.get("time_start", "00:00:00.000"))
        self.seg_end.setText(segment.get("time_end", "00:00:05.000"))
        self.seg_content.setPlainText(segment.get("content", ""))
        self.seg_notes.setPlainText(segment.get("notes", ""))
        ve = segment.get("video_effect", {})
        idx = self.seg_effect.findText(ve.get("type", "none"))
        if idx >= 0:
            self.seg_effect.setCurrentIndex(idx)
        self.seg_intensity.setValue(ve.get("intensity", 1.0))
        zoom = segment.get("zoom", {})
        self.seg_zoom_en.setChecked(zoom.get("enabled", False))
        self.seg_zoom_factor.setValue(zoom.get("factor", 1.3))
        ti = segment.get("transition_in", {})
        idx = self.seg_trans_in.findText(ti.get("type", "none"))
        if idx >= 0:
            self.seg_trans_in.setCurrentIndex(idx)
        pip = segment.get("pip", {})
        self.seg_pip_en.setChecked(pip.get("enabled", False))
        self.seg_pip_src.setText(pip.get("source", ""))
        text = segment.get("text_overlay", {})
        self.seg_text_en.setChecked(text.get("enabled", False))
        self.seg_text_content.setText(text.get("text", ""))
        music = segment.get("music", {})
        self.seg_music_en.setChecked(music.get("enabled", False))
        self.seg_music_src.setText(music.get("file_path", ""))
        self.seg_music_vol.setValue(int(music.get("volume_db", -12)))
        self.tabs.setCurrentIndex(0)

    def get_silence_config(self) -> dict:
        return {
            "silence_threshold_db": self.sil_thresh.value(),
            "silence_min_duration_ms": self.sil_dur.value(),
            "silence_margin_ms": self.sil_margin.value(),
        }

    def get_export_config(self) -> dict:
        return {
            "platform": self.exp_platform.currentText().lower(),
            "burn_subtitles": self.exp_burn_subs.isChecked(),
            "subtitle_lang": self.exp_sub_lang.currentText()[:2].lower(),
            "subtitle_font": self.sub_font.currentText(),
            "subtitle_size": self.sub_size.value(),
        }
