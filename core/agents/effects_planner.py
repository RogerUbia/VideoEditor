import json
import time
from .base_agent import BaseVideoAgent, AgentResult

VALID_EFFECTS = {"none", "zoom_in", "zoom_out", "shake", "blur", "vignette"}
VALID_TRANSITIONS = {"none", "fade", "dissolve", "slide_up", "wipe_left", "wipe_right", "cut"}


class EffectsPlannerAgent(BaseVideoAgent):
    MODEL = "gemini-2.5-flash"
    SYSTEM_PROMPT = (
        "You are an expert video editor. "
        "Suggest appropriate visual effects and transitions for video segments. "
        "Consider content emotion and pacing. Return JSON only."
    )

    def run(self, input_data: dict) -> AgentResult:
        script = input_data.get("script", {})
        segments = script.get("segments", [])

        if not segments:
            return self._make_result(script, 0)

        seg_summary = [
            {
                "id": s.get("id"),
                "content": s.get("content", "")[:120],
                "message": s.get("message", ""),
                "order": s.get("order", i),
            }
            for i, s in enumerate(segments)
        ]

        prompt = f"""Suggest visual effects for these video segments to enhance engagement.

SEGMENTS:
{json.dumps(seg_summary, ensure_ascii=False)}

For each segment suggest effects appropriate to the content.
- Use zoom_in for close-up emphasis, zoom_out for reveal/context
- Use shake sparingly for emphasis
- Use fade transitions for smooth flow, cut for sharp pacing

Return JSON array:
[
  {{
    "id": "segment_id",
    "video_effect": {{"type": "none|zoom_in|zoom_out|shake", "intensity": 1.0}},
    "zoom": {{"enabled": false, "factor": 1.0}},
    "transition_in": {{"type": "none|fade|dissolve|slide_up", "duration_s": 0.5}},
    "transition_out": {{"type": "none|fade", "duration_s": 0.5}}
  }}
]"""

        try:
            start = time.perf_counter()
            result = self._call_json(prompt)
            dur = int((time.perf_counter() - start) * 1000)

            if isinstance(result, list):
                result_map = {r["id"]: r for r in result if "id" in r}
                for seg in segments:
                    sid = seg.get("id")
                    if sid in result_map:
                        updates = result_map[sid]
                        # Validate and apply effect
                        ve = updates.get("video_effect", {})
                        if ve.get("type") in VALID_EFFECTS:
                            seg["video_effect"] = ve
                        zoom = updates.get("zoom", {})
                        if isinstance(zoom.get("factor"), (int, float)):
                            zoom["factor"] = max(1.0, min(2.0, float(zoom["factor"])))
                            seg["zoom"] = zoom
                        ti = updates.get("transition_in", {})
                        if ti.get("type") in VALID_TRANSITIONS:
                            seg["transition_in"] = ti
                        to_ = updates.get("transition_out", {})
                        if to_.get("type") in VALID_TRANSITIONS:
                            seg["transition_out"] = to_

            return self._make_result(script, dur)
        except Exception as exc:
            return self._make_result(script, 0)
