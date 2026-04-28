import cv2
import time
import numpy as np
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QSlider, QComboBox, QSizePolicy)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QMutex, QMutexLocker
from PyQt6.QtGui import QImage, QPixmap


class VideoPlayerThread(QThread):
    frame_ready = pyqtSignal(QImage)
    position_changed = pyqtSignal(float)  # seconds
    playback_finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cap = None
        self._paused = True
        self._stopped = False
        self._speed = 1.0
        self._seek_pos = -1.0
        self._fps = 25.0
        self._mutex = QMutex()

    def load(self, path: str):
        with QMutexLocker(self._mutex):
            if self._cap:
                self._cap.release()
            self._cap = cv2.VideoCapture(path)
            self._fps = self._cap.get(cv2.CAP_PROP_FPS) or 25.0
            self._paused = True
            self._stopped = False
            self._seek_pos = 0.0

    def play(self):
        self._paused = False

    def pause(self):
        self._paused = True

    def seek(self, seconds: float):
        with QMutexLocker(self._mutex):
            self._seek_pos = seconds

    def set_speed(self, speed: float):
        self._speed = speed

    def stop(self):
        self._stopped = True
        self._paused = True

    def get_duration(self) -> float:
        if self._cap:
            frames = self._cap.get(cv2.CAP_PROP_FRAME_COUNT)
            return frames / self._fps if self._fps > 0 else 0.0
        return 0.0

    def _read_frame(self):
        with QMutexLocker(self._mutex):
            if self._cap is None:
                return None
            if self._seek_pos >= 0:
                self._cap.set(cv2.CAP_PROP_POS_MSEC, self._seek_pos * 1000)
                self._seek_pos = -1.0
            ret, frame = self._cap.read()
            if not ret:
                return None
            pos = self._cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            return frame, pos

    def run(self):
        while not self._stopped:
            if self._paused or self._cap is None:
                time.sleep(0.05)
                # Still emit frame if seek requested while paused
                if self._seek_pos >= 0:
                    result = self._read_frame()
                    if result:
                        frame, pos = result
                        qimg = self._frame_to_qimage(frame)
                        self.frame_ready.emit(qimg)
                        self.position_changed.emit(pos)
                continue

            t_start = time.perf_counter()
            result = self._read_frame()
            if result is None:
                self._paused = True
                self.playback_finished.emit()
                continue

            frame, pos = result
            qimg = self._frame_to_qimage(frame)
            self.frame_ready.emit(qimg)
            self.position_changed.emit(pos)

            elapsed = time.perf_counter() - t_start
            target_interval = 1.0 / (self._fps * self._speed)
            sleep_time = target_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    @staticmethod
    def _frame_to_qimage(frame: np.ndarray) -> QImage:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        return QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()


class PreviewPanel(QWidget):
    seek_requested = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._duration = 0.0
        self._current_pos = 0.0
        self._loaded = False
        self.player = VideoPlayerThread(self)
        self._setup_ui()
        self._connect_signals()
        self.player.start()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Video display
        self.video_label = QLabel()
        self.video_label.setObjectName("video_preview")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_label.setText("No video loaded\nDrag & drop a video file or use File → Open Video")
        self.video_label.setStyleSheet("color: #555555; font-size: 14px;")
        layout.addWidget(self.video_label, stretch=1)

        # Position slider
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setMinimum(0)
        self.position_slider.setMaximum(10000)
        self.position_slider.setValue(0)
        self.position_slider.setEnabled(False)
        layout.addWidget(self.position_slider)

        # Transport controls
        controls = QWidget()
        controls.setFixedHeight(40)
        controls.setStyleSheet("background: transparent;")
        ctrl_layout = QHBoxLayout(controls)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(4)

        def make_btn(text, width=36):
            b = QPushButton(text)
            b.setFixedSize(width, 30)
            return b

        self.first_btn = make_btn("|◀")
        self.prev_btn = make_btn("◀")
        self.play_btn = make_btn("▶", 48)
        self.play_btn.setProperty("role", "primary")
        self.next_btn = make_btn("▶")
        self.last_btn = make_btn("▶|")

        ctrl_layout.addWidget(self.first_btn)
        ctrl_layout.addWidget(self.prev_btn)
        ctrl_layout.addWidget(self.play_btn)
        ctrl_layout.addWidget(self.next_btn)
        ctrl_layout.addWidget(self.last_btn)
        ctrl_layout.addStretch()

        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setStyleSheet("color: #888888; font-size: 12px; background: transparent; min-width: 90px;")
        ctrl_layout.addWidget(self.time_label)

        ctrl_layout.addSpacing(8)
        speed_label = QLabel("Speed:")
        speed_label.setStyleSheet("color: #888888; font-size: 11px; background: transparent;")
        ctrl_layout.addWidget(speed_label)

        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.25x", "0.5x", "1x", "1.5x", "2x"])
        self.speed_combo.setCurrentText("1x")
        self.speed_combo.setFixedWidth(70)
        ctrl_layout.addWidget(self.speed_combo)

        layout.addWidget(controls)

    def _connect_signals(self):
        self.player.frame_ready.connect(self._on_frame)
        self.player.position_changed.connect(self._on_position)
        self.player.playback_finished.connect(self._on_finished)
        self.play_btn.clicked.connect(self._toggle_play)
        self.first_btn.clicked.connect(lambda: self.seek(0))
        self.last_btn.clicked.connect(lambda: self.seek(self._duration))
        self.prev_btn.clicked.connect(lambda: self.seek(max(0, self._current_pos - 5)))
        self.next_btn.clicked.connect(lambda: self.seek(min(self._duration, self._current_pos + 5)))
        self.position_slider.sliderMoved.connect(self._on_slider_moved)
        self.speed_combo.currentTextChanged.connect(self._on_speed_changed)

    def load_video(self, path: str):
        self.player.load(path)
        self._duration = self.player.get_duration()
        self._loaded = True
        self.position_slider.setEnabled(True)
        self.video_label.setStyleSheet("")
        # Show first frame
        self.player.seek(0)

    def seek(self, seconds: float):
        self.player.seek(seconds)
        self._current_pos = seconds

    def _toggle_play(self):
        if not self._loaded:
            return
        if self.player._paused:
            self.player.play()
            self.play_btn.setText("⏸")
        else:
            self.player.pause()
            self.play_btn.setText("▶")

    @pyqtSlot(QImage)
    def _on_frame(self, qimage: QImage):
        pixmap = QPixmap.fromImage(qimage)
        scaled = pixmap.scaled(
            self.video_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.video_label.setPixmap(scaled)

    @pyqtSlot(float)
    def _on_position(self, pos: float):
        self._current_pos = pos
        if self._duration > 0:
            slider_val = int(pos / self._duration * 10000)
            self.position_slider.blockSignals(True)
            self.position_slider.setValue(slider_val)
            self.position_slider.blockSignals(False)
        self.time_label.setText(f"{self._fmt(pos)} / {self._fmt(self._duration)}")

    @pyqtSlot()
    def _on_finished(self):
        self.play_btn.setText("▶")
        self.seek(0)

    def _on_slider_moved(self, value: int):
        if self._duration > 0:
            self.seek(value / 10000 * self._duration)

    def _on_speed_changed(self, text: str):
        speed = float(text.replace("x", ""))
        self.player.set_speed(speed)

    @staticmethod
    def _fmt(seconds: float) -> str:
        m = int(seconds) // 60
        s = int(seconds) % 60
        return f"{m}:{s:02d}"

    def closeEvent(self, event):
        self.player.stop()
        self.player.wait(2000)
        super().closeEvent(event)
