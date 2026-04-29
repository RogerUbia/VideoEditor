from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSizePolicy, QScrollBar, QAbstractScrollArea
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QRectF, QPoint
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics,
    QPainterPath, QLinearGradient, QCursor, QMouseEvent, QWheelEvent,
)

from core.timeline_editor import (
    TRACK_VIDEO, TRACK_FX, TRACK_MUSIC, TRACK_CA, TRACK_ES, TRACK_EN,
)

# ── Track layout ──────────────────────────────────────────────────────────────

@dataclass
class TrackInfo:
    name:   str
    height: int
    bg:     str

TRACKS = [
    TrackInfo("VIDEO",  56, "#141414"),
    TrackInfo("FX",     24, "#0F0F0F"),
    TrackInfo("MUSIC",  24, "#0F0F0F"),
    TrackInfo("CA",     22, "#0A0A0A"),
    TrackInfo("ES",     22, "#0A0A0A"),
    TrackInfo("EN",     22, "#0A0A0A"),
]

RULER_H  = 24
LABEL_W  = 52
TRIM_ZONE = 7   # px from clip edge that activates trim mode


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class TimelineClip:
    id:                  str
    track:               int
    start_s:             float
    end_s:               float
    label:               str
    color:               str
    effect_type:         str   = "none"
    has_transition_in:   bool  = False
    has_transition_out:  bool  = False
    has_pip:             bool  = False
    has_zoom:            bool  = False
    transition_in_dur:   float = 0.5
    transition_out_dur:  float = 0.5
    is_selected:         bool  = False
    is_duplicate:        bool  = False
    is_resizable:        bool  = True
    segment_data:        dict  = field(default_factory=dict)


# ── Timeline Canvas ───────────────────────────────────────────────────────────

