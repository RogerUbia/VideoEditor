import json
import time
from .base_agent import BaseVideoAgent, AgentResult


class DuplicateDetectorAgent(BaseVideoAgent):
    MODEL = "gemini-2.0-flash-lite"  # lightweight task
    SYSTEM_PROMPT = (
        "You are a video take analyzer. "
        "Identify duplicate video takes and determine the best one. "
        "Return structured JSON only."
    )

    def run(self, input_data: dict) -> AgentResult:
        segments = input_data.get("segments", [])
        if len(segments) <= 1:
            if segments:
                segments[0]["is_duplicate"] = False
                segments[0]["is_best_take"] = True
            return self._make_result(segments, 0)

        seg_summary = [
            {
                "id": s.get("id"),
                "order": s.get("order", i),
                "content": s.get("content", "")[:100],
                "transcription": s.get("transcription", "")[:100],
            }
            for i, s in enumerate(segments)
        ]

        prompt = f"""Analyze these video segments. Find duplicate takes (same or similar content spoken multiple times).
Mark the BEST take of each duplicate group (most complete, fewest errors).

SEGMENTS:
{json.dumps(seg_summary, ensure_ascii=False)}

Return JSON array (one entry per segment):
[{{"id": "...", "is_duplicate": false, "is_best_take": true, "duplicate_of": null}}]

Rules:
- If a segment is unique, is_duplicate=false, is_best_take=true
- If duplicates exist, mark all but the best as is_duplicate=true, is_best_take=false
- Best take: most complete content, clearest transcription"""

        try:
            start = time.perf_counter()
            result = self._call_json(prompt)
            dur = int((time.perf_counter() - start) * 1000)

            if isinstance(result, list):
                result_map = {r["id"]: r for r in result if "id" in r}
                for seg in segments:
                    sid = seg.get("id")
                    if sid in result_map:
                        r = result_map[sid]
                        seg["is_duplicate"] = r.get("is_duplicate", False)
                        seg["is_best_take"] = r.get("is_best_take", True)
                        seg["duplicate_of"] = r.get("duplicate_of")

            return self._make_result(segments, dur)
        except Exception as exc:
            # Fallback: mark all as unique
            for seg in segments:
                seg.setdefault("is_duplicate", False)
                seg.setdefault("is_best_take", True)
            return self._make_result(segments, 0)
