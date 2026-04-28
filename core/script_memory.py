import json
import uuid
from datetime import datetime
from pathlib import Path


class ScriptMemory:
    """Persistent JSON-based storage for scripts and chat history."""

    def __init__(self, scripts_dir: str):
        self.scripts_dir = Path(scripts_dir)
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.scripts_dir / "memory_index.json"
        self._index = self._load_index()

    # ── Index management ─────────────────────────────────────────────────────

    def _load_index(self) -> dict:
        if self._index_path.exists():
            try:
                return json.loads(self._index_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"entries": []}

    def _save_index(self):
        self._index_path.write_text(
            json.dumps(self._index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── Script persistence ───────────────────────────────────────────────────

    def save_script(self, script_dict: dict, project_name: str) -> str:
        project_dir = self.scripts_dir / project_name
        project_dir.mkdir(exist_ok=True)

        existing = sorted(project_dir.glob("script_v*.json"))
        version = len(existing) + 1

        script_dict = {
            **script_dict,
            "modified_at": datetime.now().isoformat(),
        }
        if "created_at" not in script_dict:
            script_dict["created_at"] = script_dict["modified_at"]

        file_path = project_dir / f"script_v{version:03d}.json"
        file_path.write_text(
            json.dumps(script_dict, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        summary = self.generate_summary(script_dict)
        entry = {
            "id": str(uuid.uuid4()),
            "project_name": project_name,
            "created_at": script_dict["created_at"],
            "modified_at": script_dict["modified_at"],
            "version_count": version,
            "latest_file": str(file_path),
            "summary": summary,
            "segment_count": len(script_dict.get("segments", [])),
        }

        for i, e in enumerate(self._index["entries"]):
            if e["project_name"] == project_name:
                self._index["entries"][i] = entry
                break
        else:
            self._index["entries"].append(entry)

        self._save_index()
        return str(file_path)

    def load_latest(self, project_name: str) -> dict | None:
        for entry in self._index["entries"]:
            if entry["project_name"] == project_name:
                path = Path(entry["latest_file"])
                if path.exists():
                    return json.loads(path.read_text(encoding="utf-8"))
        return None

    def list_projects(self) -> list[dict]:
        return sorted(
            self._index["entries"],
            key=lambda e: e.get("modified_at", ""),
            reverse=True,
        )

    # ── Chat history ──────────────────────────────────────────────────────────

    def save_chat_message(self, project_name: str, role: str, content: str):
        project_dir = self.scripts_dir / project_name
        project_dir.mkdir(exist_ok=True)
        log_path = project_dir / "session_log.json"

        if log_path.exists():
            log = json.loads(log_path.read_text(encoding="utf-8"))
        else:
            log = {
                "project_name": project_name,
                "session_id": str(uuid.uuid4()),
                "messages": [],
            }

        log["messages"].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        log_path.write_text(
            json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get_chat_history(self, project_name: str, last_n: int = 20) -> list[dict]:
        log_path = self.scripts_dir / project_name / "session_log.json"
        if not log_path.exists():
            return []
        log = json.loads(log_path.read_text(encoding="utf-8"))
        return log.get("messages", [])[-last_n:]

    # ── Context for AI agent ─────────────────────────────────────────────────

    def get_recent_summaries(self, count: int = 3) -> list[str]:
        entries = sorted(
            self._index["entries"],
            key=lambda e: e.get("modified_at", ""),
            reverse=True,
        )
        return [e["summary"] for e in entries[:count]]

    def build_context_prompt(self, project_name: str) -> str:
        summaries = self.get_recent_summaries(3)
        history = self.get_chat_history(project_name, 10)

        parts = []
        if summaries:
            parts.append("RECENT PROJECTS:\n" + "\n".join(f"- {s}" for s in summaries))
        if history:
            conv = "\n".join(
                f"{m['role'].upper()}: {m['content'][:200]}" for m in history
            )
            parts.append(f"CURRENT SESSION CONTEXT:\n{conv}")
        return "\n\n".join(parts)

    # ── Summary ──────────────────────────────────────────────────────────────

    @staticmethod
    def generate_summary(script_dict: dict) -> str:
        segs = script_dict.get("segments", [])
        n = len(segs)
        effects: set[str] = set()
        for s in segs:
            vtype = s.get("video_effect", {}).get("type", "none")
            if vtype != "none":
                effects.add(vtype)
            if s.get("pip", {}).get("enabled"):
                effects.add("pip")
            if s.get("text_overlay", {}).get("enabled"):
                effects.add("text")
        platform = (
            script_dict.get("global_settings", {}).get("target_platform", "?")
        )
        fx = f" [{', '.join(sorted(effects))}]" if effects else ""
        name = script_dict.get("project_name", "Unnamed")
        return f"'{name}' — {n} segments, {platform}{fx}"
