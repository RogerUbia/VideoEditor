"""
PreviewPanel: OpenCV for video frames (fast, reliable) +
QMediaPlayer audio-only for sound. Both synced together.
"""
import os
import time
import subprocess
import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QComboBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QUrl, QThread, QMutex, QMutexLocker
from PyQt6.QtGui import QImage, QPixmap

try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    _HAS_AUDIO = True
except ImportError:
    _HAS_AUDIO = False

import cv2


# ── OpenCV frame thread ───────────────────────────────────────────────────────

class VideoPlayerThread(QThread):
    frame_ready       = pyqtSignal(QImage)
    position_changed  = pyqtSignal(float)   # seconds
    playback_finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cap     = None
        self._paused  = True
        self._stopped = False
        self._speed   = 1.0
        self._seek_ms = -1.0
        self._fps     = 25.0
        self._mutex   = QMutex()
        self._rotation = 0  # degrees from metadata

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, path: str, rotation: int = 0):
        with QMutexLocker(self._mutex):
            if self._cap:
                self._cap.release()
            self._cap      = cv2.VideoCapture(path)
            self._fps      = self._cap.get(cv2.CAP_PROP_FPS) or 25.0
            self._paused   = True
            self._stopped  = False
            self._seek_ms  = 0.0
            self._rotation = rotation

    def play(self):   self._paused = False
    def pause(self):  self._paused = True
    def stop(self):   self._stopped = True; self._paused = True

    def seek(self, s: float):
        with QMutexLocker(self._mutex):
            self._seek_ms = max(0.0, s * 1000.0)

    def set_speed(self, s: float): self._speed = s

    def get_duration(self) -> float:
        if self._cap:
            return self._cap.get(cv2.CAP_PROP_FRAME_COUNT) / max(1.0, self._fps)
        return 0.0

    # ── Thread loop ───────────────────────────────────────────────────────────

    def run(self):
        while not self._stopped:
            # Handle seek (also while paused)
            with QMutexLocker(self._mutex):
                do_seek = self._seek_ms >= 0
                seek_ms = self._seek_ms
                self._seek_ms = -1.0

            if do_seek and self._cap:
                self._cap.set(cv2.CAP_PROP_POS_MSEC, seek_ms)
                ret, frame = self._cap.read()
                if ret:
                    self.frame_ready.emit(self._proc(frame))
                    pos = self._cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                    self.position_changed.emit(pos)

            if self._paused or not self._cap:
                time.sleep(0.04)
                continue

            t0  = time.perf_counter()
            ret, frame = self._cap.read()
            if not ret:
                self._paused = True
                self.playback_finished.emit()
                continue

            pos = self._cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            self.frame_ready.emit(self._proc(frame))
            self.position_changed.emit(pos)

            elapsed = time.perf_counter() - t0
            sleep   = 1.0 / (self._fps * self._speed) - elapsed
            if sleep > 0:
                time.sleep(sleep)

    def _proc(self, frame) -> QImage:
        # Apply rotation if needed
        if self._rotation == 90:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif self._rotation == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        elif self._rotation == 270:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        return QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()


# ── Preview Panel ─────────────────────────────────────────────────────────────

