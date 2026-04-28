import json
import uuid
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QTextEdit, QLineEdit, QPushButton, QLabel, QMenu, QComboBox,
    QCheckBox, QFrame, QSizePolicy,
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, pyqtSlot, QSize,
)
from PyQt6.QtGui import QColor, QBrush, QFont, QTextCursor, QAction


# ── Worker: AI script generation ─────────────────────────────────────────────

class ScriptAgentWorker(QThread):
    result_ready   = pyqtSignal(dict, str)   # (script_dict, explanation)
    error_occurred = pyqtSignal(str)

    def __init__(self, api_key: str, config: dict, base_dir: str,
                 message: str, current_script: dict, project_name: str):
        super().__init__()
        self.api_key       = api_key
        self.config        = config
        self.base_dir      = base_dir
        self.message       = message
        self.current_script = current_script
        self.project_name  = project_name
        self._cancelled    = False

    def run(self):
        try:
            from core.script_memory import ScriptMemory
            from core.agents.orchestrator import AgentOrchestrator

            mem  = ScriptMemory(self.config.get("scripts_dir", "data/scripts"))
            orch = AgentOrchestrator(self.api_key, self.config, memory=mem)
            r    = orch.generate_script(
                self.message, self.project_name, self.current_script
            )
            if self._cancelled:
                return
            if r.success:
                script   = r.output if isinstance(r.output, dict) else {}
                n        = len(script.get("segments", []))
                explain  = f"Generated script with {n} segments."
                self.result_ready.emit(script, explain)
            else:
                self.error_occurred.emit(r.error or "Unknown error")
        except Exception as exc:
            if not self._cancelled:
                self.error_occurred.emit(str(exc))

    def cancel(self):
        self._cancelled = True


# ── Script table columns ──────────────────────────────────────────────────────

COL_IDX       = 0
COL_START     = 1
COL_END       = 2
COL_DUR       = 3
COL_CONTENT   = 4
COL_MESSAGE   = 5
COL_EFFECT    = 6
COL_ZOOM      = 7
COL_TRANS     = 8
COL_PIP       = 9
COL_MUSIC     = 10
COL_TEXT      = 11
COL_NOTES     = 12
COL_VALID     = 13
NUM_COLS      = 14

HEADERS = [
    "#", "Start", "End", "Dur.", "Content", "Message",
    "Effect", "Zoom", "Trans.", "PiP", "Music", "Text", "Notes", "✓",
]


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


def _dur_label(start: str, end: str) -> str:
    d = _t2s(end) - _t2s(start)
    if d < 0:
        return "—"
    m = int(d) // 60
    s = int(d) % 60
    return f"{m}:{s:02d}"


# ── Script Table Widget ───────────────────────────────────────────────────────

