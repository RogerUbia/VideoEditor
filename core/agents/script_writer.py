import json
import time
import uuid
from datetime import datetime
from .base_agent import BaseVideoAgent, AgentResult

SCRIPT_SCHEMA = {
    "script_version": "1.0",
    "project_name": "string",
    "created_at": "ISO8601",
    "segments": [{
        "id": "uuid4",
        "order": 0,
        "time_start": "00:00:00.000",
        "time_end": "00:00:05.000",
        "content": "spoken text",
        "message": "editor note",
        "video_effect": {"type": "none", "intensity": 1.0},
        "zoom": {"enabled": False, "factor": 1.0, "anchor_x": 0.5, "anchor_y": 0.5},
        "transition_in": {"type": "none", "duration_s": 0.5},
        "transition_out": {"type": "none", "duration_s": 0.5},
        "pip": {"enabled": False, "source": "none", "position": "bottom_right", "size_pct": 0.25, "border_radius_px": 12, "border_color": "#FFFFFF", "border_width_px": 2},
        "music": {"enabled": False, "file_path": "", "volume_db": -12.0, "fade_in_s": 1.0, "fade_out_s": 1.0},
        "text_overlay": {"enabled": False, "text": "", "font_family": "Arial", "font_size_pt": 36, "color": "#FFFFFF", "bg_color": "#00000080", "position": "bottom_center", "bold": False, "animation": "none"},
        "notes": "",
        "transcription": "",
        "validated": False,
        "validation_score": 0.0,
        "is_duplicate": False,
        "is_best_take": True,
        "effects_ffmpeg": ""
    }],
    "global_settings": {
        "target_platform": "youtube",
        "output_resolution": "1920x1080",
        "output_fps": 30,
        "background_music_file": "",
        "background_music_volume_db": -20.0,
        "subtitle_font": "Arial",
        "subtitle_font_size": 28,
        "subtitle_color": "#FFFFFF",
        "subtitle_bg_color": "#00000080",
        "burn_subtitles_instagram": True
    }
}

SYSTEM_PROMPT_TEMPLATE = """You are VideoForge Script Agent, an expert video script writer and editor assistant.

Your role: help create and modify structured video scripts as JSON.

OUTPUT FORMAT: Always respond with valid JSON matching this schema:
{schema}

RULES:
1. All segment IDs must be unique UUID4 strings
2. Segment times must not overlap
3. time_start and time_end format: HH:MM:SS.mmm
4. video_effect.type: none|zoom_in|zoom_out|shake|blur
5. transition types: none|fade|dissolve|slide_up|wipe_left|wipe_right
6. Keep content in the same language the user writes in
7. Estimate realistic timing based on speaking speed (~130 words/minute)
8. Respond with ONLY the JSON script, no markdown, no explanations
""".format(schema=json.dumps(SCRIPT_SCHEMA, indent=2, ensure_ascii=False))


class ScriptWriterAgent(BaseVideoAgent):
    MODEL = "gemini-2.5-flash"
    SYSTEM_PROMPT = SYSTEM_PROMPT_TEMPLATE

    def run(self, input_data: dict) -> AgentResult:
        user_prompt = input_data.get("user_prompt", "")
        project_name = input_data.get("project_name", "default")
        current_script = input_data.get("current_script")

        context = ""
        if self.memory:
            context = self.memory.build_context_prompt(project_name)

        prompt = self._build_prompt(user_prompt, current_script, context, project_name)

        try:
            start = time.perf_counter()
            result_dict = self._call_json(prompt)
            dur = int((time.perf_counter() - start) * 1000)

            result_dict = self._ensure_schema(result_dict, project_name)

            if self.memory:
                self.memory.save_script(result_dict, project_name)
                self.memory.save_chat_message(project_name, "user", user_prompt)
                explanation = f"Generated script with {len(result_dict.get('segments', []))} segments"
                self.memory.save_chat_message(project_name, "assistant", explanation)

            return self._make_result(result_dict, dur)
        except Exception as exc:
            return self._make_error(str(exc))

    def _build_prompt(self, user_prompt: str, current_script: dict | None,
                      context: str, project_name: str) -> str:
        parts = []
        if context:
            parts.append(context)
        if current_script and current_script.get("segments"):
            segs_summary = json.dumps(
                [{"id": s.get("id"), "content": s.get("content", "")[:80]}
                 for s in current_script["segments"]],
                ensure_ascii=False
            )
            parts.append(f"CURRENT SCRIPT ({len(current_script['segments'])} segments):\n{segs_summary}")
        parts.append(f"PROJECT: {project_name}")
        parts.append(f"USER REQUEST: {user_prompt}")
        parts.append("Respond with the complete JSON script only.")
        return "\n\n".join(parts)

    def _ensure_schema(self, data: dict, project_name: str) -> dict:
        if "project_name" not in data:
            data["project_name"] = project_name
        if "created_at" not in data:
            data["created_at"] = datetime.now().isoformat()
        if "segments" not in data:
            data["segments"] = []
        if "global_settings" not in data:
            data["global_settings"] = SCRIPT_SCHEMA["global_settings"].copy()
        for i, seg in enumerate(data["segments"]):
            if "id" not in seg or not seg["id"]:
                seg["id"] = str(uuid.uuid4())
            if "order" not in seg:
                seg["order"] = i
            # Fill missing optional fields with defaults
            defaults = SCRIPT_SCHEMA["segments"][0]
            for key, default_val in defaults.items():
                if key not in seg:
                    seg[key] = default_val
        return data
