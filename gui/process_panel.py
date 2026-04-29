from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
                              QLabel, QPushButton, QProgressBar, QFrame)
from PyQt6.QtCore import Qt, pyqtSlot, QTimer
from PyQt6.QtGui import QTextCursor
from datetime import datetime


class ModelStatusBar(QWidget):
    """Small status strip showing quota state for each Gemini model."""

    MODELS = ["gemini-2.5-flash", "gemini-2.5-pro", "groq-llama", "groq-whisper"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(22)
        self.setStyleSheet("background: #0A0A0A; border-top: 1px solid #1A1A1A;")
        lo = QHBoxLayout(self)
        lo.setContentsMargins(10, 0, 10, 0)
        lo.setSpacing(12)

        prefix = QLabel("AI Models:")
        prefix.setStyleSheet("color:#666; font-size:10px; background:transparent;")
        lo.addWidget(prefix)

        self._dots: dict[str, QLabel] = {}
        for m in self.MODELS:
            dot = QLabel("●")
            dot.setStyleSheet("color:#AAAAAA; font-size:12px; font-weight:bold; background:transparent;")
            dot.setToolTip(f"{m}: unknown")
            name_lbl = QLabel(m.replace("gemini-", ""))
            name_lbl.setStyleSheet("color:#888; font-size:10px; background:transparent;")
            lo.addWidget(dot)
            lo.addWidget(name_lbl)
            self._dots[m] = dot

        lo.addStretch()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(3000)  # refresh every 3s

    def _refresh(self):
        try:
            from core.agents.base_agent import get_quota_status
            status = get_quota_status()
        except Exception:
            return
        colors = {
            "ok":            "#2ECC71",
            "exhausted":     "#E74C3C",
            "rate_limited":  "#F39C12",
            "unavailable":   "#F39C12",
            "not_available": "#888888",
            "unknown":       "#AAAAAA",
        }
        tooltips = {
            "ok":            "✓ Working",
            "exhausted":     "✗ Quota exhausted — resets midnight PT",
            "rate_limited":  "⚠ Rate limited (temporary)",
            "unavailable":   "⚠ Server busy (503) — retrying with next model",
            "not_available": "✗ Not available for this API key",
            "unknown":       "? Not tested yet",
        }
        for model, dot in self._dots.items():
            s = status.get(model, "unknown")
            color = colors.get(s, "#AAAAAA")
            dot.setStyleSheet(
                f"color:{color}; font-size:12px; font-weight:bold; background:transparent;"
            )
            dot.setToolTip(f"{model}: {tooltips.get(s, s)}")


class ProcessPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_entries = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header = QWidget()
        header.setFixedHeight(36)
        header.setStyleSheet("background-color: #141414; border-top: 1px solid #2D2D2D; border-bottom: 1px solid #2D2D2D;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 0, 10, 0)

        title = QLabel("PROCESS LOG")
        title.setStyleSheet("color: #888888; font-size: 11px; font-weight: 700; letter-spacing: 1px; background: transparent;")
        h_layout.addWidget(title)
        h_layout.addStretch()

        self.step_label = QLabel("Idle")
        self.step_label.setStyleSheet("color: #666666; font-size: 11px; background: transparent;")
        h_layout.addWidget(self.step_label)

        h_layout.addSpacing(12)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(160)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        h_layout.addWidget(self.progress_bar)

        h_layout.addSpacing(12)

        self.resume_btn = QPushButton("▶▶  RESUME")
        self.resume_btn.setFixedSize(110, 24)
        self.resume_btn.setStyleSheet(
            "QPushButton { background-color: #27AE60; color: white; font-weight: 700; "
            "border-radius: 4px; border: none; font-size: 12px; }"
            "QPushButton:hover { background-color: #2ECC71; }"
        )
        self.resume_btn.setVisible(False)
        h_layout.addWidget(self.resume_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setFixedSize(60, 24)
        self.stop_btn.setProperty("role", "danger")
        self.stop_btn.setEnabled(False)
        h_layout.addWidget(self.stop_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedSize(60, 24)
        clear_btn.clicked.connect(self.clear)
        h_layout.addWidget(clear_btn)

        layout.addWidget(header)

        # Model status bar
        self.model_status = ModelStatusBar(self)
        layout.addWidget(self.model_status)

        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setObjectName("process_log")
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(80)
        layout.addWidget(self.log_text)

    @pyqtSlot(str, str)
    def append_log(self, level: str, message: str):
        colors = {
            "INFO": "#00CC44",
            "SUCCESS": "#2ECC71",
            "WARNING": "#F39C12",
            "ERROR": "#E74C3C",
            "DEBUG": "#666666",
            "STEP": "#6C3BE4",
        }
        color = colors.get(level.upper(), "#CCCCCC")
        ts = datetime.now().strftime("%H:%M:%S")
        html = (f'<span style="color:#555555;">[{ts}]</span> '
                f'<span style="color:{color}; font-weight:600;">[{level}]</span> '
                f'<span style="color:#DDDDDD;">{message}</span><br>')
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
        self.log_text.insertHtml(html)
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
        self._log_entries.append({"level": level, "message": message, "ts": ts})

    @pyqtSlot(int)
    def set_progress(self, value: int):
        self.progress_bar.setValue(max(0, min(100, value)))

    @pyqtSlot(int, str)
    def set_step(self, step_idx: int, step_name: str):
        self.step_label.setText(f"Step {step_idx + 1}/8: {step_name}")
        self.append_log("STEP", f"Starting: {step_name}")

    def set_pipeline_running(self, running: bool):
        self.stop_btn.setEnabled(running)
        if not running:
            self.step_label.setText("Idle")
            self.progress_bar.setValue(0)

    def clear(self):
        self.log_text.clear()
        self._log_entries.clear()

    def export_log(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            for entry in self._log_entries:
                f.write(f"[{entry['ts']}] [{entry['level']}] {entry['message']}\n")
