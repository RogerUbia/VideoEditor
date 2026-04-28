import json
import time
import difflib
from .base_agent import BaseVideoAgent, AgentResult


class ValidatorAgent(BaseVideoAgent):
    MODEL = "gemini-2.5-flash"
    SYSTEM_PROMPT = (
        "You are an expert content validator. "
        "Compare scripts and transcriptions carefully. "
        "Return structured JSON analysis."
    )

    def run(self, input_data: dict) -> AgentResult:
        script = input_data.get("script", {})
        transcription = input_data.get("transcription", "")

        script_text_parts = [
            s.get("content", "") for s in script.get("segments", [])
        ]
        script_text = " ".join(script_text_parts)

        # Quick local similarity score
        local_score = difflib.SequenceMatcher(
            None, script_text.lower(), transcription.lower()
        ).ratio()

        prompt = f"""Compare this video script with its transcription.

SCRIPT SEGMENTS:
{json.dumps(script_text_parts, ensure_ascii=False, indent=2)}

ACTUAL TRANSCRIPTION:
{transcription}

Identify:
1. Content in the script NOT spoken (missing)
2. Content spoken NOT in the script (extra)
3. Semantic match quality

Return JSON only:
{{
  "overall_match_score": {local_score:.2f},
  "missing_content": [],
  "extra_content": [],
  "segment_results": [],
  "recommendation": "approve|review|reject",
  "notes": "brief summary"
}}"""

        try:
            start = time.perf_counter()
            result = self._call_thinking(prompt)
            dur = int((time.perf_counter() - start) * 1000)
            parsed = self._parse_json(result)
            score = parsed.get("overall_match_score", local_score)
            return self._make_result(parsed, dur, float(score))
        except Exception as exc:
            # Fallback to local analysis only
            fallback = {
                "overall_match_score": local_score,
                "missing_content": [],
                "extra_content": [],
                "segment_results": [],
                "recommendation": "review" if local_score < 0.7 else "approve",
                "notes": f"Local similarity: {local_score:.0%}",
            }
            return self._make_result(fallback, 0, local_score)