class PreviewPanel(QWidget):
    position_changed = pyqtSignal(float)   # seconds — for timeline sync

    def __init__(self, parent=None):
        super().__init__(parent)
        self._duration  = 0.0
        self._cur_pos   = 0.0
        self._loaded    = False
        self._cur_path  = ""

        # Video thread (OpenCV)
        self.player = VideoPlayerThread(self)
        self.player.frame_ready.connect(self._on_frame)
        self.player.position_changed.connect(self._on_position)
        self.player.playback_finished.connect(self._on_finished)
        self.player.start()

        # Audio player (QMediaPlayer, no video output)
        self._audio_player = None
        self._audio_out    = None
        if _HAS_AUDIO:
            self._audio_player = QMediaPlayer(self)
            self._audio_out    = QAudioOutput(self)
            self._audio_player.setAudioOutput(self._audio_out)
            self._audio_out.setVolume(1.0)

        self._setup_ui()
        self._connect_transport()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(6, 6, 6, 6)
        lo.setSpacing(4)

        # Video display (QLabel)
        self._video_lbl = QLabel()
        self._video_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._video_lbl.setStyleSheet("background:#000; border-radius:4px;")
        self._video_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._video_lbl.setText(
            "No video loaded\nDrag & drop or File → Import Video"
        )
        self._video_lbl.setStyleSheet(
            "background:#000; color:#444; font-size:13px;"
        )
        lo.addWidget(self._video_lbl, stretch=1)

        # Position slider
        self.pos_slider = QSlider(Qt.Orientation.Horizontal)
        self.pos_slider.setRange(0, 10000)
        self.pos_slider.setValue(0)
        self.pos_slider.setEnabled(False)
        lo.addWidget(self.pos_slider)

        # Volume row (audio only)
        extras = QWidget()
        extras.setStyleSheet("background:transparent;")
        ex_lo = QHBoxLayout(extras)
        ex_lo.setContentsMargins(0, 0, 0, 0)
        ex_lo.setSpacing(6)

        if _HAS_AUDIO and self._audio_player:
            vol_lbl = QLabel("🔊")
            vol_lbl.setStyleSheet("background:transparent; color:#888; font-size:12px;")
            ex_lo.addWidget(vol_lbl)
            self.vol_slider = QSlider(Qt.Orientation.Horizontal)
            self.vol_slider.setRange(0, 100)
            self.vol_slider.setValue(100)
            self.vol_slider.setFixedWidth(80)
            self.vol_slider.valueChanged.connect(
                lambda v: self._audio_out.setVolume(v / 100.0)
            )
            ex_lo.addWidget(self.vol_slider)

        ex_lo.addStretch()
        mode = "🔊 Video+Audio" if _HAS_AUDIO else "🔇 Video only"
        mode_lbl = QLabel(mode)
        mode_lbl.setStyleSheet("color:#555; font-size:9px; background:transparent;")
        ex_lo.addWidget(mode_lbl)
        lo.addWidget(extras)

        # Transport controls
        ctrl = QWidget()
        ctrl.setFixedHeight(38)
        ctrl.setStyleSheet("background:transparent;")
        c_lo = QHBoxLayout(ctrl)
        c_lo.setContentsMargins(0, 0, 0, 0)
        c_lo.setSpacing(4)

        def btn(text, w=36):
            b = QPushButton(text)
            b.setFixedSize(w, 30)
            return b

        self.first_btn = btn("|◀")
        self.prev_btn  = btn("◀")
        self.play_btn  = btn("▶", 48)
        self.play_btn.setProperty("role", "primary")
        self.next_btn  = btn("▶")
        self.last_btn  = btn("▶|")

        for b in (self.first_btn, self.prev_btn, self.play_btn,
                  self.next_btn, self.last_btn):
            c_lo.addWidget(b)
        c_lo.addStretch()

        self.time_lbl = QLabel("0:00 / 0:00")
        self.time_lbl.setStyleSheet(
            "color:#888; font-size:12px; background:transparent; min-width:90px;"
        )
        c_lo.addWidget(self.time_lbl)

        speed_lbl = QLabel("Speed:")
        speed_lbl.setStyleSheet("color:#888; font-size:11px; background:transparent;")
        c_lo.addWidget(speed_lbl)
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.25x", "0.5x", "1x", "1.5x", "2x"])
        self.speed_combo.setCurrentText("1x")
        self.speed_combo.setFixedWidth(70)
        self.speed_combo.currentTextChanged.connect(
            lambda t: self.player.set_speed(float(t.replace("x", "")))
        )
        c_lo.addWidget(self.speed_combo)

        lo.addWidget(ctrl)

    def _connect_transport(self):
        self.play_btn.clicked.connect(self._toggle_play)
        self.first_btn.clicked.connect(lambda: self.seek(0))
        self.last_btn.clicked.connect(lambda: self.seek(self._duration))
        self.prev_btn.clicked.connect(
            lambda: self.seek(max(0, self._cur_pos - 5))
        )
        self.next_btn.clicked.connect(
            lambda: self.seek(min(self._duration, self._cur_pos + 5))
        )
        self.pos_slider.sliderMoved.connect(
            lambda v: self.seek(v / 10000 * self._duration) if self._duration else None
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def load_video(self, path: str):
        if not path or not os.path.exists(path):
            return
        self._cur_path = path
        self._loaded   = True
        self._cur_pos  = 0.0
        self.pos_slider.setEnabled(True)
        self._video_lbl.setStyleSheet("background:#000;")

        # Detect rotation from metadata
        rotation = self._get_rotation(path)

        # Load video in OpenCV thread
        self.player.load(path, rotation)
        self._duration = self.player.get_duration()
        self._update_time()
        self.player.seek(0)

        # Load audio separately
        if self._audio_player:
            self._audio_player.setSource(QUrl.fromLocalFile(os.path.abspath(path)))

    def seek(self, seconds: float):
        self._cur_pos = max(0.0, min(seconds, self._duration))
        self.player.seek(self._cur_pos)
        if self._audio_player:
            self._audio_player.setPosition(int(self._cur_pos * 1000))

    def get_duration(self) -> float:
        return self._duration

    def _toggle_play(self):
        if not self._loaded:
            return
        if self.player._paused:
            self.player.play()
            if self._audio_player:
                self._audio_player.play()
            self.play_btn.setText("⏸")
        else:
            self.player.pause()
            if self._audio_player:
                self._audio_player.pause()
            self.play_btn.setText("▶")

    # ── Slots ─────────────────────────────────────────────────────────────────

    @pyqtSlot(QImage)
    def _on_frame(self, img: QImage):
        px = QPixmap.fromImage(img).scaled(
            self._video_lbl.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,  # faster than Smooth
        )
        self._video_lbl.setPixmap(px)

    @pyqtSlot(float)
    def _on_position(self, pos_s: float):
        self._cur_pos = pos_s
        self.position_changed.emit(pos_s)
        self._update_time()
        if self._duration > 0:
            val = int(pos_s / self._duration * 10000)
            self.pos_slider.blockSignals(True)
            self.pos_slider.setValue(val)
            self.pos_slider.blockSignals(False)

    @pyqtSlot()
    def _on_finished(self):
        self.play_btn.setText("▶")
        if self._audio_player:
            self._audio_player.stop()
        self.seek(0)

    def _update_time(self):
        self.time_lbl.setText(
            f"{self._fmt(self._cur_pos)} / {self._fmt(self._duration)}"
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _get_rotation(path: str) -> int:
        """Read video rotation from metadata using ffprobe."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
                 "-show_entries", "stream_tags=rotate",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, timeout=5
            )
            rot = result.stdout.strip()
            return int(rot) if rot.lstrip("-").isdigit() else 0
        except Exception:
            return 0

    @staticmethod
    def _fmt(s: float) -> str:
        return f"{int(s) // 60}:{int(s) % 60:02d}"

    def closeEvent(self, event):
        self.player.stop()
        self.player.wait(2000)
        super().closeEvent(event)
