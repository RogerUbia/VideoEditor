from dataclasses import dataclass, field
from typing import List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QPushButton, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect, QRectF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics, QPainterPath,
    QMouseEvent, QWheelEvent,
)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class TimelineClip:
    id:          str
    track:       int        # 0=video, 1=audio, 2=text/overlay
    start_s:     float
    end_s:       float
    label:       str
    color:       str        # hex
    is_selected: bool = False
    is_duplicate: bool = False


TRACK_COLORS = {
    0: "#4A235A",   # video
    1: "#1A5276",   # audio / music
    2: "#1A4731",   # text / subtitle
}

TRACK_LABELS = {0: "VIDEO", 1: "AUDIO", 2: "TEXT"}

TRACK_HEIGHT = 38
RULER_HEIGHT = 24
LABEL_WIDTH  = 60


# ── Timeline canvas ───────────────────────────────────────────────────────────

class TimelineCanvas(QWidget):
    seek_requested     = pyqtSignal(float)   # seconds
    clip_selected      = pyqtSignal(str)     # clip id
    clip_moved         = pyqtSignal(str, float)  # clip id, new start_s

    def __init__(self, parent=None):
        super().__init__(parent)
        self.clips:       List[TimelineClip] = []
        self.duration_s:  float = 60.0
        self.playhead_s:  float = 0.0
        self.px_per_s:    float = 80.0      # zoom level
        self.scroll_s:    float = 0.0       # horizontal scroll offset in seconds

        self._drag_clip:  TimelineClip | None = None
        self._drag_offset: float = 0.0
        self._drag_active: bool = False

        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(RULER_HEIGHT + TRACK_HEIGHT * 3 + 4)

    # ── Coordinate helpers ────────────────────────────────────────────────────

    def _s_to_px(self, s: float) -> float:
        return LABEL_WIDTH + (s - self.scroll_s) * self.px_per_s

    def _px_to_s(self, px: float) -> float:
        return (px - LABEL_WIDTH) / self.px_per_s + self.scroll_s

    def _track_y(self, track: int) -> int:
        return RULER_HEIGHT + track * TRACK_HEIGHT

    def _visible_s_range(self) -> tuple[float, float]:
        w = max(1, self.width() - LABEL_WIDTH)
        return self.scroll_s, self.scroll_s + w / self.px_per_s

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Background
        painter.fillRect(0, 0, w, h, QColor("#141414"))

        # Track label strip
        painter.fillRect(0, 0, LABEL_WIDTH, h, QColor("#1A1A1A"))
        painter.setPen(QPen(QColor("#2D2D2D"), 1))
        painter.drawLine(LABEL_WIDTH, 0, LABEL_WIDTH, h)

        # Track rows
        font_small = QFont("Segoe UI", 9, QFont.Weight.DemiBold)
        painter.setFont(font_small)

        for track, label in TRACK_LABELS.items():
            ty = self._track_y(track)
            bg = QColor("#181818") if track % 2 == 0 else QColor("#161616")
            painter.fillRect(LABEL_WIDTH, ty, w - LABEL_WIDTH, TRACK_HEIGHT, bg)
            painter.fillRect(0, ty, LABEL_WIDTH, TRACK_HEIGHT, QColor("#1A1A1A"))
            # Horizontal separator
            painter.setPen(QPen(QColor("#2D2D2D"), 1))
            painter.drawLine(0, ty, w, ty)
            # Track label
            painter.setPen(QPen(QColor("#555555"), 1))
            painter.drawText(
                QRect(0, ty, LABEL_WIDTH, TRACK_HEIGHT),
                Qt.AlignmentFlag.AlignCenter, label
            )

        # Time ruler
        painter.fillRect(LABEL_WIDTH, 0, w - LABEL_WIDTH, RULER_HEIGHT, QColor("#0F0F0F"))
        painter.setPen(QPen(QColor("#2D2D2D"), 1))
        painter.drawLine(0, RULER_HEIGHT, w, RULER_HEIGHT)

        # Ruler ticks and labels
        s_start, s_end = self._visible_s_range()
        # Determine tick interval based on zoom
        if self.px_per_s >= 200:
            minor_interval, major_interval = 0.5, 5.0
        elif self.px_per_s >= 80:
            minor_interval, major_interval = 1.0, 10.0
        elif self.px_per_s >= 30:
            minor_interval, major_interval = 2.0, 10.0
        else:
            minor_interval, major_interval = 5.0, 30.0

        import math
        first_minor = math.floor(s_start / minor_interval) * minor_interval
        s = first_minor
        while s <= s_end + minor_interval:
            px = int(self._s_to_px(s))
            is_major = abs(s % major_interval) < 0.001 or abs(s % major_interval - major_interval) < 0.001
            if is_major:
                painter.setPen(QPen(QColor("#555555"), 1))
                painter.drawLine(px, RULER_HEIGHT - 10, px, RULER_HEIGHT)
                # Label
                mins = int(s) // 60
                secs = int(s) % 60
                label_text = f"{mins}:{secs:02d}"
                painter.setPen(QPen(QColor("#888888"), 1))
                font_ruler = QFont("Segoe UI", 9)
                painter.setFont(font_ruler)
                painter.drawText(px + 3, RULER_HEIGHT - 4, label_text)
            else:
                painter.setPen(QPen(QColor("#3A3A3A"), 1))
                painter.drawLine(px, RULER_HEIGHT - 5, px, RULER_HEIGHT)
            s += minor_interval

        # Clips
        clip_font = QFont("Segoe UI", 9)
        painter.setFont(clip_font)
        fm = QFontMetrics(clip_font)

        for clip in self.clips:
            x1 = self._s_to_px(clip.start_s)
            x2 = self._s_to_px(clip.end_s)
            ty = self._track_y(clip.track)

            if x2 < LABEL_WIDTH or x1 > w:
                continue

            x1_clamped = max(x1, float(LABEL_WIDTH))
            clip_w = max(2.0, x2 - x1_clamped)

            rect = QRectF(x1_clamped, ty + 3, clip_w, TRACK_HEIGHT - 6)
            path = QPainterPath()
            path.addRoundedRect(rect, 4, 4)

            base_color = QColor(clip.color)
            if clip.is_selected:
                base_color = base_color.lighter(150)
            if clip.is_duplicate:
                base_color.setAlpha(100)

            painter.fillPath(path, QBrush(base_color))
            border_color = base_color.lighter(130) if clip.is_selected else QColor("#555555")
            painter.setPen(QPen(border_color, 1 if not clip.is_selected else 2))
            painter.drawPath(path)

            # Label
            if clip_w > 20:
                label_x = x1_clamped + 5
                label_text = fm.elidedText(
                    clip.label, Qt.TextElideMode.ElideRight, int(clip_w) - 10
                )
                painter.setPen(QPen(QColor("#FFFFFF"), 1))
                painter.drawText(
                    int(label_x), int(ty + TRACK_HEIGHT // 2 + 4), label_text
                )

        # Playhead
        ph_px = int(self._s_to_px(self.playhead_s))
        if LABEL_WIDTH <= ph_px <= w:
            painter.setPen(QPen(QColor("#E74C3C"), 2))
            painter.drawLine(ph_px, 0, ph_px, h)
            # Triangle head
            path = QPainterPath()
            path.moveTo(ph_px - 6, 0)
            path.lineTo(ph_px + 6, 0)
            path.lineTo(ph_px, 10)
            path.closeSubpath()
            painter.fillPath(path, QBrush(QColor("#E74C3C")))

        painter.end()

    # ── Mouse events ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        px = event.position().x()
        py = event.position().y()

        if py < RULER_HEIGHT:
            s = self._px_to_s(px)
            self.playhead_s = max(0, min(s, self.duration_s))
            self.seek_requested.emit(self.playhead_s)
            self.update()
            return

        # Find clicked clip
        for clip in reversed(self.clips):
            x1 = self._s_to_px(clip.start_s)
            x2 = self._s_to_px(clip.end_s)
            ty = self._track_y(clip.track)
            if x1 <= px <= x2 and ty <= py <= ty + TRACK_HEIGHT:
                for c in self.clips:
                    c.is_selected = False
                clip.is_selected = True
                self._drag_clip    = clip
                self._drag_offset  = self._px_to_s(px) - clip.start_s
                self._drag_active  = False
                self.clip_selected.emit(clip.id)
                self.update()
                return

        for c in self.clips:
            c.is_selected = False
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_clip and event.buttons() & Qt.MouseButton.LeftButton:
            new_start = self._px_to_s(event.position().x()) - self._drag_offset
            new_start = max(0.0, round(new_start * 10) / 10)  # snap 0.1s
            dur = self._drag_clip.end_s - self._drag_clip.start_s
            self._drag_clip.start_s = new_start
            self._drag_clip.end_s   = new_start + dur
            self._drag_active = True
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._drag_clip and self._drag_active:
            self.clip_moved.emit(self._drag_clip.id, self._drag_clip.start_s)
        self._drag_clip   = None
        self._drag_active = False

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Zoom
            factor = 1.15 if delta > 0 else 1 / 1.15
            self.px_per_s = max(10.0, min(500.0, self.px_per_s * factor))
        else:
            # Scroll
            s_shift = -delta / 120.0 * (5.0 / (self.px_per_s / 80.0))
            self.scroll_s = max(0.0, self.scroll_s + s_shift)
        self.update()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_playhead(self, s: float):
        self.playhead_s = s
        # Auto-scroll to keep playhead visible
        s_start, s_end = self._visible_s_range()
        if s > s_end - 5 or s < s_start:
            margin = (s_end - s_start) * 0.1
            self.scroll_s = max(0.0, s - margin)
        self.update()

    def load_clips(self, clips: list[TimelineClip], duration_s: float = 60.0):
        self.clips = clips
        self.duration_s = duration_s
        self.update()

    def zoom_to_fit(self):
        if self.duration_s > 0:
            available = max(1, self.width() - LABEL_WIDTH)
            self.px_per_s = available / self.duration_s * 0.95
            self.scroll_s = 0.0
            self.update()


# ── Timeline Panel ────────────────────────────────────────────────────────────

class TimelinePanel(QWidget):
    seek_requested = pyqtSignal(float)
    clip_selected  = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("timeline_widget")
        self._setup_ui()

    def _setup_ui(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(30)
        header.setStyleSheet(
            "background:#0F0F0F; border-bottom:1px solid #2D2D2D;"
        )
        h_lo = QHBoxLayout(header)
        h_lo.setContentsMargins(8, 0, 8, 0)
        h_lo.setSpacing(6)

        title = QLabel("TIMELINE")
        title.setStyleSheet(
            "color:#888; font-size:11px; font-weight:700;"
            "letter-spacing:1px; background:transparent;"
        )
        h_lo.addWidget(title)
        h_lo.addStretch()

        def ctrl_btn(text, slot, width=36):
            b = QPushButton(text)
            b.setFixedSize(width, 22)
            b.clicked.connect(slot)
            return b

        h_lo.addWidget(ctrl_btn("⊟", self._zoom_out))
        h_lo.addWidget(ctrl_btn("⊞", self._zoom_in))
        h_lo.addWidget(ctrl_btn("Fit", self._fit, 38))
        lo.addWidget(header)

        # Canvas
        self.canvas = TimelineCanvas(self)
        self.canvas.seek_requested.connect(self.seek_requested)
        self.canvas.clip_selected.connect(self.clip_selected)
        lo.addWidget(self.canvas, stretch=1)

    def _zoom_in(self):
        self.canvas.px_per_s = min(500.0, self.canvas.px_per_s * 1.3)
        self.canvas.update()

    def _zoom_out(self):
        self.canvas.px_per_s = max(10.0, self.canvas.px_per_s / 1.3)
        self.canvas.update()

    def _fit(self):
        self.canvas.zoom_to_fit()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_playhead(self, s: float):
        self.canvas.set_playhead(s)

    def load_from_script(self, script: dict, video_duration_s: float = 60.0):
        clips: list[TimelineClip] = []
        segments = script.get("segments", [])

        for seg in segments:
            seg_id    = seg.get("id", str(id(seg)))
            start     = self._t2s(seg.get("time_start", "0:00"))
            end       = self._t2s(seg.get("time_end",   "0:05"))
            is_dup    = seg.get("is_duplicate", False)
            label     = seg.get("content", "")[:30] or f"Seg {seg.get('order', 0) + 1}"

            # Video track
            clips.append(TimelineClip(
                id=seg_id, track=0,
                start_s=start, end_s=end,
                label=label,
                color=TRACK_COLORS[0],
                is_duplicate=is_dup,
            ))

            # Music track
            if seg.get("music", {}).get("enabled"):
                clips.append(TimelineClip(
                    id=f"{seg_id}_music", track=1,
                    start_s=start, end_s=end,
                    label="♪ " + seg["music"].get("file_path", "")[-20:],
                    color=TRACK_COLORS[1],
                ))

            # Text overlay track
            if seg.get("text_overlay", {}).get("enabled"):
                clips.append(TimelineClip(
                    id=f"{seg_id}_text", track=2,
                    start_s=start, end_s=end,
                    label="T  " + seg["text_overlay"].get("text", "")[:20],
                    color=TRACK_COLORS[2],
                ))

        dur = max(video_duration_s, max((c.end_s for c in clips), default=10.0))
        self.canvas.load_clips(clips, dur)
        self.canvas.zoom_to_fit()

    def clear(self):
        self.canvas.clips = []
        self.canvas.update()

    @staticmethod
    def _t2s(t: str) -> float:
        t = t.replace(",", ".")
        parts = t.split(":")
        try:
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
        except (ValueError, IndexError):
            pass
        return 0.0