class TimelineCanvas(QWidget):
    seek_requested   = pyqtSignal(float)          # seconds
    clip_selected    = pyqtSignal(str)            # clip id
    clip_moved       = pyqtSignal(str, float)     # id, new_start_s
    clip_trimmed     = pyqtSignal(str, float, float)  # id, new_start_s, new_end_s

    def __init__(self, parent=None):
        super().__init__(parent)
        self.clips:       List[TimelineClip] = []
        self.duration_s:  float = 60.0
        self.playhead_s:  float = 0.0
        self.px_per_s:    float = 80.0
        self.scroll_s:    float = 0.0
        self.scroll_y:    int   = 0     # vertical scroll offset in pixels

        self._drag_clip:   TimelineClip | None = None
        self._trim_clip:   TimelineClip | None = None
        self._trim_side:   str = ""          # "left" | "right"
        self._drag_offset: float = 0.0
        self._hover_clip:  TimelineClip | None = None
        self._hover_trim:  str = ""          # "left" | "right" | ""

        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._update_min_height()

    def _update_min_height(self):
        # Fixed small minimum — vertical scrollbar handles overflow
        self.setMinimumHeight(RULER_H + 80)

    # ── Coordinate helpers ────────────────────────────────────────────────────

    def _s_to_px(self, s: float) -> float:
        return LABEL_W + (s - self.scroll_s) * self.px_per_s

    def _px_to_s(self, px: float) -> float:
        return (px - LABEL_W) / self.px_per_s + self.scroll_s

    def _track_y(self, track_idx: int) -> int:
        y = RULER_H - self.scroll_y
        for i, t in enumerate(TRACKS):
            if i == track_idx:
                return y
            y += t.height + 1
        return y

    def _total_tracks_height(self) -> int:
        return sum(t.height + 1 for t in TRACKS)

    def _track_height(self, track_idx: int) -> int:
        if 0 <= track_idx < len(TRACKS):
            return TRACKS[track_idx].height
        return 28

    def _clip_at(self, px: float, py: float) -> tuple[TimelineClip | None, str]:
        """Return (clip, trim_side) for a given pixel position."""
        for clip in reversed(self.clips):
            x1 = self._s_to_px(clip.start_s)
            x2 = self._s_to_px(clip.end_s)
            ty = self._track_y(clip.track)
            th = self._track_height(clip.track)
            if not (ty <= py <= ty + th and x1 <= px <= x2):
                continue
            if clip.is_resizable:
                if abs(px - x1) <= TRIM_ZONE:
                    return clip, "left"
                if abs(px - x2) <= TRIM_ZONE:
                    return clip, "right"
            return clip, ""
        return None, ""

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Global background
        p.fillRect(0, 0, w, h, QColor("#0F0F0F"))

        # Clip drawing to the area BELOW the ruler so tracks don't bleed over it
        p.setClipRect(0, RULER_H, w, h - RULER_H)

        # Track backgrounds + labels (vertically scrollable)
        self._paint_tracks(p, w)

        # Clips (only those in the visible vertical range)
        for clip in self.clips:
            ty = self._track_y(clip.track)
            th = self._track_height(clip.track)
            if ty + th < RULER_H or ty > h:   # fully outside — skip
                continue
            self._paint_clip(p, clip)

        # Remove clip rect so ruler and playhead draw over everything
        p.setClipping(False)

        # Ruler always at top
        self._paint_ruler(p, w)

        # Playhead on top of everything
        self._paint_playhead(p, h)

        p.end()

    def _paint_tracks(self, p: QPainter, w: int):
        font = QFont("Segoe UI", 8, QFont.Weight.DemiBold)
        p.setFont(font)

        for i, track in enumerate(TRACKS):
            ty = self._track_y(i)
            th = track.height

            # Track background
            p.fillRect(LABEL_W, ty, w - LABEL_W, th, QColor(track.bg))

            # Label strip
            p.fillRect(0, ty, LABEL_W, th, QColor("#141414"))
            p.setPen(QPen(QColor("#444444"), 1))
            p.drawText(
                QRect(0, ty, LABEL_W - 2, th),
                Qt.AlignmentFlag.AlignCenter,
                track.name,
            )

            # Horizontal separator
            p.setPen(QPen(QColor("#222222"), 1))
            p.drawLine(0, ty + th, w, ty + th)

        # Vertical separator (label / content)
        p.setPen(QPen(QColor("#2D2D2D"), 1))
        p.drawLine(LABEL_W, RULER_H, LABEL_W, self.height())

    def _paint_ruler(self, p: QPainter, w: int):
        p.fillRect(LABEL_W, 0, w - LABEL_W, RULER_H, QColor("#0A0A0A"))
        p.setPen(QPen(QColor("#2D2D2D"), 1))
        p.drawLine(0, RULER_H, w, RULER_H)

        # Adaptive tick intervals
        if self.px_per_s >= 200:
            minor, major = 0.5, 5.0
        elif self.px_per_s >= 80:
            minor, major = 1.0, 10.0
        elif self.px_per_s >= 30:
            minor, major = 2.0, 10.0
        else:
            minor, major = 5.0, 30.0

        s_start, s_end = self.scroll_s, self.scroll_s + (w - LABEL_W) / self.px_per_s
        first = math.floor(s_start / minor) * minor
        s = first

        font_ruler = QFont("Segoe UI", 8)
        p.setFont(font_ruler)

        while s <= s_end + minor:
            px = int(self._s_to_px(s))
            is_major = (abs(s % major) < 0.01 or abs(s % major - major) < 0.01)
            if is_major:
                p.setPen(QPen(QColor("#555555"), 1))
                p.drawLine(px, RULER_H - 10, px, RULER_H)
                m_val = int(s) // 60
                sec   = int(s) % 60
                lbl   = f"{m_val}:{sec:02d}"
                p.setPen(QPen(QColor("#888888"), 1))
                p.drawText(px + 3, RULER_H - 3, lbl)
            else:
                p.setPen(QPen(QColor("#333333"), 1))
                p.drawLine(px, RULER_H - 5, px, RULER_H)
            s += minor

    def _paint_clip(self, p: QPainter, clip: TimelineClip):
        x1 = self._s_to_px(clip.start_s)
        x2 = self._s_to_px(clip.end_s)
        ty = self._track_y(clip.track)
        th = self._track_height(clip.track)
        w  = self.width()

        # Off-screen check
        if x2 < LABEL_W or x1 > w:
            return

        x1c     = max(x1, float(LABEL_W))
        clip_w  = max(2.0, x2 - x1c)
        padding = 3

        rect = QRectF(x1c, ty + padding, clip_w, th - padding * 2)
        path = QPainterPath()
        path.addRoundedRect(rect, 3, 3)

        # ── Fill ──────────────────────────────────────────────────────────────
        base = QColor(clip.color)
        if clip.is_duplicate:
            base.setAlpha(80)

        if clip.track == TRACK_VIDEO and clip.effect_type not in ("none", ""):
            # Gradient for effect clips
            grad = QLinearGradient(x1c, ty, x2, ty)
            grad.setColorAt(0.0, QColor(clip.color).lighter(130))
            grad.setColorAt(1.0, base)
            p.fillPath(path, QBrush(grad))
        else:
            p.fillPath(path, QBrush(base))

        # ── Transition markers ────────────────────────────────────────────────
        if clip.track == TRACK_VIDEO:
            if clip.has_transition_in and clip_w > 20:
                tri_w = min(clip.transition_in_dur * self.px_per_s, clip_w * 0.3)
                tri = QPainterPath()
                tri.moveTo(x1c,          ty + padding)
                tri.lineTo(x1c + tri_w,  ty + padding)
                tri.lineTo(x1c,          ty + th - padding)
                tri.closeSubpath()
                p.fillPath(tri, QBrush(QColor("#6C3BE4")))

            if clip.has_transition_out and clip_w > 20:
                tri_w = min(clip.transition_out_dur * self.px_per_s, clip_w * 0.3)
                tri = QPainterPath()
                tri.moveTo(x2,           ty + padding)
                tri.lineTo(x2 - tri_w,   ty + th - padding)
                tri.lineTo(x2,           ty + th - padding)
                tri.closeSubpath()
                p.fillPath(tri, QBrush(QColor("#6C3BE4")))

        # ── Border ────────────────────────────────────────────────────────────
        if clip.is_selected:
            pen = QPen(QColor("#FFFFFF"), 2)
        elif clip == self._hover_clip:
            pen = QPen(QColor("#9B59B6"), 1)
        else:
            pen = QPen(base.lighter(140), 1)
        p.setPen(pen)
        p.drawPath(path)

        # ── Trim handles ──────────────────────────────────────────────────────
        if clip.is_resizable and clip.is_selected and clip_w > 16:
            handle_color = QColor("#FFFFFF")
            p.setPen(QPen(handle_color, 2))
            cx = ty + padding + 3
            cy = ty + th - padding - 3
            p.drawLine(int(x1c) + 3, int(cx), int(x1c) + 3, int(cy))
            p.drawLine(int(x2) - 3,  int(cx), int(x2) - 3,  int(cy))

        # ── Icons on VIDEO track ──────────────────────────────────────────────
        if clip.track == TRACK_VIDEO and clip_w > 24:
            icon_x = int(x2) - 4
            icon_y = int(ty) + padding + 2
            icon_font = QFont("Segoe UI", 7)
            p.setFont(icon_font)
            p.setPen(QPen(QColor("#CCCCCC"), 1))
            icons = []
            if clip.has_zoom:
                icons.append("⊕")
            if clip.has_pip:
                icons.append("⊡")
            if icons and icon_x > LABEL_W + 10:
                p.drawText(icon_x - len(icons) * 10, icon_y + 9, " ".join(icons))

        # ── Label ─────────────────────────────────────────────────────────────
        if clip_w > 14:
            lbl_font_size = 9 if clip.track == TRACK_VIDEO else 8
            lbl_font = QFont("Segoe UI", lbl_font_size)
            p.setFont(lbl_font)
            fm = QFontMetrics(lbl_font)

            max_label_w = int(clip_w) - 10
            label = fm.elidedText(clip.label, Qt.TextElideMode.ElideRight, max_label_w)

            lbl_color = QColor("#FFFFFF") if clip.is_selected else QColor("#DDDDDD")
            p.setPen(QPen(lbl_color, 1))

            lbl_y_offset = (th // 2) + lbl_font_size // 2 - 1
            p.drawText(int(x1c) + 5, int(ty) + lbl_y_offset, label)

    def _paint_playhead(self, p: QPainter, h: int):
        ph_px = int(self._s_to_px(self.playhead_s))
        if LABEL_W <= ph_px <= self.width():
            p.setPen(QPen(QColor("#E74C3C"), 2))
            p.drawLine(ph_px, 0, ph_px, h)
            triangle = QPainterPath()
            triangle.moveTo(ph_px - 6, 0)
            triangle.lineTo(ph_px + 6, 0)
            triangle.lineTo(ph_px, 10)
            triangle.closeSubpath()
            p.fillPath(triangle, QBrush(QColor("#E74C3C")))

    # ── Mouse events ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        px = event.position().x()
        py = event.position().y()

        # Click on ruler → seek
        if py < RULER_H:
            self.playhead_s = max(0.0, min(self._px_to_s(px), self.duration_s))
            self.seek_requested.emit(self.playhead_s)
            self.update()
            return

        clip, trim_side = self._clip_at(px, py)

        # Deselect all
        for c in self.clips:
            c.is_selected = False

        if clip:
            clip.is_selected = True
            self.clip_selected.emit(clip.id)

            if trim_side:
                self._trim_clip = clip
                self._trim_side = trim_side
            elif clip.is_resizable:
                self._drag_clip   = clip
                self._drag_offset = self._px_to_s(px) - clip.start_s

        self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        px = event.position().x()
        py = event.position().y()

        # Trim drag
        if self._trim_clip and event.buttons() & Qt.MouseButton.LeftButton:
            s = max(0.0, self._px_to_s(px))
            clip = self._trim_clip
            if self._trim_side == "left":
                new_start = min(s, clip.end_s - 0.1)
                clip.start_s = round(new_start * 10) / 10
            else:
                new_end = max(s, clip.start_s + 0.1)
                clip.end_s = round(new_end * 10) / 10
            self.update()
            return

        # Move drag
        if self._drag_clip and event.buttons() & Qt.MouseButton.LeftButton:
            new_start = max(0.0, self._px_to_s(px) - self._drag_offset)
            new_start = round(new_start * 10) / 10
            dur = self._drag_clip.end_s - self._drag_clip.start_s
            self._drag_clip.start_s = new_start
            self._drag_clip.end_s   = new_start + dur
            self.update()
            return

        # Hover cursor
        clip, trim_side = self._clip_at(px, py)
        self._hover_clip = clip
        self._hover_trim = trim_side

        if trim_side:
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        elif clip and clip.is_resizable:
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        elif py < RULER_H:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._trim_clip:
            clip = self._trim_clip
            self.clip_trimmed.emit(clip.id, clip.start_s, clip.end_s)
            self._trim_clip = None
            self._trim_side = ""

        elif self._drag_clip:
            self.clip_moved.emit(self._drag_clip.id, self._drag_clip.start_s)
            self._drag_clip = None

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        mods  = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            # Ctrl+wheel = horizontal zoom
            factor = 1.15 if delta > 0 else 1 / 1.15
            self.px_per_s = max(10.0, min(600.0, self.px_per_s * factor))
        elif mods & Qt.KeyboardModifier.ShiftModifier:
            # Shift+wheel = vertical scroll
            visible_h  = max(1, self.height() - RULER_H)
            total_h    = self._total_tracks_height()
            max_scroll = max(0, total_h - visible_h)
            self.scroll_y = max(0, min(max_scroll, self.scroll_y - delta // 3))
            parent = self.parent()
            if hasattr(parent, "_sync_v_scrollbar"):
                parent._sync_v_scrollbar()
        else:
            # wheel = horizontal scroll
            shift = -delta / 120.0 * (5.0 / max(0.1, self.px_per_s / 80.0))
            self.scroll_s = max(0.0, self.scroll_s + shift)
        self.update()
        parent = self.parent()
        if hasattr(parent, "_sync_scrollbar"):
            parent._sync_scrollbar()

    # ── Public API ────────────────────────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        parent = self.parent()
        if hasattr(parent, "_sync_v_scrollbar"):
            parent._sync_v_scrollbar()

    def load_clips(self, clips: List[TimelineClip], duration_s: float = 60.0):
        self.clips      = clips
        self.duration_s = duration_s
        self._update_min_height()
        self.update()

    def set_playhead(self, s: float):
        self.playhead_s = s
        s_start = self.scroll_s
        s_end   = self.scroll_s + (self.width() - LABEL_W) / max(1, self.px_per_s)
        if s > s_end - 2 or s < s_start:
            self.scroll_s = max(0.0, s - (s_end - s_start) * 0.1)
        self.update()

    def zoom_to_fit(self):
        if self.duration_s > 0:
            available = max(1, self.width() - LABEL_W)
            self.px_per_s = available / self.duration_s * 0.95
            self.scroll_s = 0.0
            self.update()

    def get_selected_clip(self) -> TimelineClip | None:
        for clip in self.clips:
            if clip.is_selected:
                return clip
        return None


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

        # Legend
        for color, label in [
            ("#3D2454", "Video"), ("#6C3BE4", "Zoom/FX"),
            ("#1A4731", "Sub CA"), ("#1A3A5C", "Sub ES"), ("#2C1A5C", "Sub EN"),
        ]:
            dot = QLabel(f"● {label}")
            dot.setStyleSheet(
                f"color:{color}; font-size:9px; background:transparent; filter: brightness(2);"
            )
            dot.setStyleSheet(
                f"color: {QColor(color).lighter(180).name()}; "
                "font-size:9px; background:transparent;"
            )
            h_lo.addWidget(dot)
            h_lo.addSpacing(2)

        h_lo.addSpacing(8)

        def ctrl(text, slot, w=32):
            b = QPushButton(text)
            b.setFixedSize(w, 22)
            b.clicked.connect(slot)
            return b

        h_lo.addWidget(ctrl("⊟", self._zoom_out))
        h_lo.addWidget(ctrl("⊞", self._zoom_in))
        h_lo.addWidget(ctrl("Fit", self._fit, 38))
        lo.addWidget(header)

        # Canvas + vertical scrollbar in a row
        canvas_row = QWidget()
        canvas_row.setStyleSheet("background:transparent;")
        cr_lo = QHBoxLayout(canvas_row)
        cr_lo.setContentsMargins(0, 0, 0, 0)
        cr_lo.setSpacing(0)

        self.canvas = TimelineCanvas(self)
        self.canvas.seek_requested.connect(self.seek_requested)
        self.canvas.clip_selected.connect(self.clip_selected)
        cr_lo.addWidget(self.canvas, stretch=1)

        # Vertical scrollbar (scrolls through tracks)
        self.v_scrollbar = QScrollBar(Qt.Orientation.Vertical)
        self.v_scrollbar.setRange(0, 1000)   # always active
        self.v_scrollbar.setValue(0)
        self.v_scrollbar.setFixedWidth(10)
        self.v_scrollbar.setStyleSheet(
            "QScrollBar:vertical { background:#1A1A1A; width:10px; border-radius:4px; }"
            "QScrollBar::handle:vertical { background:#444; border-radius:4px; min-height:20px; }"
            "QScrollBar::handle:vertical:hover { background:#666; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }"
        )
        self.v_scrollbar.valueChanged.connect(self._on_v_scrollbar)
        cr_lo.addWidget(self.v_scrollbar)

        lo.addWidget(canvas_row, stretch=1)

        # Horizontal scrollbar
        self.scrollbar = QScrollBar(Qt.Orientation.Horizontal)
        self.scrollbar.setRange(0, 10000)
        self.scrollbar.setValue(0)
        self.scrollbar.setFixedHeight(10)
        self.scrollbar.valueChanged.connect(self._on_scrollbar)
        lo.addWidget(self.scrollbar)

    # ── Zoom controls ─────────────────────────────────────────────────────────

    def _on_v_scrollbar(self, value: int):
        """Called when user drags vertical scrollbar."""
        visible_h = max(1, self.canvas.height() - RULER_H)
        total_h   = self.canvas._total_tracks_height()
        max_scroll = max(0, total_h - visible_h)
        self.canvas.scroll_y = int(value / 1000 * max_scroll)
        self.canvas.update()

    def _sync_v_scrollbar(self):
        """Update scrollbar position to match canvas scroll_y."""
        visible_h  = max(1, self.canvas.height() - RULER_H)
        total_h    = self.canvas._total_tracks_height()
        max_scroll = max(1, total_h - visible_h)
        val = int(self.canvas.scroll_y / max_scroll * 1000)
        self.v_scrollbar.blockSignals(True)
        self.v_scrollbar.setValue(max(0, min(1000, val)))
        self.v_scrollbar.blockSignals(False)

    def _on_scrollbar(self, value: int):
        if self.canvas.duration_s > 0:
            visible = (self.canvas.width() - LABEL_W) / max(1, self.canvas.px_per_s)
            max_scroll = max(0, self.canvas.duration_s - visible)
            self.canvas.scroll_s = value / 10000 * max_scroll
            self.canvas.update()

    def _sync_scrollbar(self):
        if self.canvas.duration_s > 0:
            visible = (self.canvas.width() - LABEL_W) / max(1, self.canvas.px_per_s)
            max_scroll = max(0.001, self.canvas.duration_s - visible)
            val = int(self.canvas.scroll_s / max_scroll * 10000)
            self.scrollbar.blockSignals(True)
            self.scrollbar.setValue(max(0, min(10000, val)))
            self.scrollbar.blockSignals(False)

    def _zoom_in(self):
        self.canvas.px_per_s = min(600.0, self.canvas.px_per_s * 1.3)
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
        """Load from script segments (before pipeline runs)."""
        from core.timeline_editor import (
            _t2s, TRACK_COLORS, TRACK_MUSIC, TRACK_EN,
        )
        clips: list[TimelineClip] = []
        segments = script.get("segments", [])

        for seg in segments:
            seg_id  = seg.get("id", "")
            start   = _t2s(seg.get("time_start", "0:00"))
            end     = _t2s(seg.get("time_end",   "0:05"))
            is_dup  = seg.get("is_duplicate", False)
            label   = (seg.get("content", "")[:28]
                       or f"Seg {seg.get('order', 0) + 1}")

            clips.append(TimelineClip(
                id=seg_id, track=TRACK_VIDEO,
                start_s=start, end_s=end,
                label=label, color="#3D2454",
                is_duplicate=is_dup, segment_data=seg,
            ))
            if seg.get("music", {}).get("enabled"):
                clips.append(TimelineClip(
                    id=f"{seg_id}_music", track=TRACK_MUSIC,
                    start_s=start, end_s=end,
                    label="♪ " + seg["music"].get("file_path", "")[-18:],
                    color=TRACK_COLORS[TRACK_MUSIC],
                    is_resizable=False, segment_data=seg,
                ))

        dur = max(video_duration_s, max((c.end_s for c in clips), default=10.0))
        self.canvas.load_clips(clips, dur)
        self.canvas.zoom_to_fit()
        self._sync_v_scrollbar()

    def load_from_pipeline_output(self, outputs: dict, duration_s: float = 60.0):
        """Load full pipeline output: segments + all subtitle tracks."""
        from core.timeline_editor import load_pipeline_output
        clips = load_pipeline_output(outputs, duration_s)
        dur   = max(duration_s, max((c.end_s for c in clips), default=10.0))
        self.canvas.load_clips(clips, dur)
        self.canvas.zoom_to_fit()
        self._sync_v_scrollbar()

    def clear(self):
        self.canvas.clips = []
        self.canvas.update()