class ScriptTableWidget(QTableWidget):
    segment_selected = pyqtSignal(dict)   # emitted when row clicked
    script_changed   = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(0, NUM_COLS, parent)
        self._segments: list[dict] = []
        self._setup()

    def _setup(self):
        self.setHorizontalHeaderLabels(HEADERS)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.itemSelectionChanged.connect(self._on_selection_changed)
        self.itemChanged.connect(self._on_item_changed)

        # Column widths
        hh = self.horizontalHeader()
        hh.setSectionResizeMode(COL_IDX,     QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(COL_START,   QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(COL_END,     QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(COL_DUR,     QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(COL_CONTENT, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(COL_MESSAGE, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(COL_EFFECT,  QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(COL_ZOOM,    QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(COL_TRANS,   QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(COL_PIP,     QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(COL_MUSIC,   QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(COL_TEXT,    QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(COL_NOTES,   QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(COL_VALID,   QHeaderView.ResizeMode.Fixed)

        self.setColumnWidth(COL_IDX,    36)
        self.setColumnWidth(COL_START,  80)
        self.setColumnWidth(COL_END,    80)
        self.setColumnWidth(COL_DUR,    56)
        self.setColumnWidth(COL_MESSAGE, 130)
        self.setColumnWidth(COL_EFFECT,  90)
        self.setColumnWidth(COL_ZOOM,    46)
        self.setColumnWidth(COL_TRANS,   80)
        self.setColumnWidth(COL_PIP,     36)
        self.setColumnWidth(COL_MUSIC,   46)
        self.setColumnWidth(COL_TEXT,    44)
        self.setColumnWidth(COL_NOTES,   130)
        self.setColumnWidth(COL_VALID,   30)

        self.setRowHeight(0, 28)
        self.verticalHeader().setDefaultSectionSize(28)

    # ── Public load/get ───────────────────────────────────────────────────────

    def load_script(self, script: dict):
        self.blockSignals(True)
        self._segments = script.get("segments", [])
        self.setRowCount(0)
        for seg in self._segments:
            self._append_row(seg)
        self.blockSignals(False)

    def get_script(self) -> list[dict]:
        return list(self._segments)

    def get_segment(self, row: int) -> dict | None:
        if 0 <= row < len(self._segments):
            return self._segments[row]
        return None

    def update_segment(self, row: int, seg: dict):
        if 0 <= row < len(self._segments):
            self._segments[row] = seg
            self._refresh_row(row, seg)
            self.script_changed.emit()

    # ── Row management ────────────────────────────────────────────────────────

    def _append_row(self, seg: dict):
        row = self.rowCount()
        self.insertRow(row)
        self._refresh_row(row, seg)

    def _refresh_row(self, row: int, seg: dict):
        self.blockSignals(True)
        self.setRowHeight(row, 28)

        start = seg.get("time_start", "00:00:00.000")
        end   = seg.get("time_end",   "00:00:05.000")

        def cell(text: str, editable: bool = False, center: bool = False) -> QTableWidgetItem:
            item = QTableWidgetItem(text)
            if not editable:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if center:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            return item

        self.setItem(row, COL_IDX,   cell(str(row + 1), center=True))
        self.setItem(row, COL_START, cell(start, editable=True, center=True))
        self.setItem(row, COL_END,   cell(end,   editable=True, center=True))
        self.setItem(row, COL_DUR,   cell(_dur_label(start, end), center=True))

        content_item = QTableWidgetItem(seg.get("content", ""))
        self.setItem(row, COL_CONTENT, content_item)

        self.setItem(row, COL_MESSAGE, QTableWidgetItem(seg.get("message", "")))

        vfx  = seg.get("video_effect", {}).get("type", "none")
        self.setItem(row, COL_EFFECT, cell(vfx, center=True))

        zoom = "✓" if seg.get("zoom", {}).get("enabled") else ""
        self.setItem(row, COL_ZOOM, cell(zoom, center=True))

        trans = seg.get("transition_in", {}).get("type", "none")
        self.setItem(row, COL_TRANS, cell(trans, center=True))

        pip = "✓" if seg.get("pip", {}).get("enabled") else ""
        self.setItem(row, COL_PIP, cell(pip, center=True))

        mus = "♪" if seg.get("music", {}).get("enabled") else ""
        self.setItem(row, COL_MUSIC, cell(mus, center=True))

        txt = "T" if seg.get("text_overlay", {}).get("enabled") else ""
        self.setItem(row, COL_TEXT, cell(txt, center=True))

        self.setItem(row, COL_NOTES, QTableWidgetItem(seg.get("notes", "")))

        # Validation indicator
        score = seg.get("validation_score", 0)
        validated = seg.get("validated", False)
        if validated and score >= 0.8:
            valid_item = cell("✓", center=True)
            valid_item.setForeground(QBrush(QColor("#2ECC71")))
        elif seg.get("is_duplicate", False):
            valid_item = cell("⚠", center=True)
            valid_item.setForeground(QBrush(QColor("#F39C12")))
        else:
            valid_item = cell("—", center=True)
            valid_item.setForeground(QBrush(QColor("#555555")))
        self.setItem(row, COL_VALID, valid_item)

        self.blockSignals(False)

    def _renumber(self):
        for r in range(self.rowCount()):
            item = self.item(r, COL_IDX)
            if item:
                item.setText(str(r + 1))

    # ── Signals ───────────────────────────────────────────────────────────────

    def _on_selection_changed(self):
        rows = self.selectedItems()
        if rows:
            row = self.row(rows[0])
            seg = self.get_segment(row)
            if seg:
                self.segment_selected.emit(seg)

    def _on_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        col = item.column()
        if row >= len(self._segments):
            return
        seg = self._segments[row]
        if col == COL_START:
            seg["time_start"] = item.text()
            dur_item = self.item(row, COL_DUR)
            if dur_item:
                dur_item.setText(_dur_label(item.text(), seg.get("time_end", "0:05")))
        elif col == COL_END:
            seg["time_end"] = item.text()
            dur_item = self.item(row, COL_DUR)
            if dur_item:
                dur_item.setText(_dur_label(seg.get("time_start", "0:00"), item.text()))
        elif col == COL_CONTENT:
            seg["content"] = item.text()
        elif col == COL_MESSAGE:
            seg["message"] = item.text()
        elif col == COL_NOTES:
            seg["notes"] = item.text()
        self.script_changed.emit()

    # ── Context menu ──────────────────────────────────────────────────────────

    def _context_menu(self, pos):
        row = self.rowAt(pos.y())
        menu = QMenu(self)

        add_above = QAction("Insert row above", self)
        add_below = QAction("Insert row below", self)
        dup_row   = QAction("Duplicate row", self)
        del_row   = QAction("Delete row", self)

        add_above.triggered.connect(lambda: self._insert_row(row))
        add_below.triggered.connect(lambda: self._insert_row(row + 1))
        dup_row.triggered.connect(lambda: self._duplicate_row(row))
        del_row.triggered.connect(lambda: self._delete_row(row))

        menu.addAction(add_above)
        menu.addAction(add_below)
        menu.addSeparator()
        menu.addAction(dup_row)
        menu.addSeparator()
        menu.addAction(del_row)
        menu.exec(self.mapToGlobal(pos))

    def _insert_row(self, at: int):
        new_seg = {
            "id": str(uuid.uuid4()),
            "order": at,
            "time_start": "00:00:00.000",
            "time_end": "00:00:05.000",
            "content": "",
            "message": "",
            "video_effect": {"type": "none", "intensity": 1.0},
            "zoom": {"enabled": False, "factor": 1.0},
            "transition_in": {"type": "none", "duration_s": 0.5},
            "transition_out": {"type": "none", "duration_s": 0.5},
            "pip": {"enabled": False, "source": "none"},
            "music": {"enabled": False, "file_path": ""},
            "text_overlay": {"enabled": False, "text": ""},
            "notes": "",
        }
        self._segments.insert(at, new_seg)
        self.insertRow(at)
        self._refresh_row(at, new_seg)
        self._renumber()
        self.script_changed.emit()

    def _duplicate_row(self, row: int):
        if 0 <= row < len(self._segments):
            import copy
            dup = copy.deepcopy(self._segments[row])
            dup["id"] = str(uuid.uuid4())
            self._insert_row(row + 1)
            self._segments[row + 1] = dup
            self._refresh_row(row + 1, dup)

    def _delete_row(self, row: int):
        if 0 <= row < len(self._segments):
            self._segments.pop(row)
            self.removeRow(row)
            self._renumber()
            self.script_changed.emit()


# ── AI Chat Widget ────────────────────────────────────────────────────────────

class AIChatWidget(QWidget):
    script_updated = pyqtSignal(dict)    # emitted after successful AI response
    log_message    = pyqtSignal(str, str)

    def __init__(self, api_key: str, config: dict, base_dir: str, parent=None):
        super().__init__(parent)
        self.api_key       = api_key
        self.config        = config
        self.base_dir      = base_dir
        self.project_name  = "default"
        self.current_script: dict = {}
        self._worker: ScriptAgentWorker | None = None
        self._setup_ui()

    def _setup_ui(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(30)
        header.setStyleSheet(
            "background:#141414; border-top:1px solid #2D2D2D;"
            "border-bottom:1px solid #2D2D2D;"
        )
        h_lo = QHBoxLayout(header)
        h_lo.setContentsMargins(10, 0, 10, 0)
        lbl = QLabel("AI SCRIPT AGENT")
        lbl.setStyleSheet(
            "color:#6C3BE4; font-size:11px; font-weight:700;"
            "letter-spacing:1px; background:transparent;"
        )
        h_lo.addWidget(lbl)
        h_lo.addStretch()
        self._status_lbl = QLabel("Ready")
        self._status_lbl.setStyleSheet(
            "color:#555; font-size:11px; background:transparent;"
        )
        h_lo.addWidget(self._status_lbl)
        lo.addWidget(header)

        # Chat history
        self.history = QTextEdit()
        self.history.setObjectName("chat_history")
        self.history.setReadOnly(True)
        self.history.setMinimumHeight(60)
        lo.addWidget(self.history, stretch=1)

        # Input row
        input_row = QWidget()
        input_row.setFixedHeight(44)
        input_row.setStyleSheet("background:#141414; border-top:1px solid #2D2D2D;")
        ir_lo = QHBoxLayout(input_row)
        ir_lo.setContentsMargins(8, 6, 8, 6)
        ir_lo.setSpacing(6)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText(
            "Describe the video script (e.g. '3-minute tutorial about PyQt6')…"
        )
        self.input_box.returnPressed.connect(self._send)
        ir_lo.addWidget(self.input_box, stretch=1)

        self._send_btn = QPushButton("Generate")
        self._send_btn.setProperty("role", "primary")
        self._send_btn.setFixedWidth(90)
        self._send_btn.clicked.connect(self._send)
        ir_lo.addWidget(self._send_btn)

        lo.addWidget(input_row)

    def set_project(self, name: str, script: dict):
        self.project_name  = name
        self.current_script = script

    # ── Chat actions ──────────────────────────────────────────────────────────

    def _send(self):
        text = self.input_box.text().strip()
        if not text:
            return
        if self._worker and self._worker.isRunning():
            return
        if not self.api_key:
            self._append("SYSTEM", "⚠ No Gemini API key configured. Go to Properties → API.")
            return

        self.input_box.clear()
        self._append("USER", text)
        self._status_lbl.setText("Thinking…")
        self._send_btn.setEnabled(False)

        self._worker = ScriptAgentWorker(
            self.api_key, self.config, self.base_dir,
            text, self.current_script, self.project_name,
        )
        self._worker.result_ready.connect(self._on_result)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.start()

    @pyqtSlot(dict, str)
    def _on_result(self, script: dict, explanation: str):
        self._status_lbl.setText("Ready")
        self._send_btn.setEnabled(True)
        n = len(script.get("segments", []))
        self._append("AI", f"✓ {explanation} ({n} segments)")
        self.current_script = script
        self.script_updated.emit(script)

    @pyqtSlot(str)
    def _on_error(self, error: str):
        self._status_lbl.setText("Error")
        self._send_btn.setEnabled(True)
        self._append("ERROR", f"⚠ {error}")
        self.log_message.emit("ERROR", f"Script agent: {error}")

    def _append(self, role: str, text: str):
        colors = {
            "USER": "#FFFFFF",
            "AI": "#9B59B6",
            "SYSTEM": "#F39C12",
            "ERROR": "#E74C3C",
        }
        color = colors.get(role, "#CCCCCC")
        ts = datetime.now().strftime("%H:%M")
        html = (
            f'<div style="margin-bottom:2px;">'
            f'<span style="color:#555;font-size:10px;">{role} · {ts}</span><br>'
            f'<span style="color:{color};">{text}</span>'
            f'</div>'
        )
        self.history.moveCursor(QTextCursor.MoveOperation.End)
        self.history.insertHtml(html)
        self.history.moveCursor(QTextCursor.MoveOperation.End)


# ── Main Script Panel ─────────────────────────────────────────────────────────

class ScriptPanel(QWidget):
    segment_selected = pyqtSignal(dict)
    script_updated   = pyqtSignal(dict)

    def __init__(self, parent=None, api_key: str = "", config: dict = None,
                 base_dir: str = ""):
        super().__init__(parent)
        self.api_key  = api_key
        self.config   = config or {}
        self.base_dir = base_dir
        self._setup_ui()

    def _setup_ui(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

        # Header toolbar
        header = QWidget()
        header.setFixedHeight(36)
        header.setStyleSheet(
            "background:#141414; border-bottom:1px solid #2D2D2D;"
        )
        h_lo = QHBoxLayout(header)
        h_lo.setContentsMargins(8, 0, 8, 0)
        h_lo.setSpacing(4)

        title = QLabel("SCRIPT")
        title.setStyleSheet(
            "color:#888; font-size:11px; font-weight:700;"
            "letter-spacing:1px; background:transparent;"
        )
        h_lo.addWidget(title)
        h_lo.addStretch()

        def small_btn(text, slot):
            b = QPushButton(text)
            b.setFixedHeight(24)
            b.clicked.connect(slot)
            return b

        h_lo.addWidget(small_btn("+ Row", self._add_row))
        h_lo.addWidget(small_btn("Clear", self._clear))
        lo.addWidget(header)

        # Splitter: table (top) + chat (bottom)
        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.setHandleWidth(3)

        # Table
        self.table = ScriptTableWidget(self)
        self.table.segment_selected.connect(self.segment_selected)
        self.table.script_changed.connect(self._on_table_changed)
        self._splitter.addWidget(self.table)

        # Chat
        self.chat = AIChatWidget(self.api_key, self.config, self.base_dir, self)
        self.chat.script_updated.connect(self._on_script_from_ai)
        self._splitter.addWidget(self.chat)

        self._splitter.setStretchFactor(0, 2)
        self._splitter.setStretchFactor(1, 1)
        lo.addWidget(self._splitter, stretch=1)

    # ── Public API ────────────────────────────────────────────────────────────

    def load_script(self, project: dict):
        self.table.load_script(project)
        name = project.get("project_name", "default")
        self.chat.set_project(name, project)

    def get_script(self) -> dict:
        segs = self.table.get_script()
        return {"segments": segs}

    def set_project_name(self, name: str):
        script = {"segments": self.table.get_script()}
        self.chat.set_project(name, script)

    # ── Slots ─────────────────────────────────────────────────────────────────

    @pyqtSlot(dict)
    def _on_script_from_ai(self, script: dict):
        self.table.load_script(script)
        self.chat.current_script = script
        self.script_updated.emit(script)

    def _on_table_changed(self):
        script = {"segments": self.table.get_script()}
        self.chat.current_script = script
        self.script_updated.emit(script)

    def _add_row(self):
        self.table._insert_row(self.table.rowCount())

    def _clear(self):
        self.table._segments.clear()
        self.table.setRowCount(0)
        self.script_updated.emit({"segments": []})
