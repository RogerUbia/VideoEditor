import json
import time
from .base_agent import BaseVideoAgent, AgentResult


class QualityControlAgent(BaseVideoAgent):
    MODEL = "gemini-2.5-flash"
    SYSTEM_PROMPT = (
        "You are a video production quality controller. "
        "Review pipeline outputs and identify issues. "
        "Return structured JSON assessment."
    )

    def run(self, input_data: dict) -> AgentResult:
        script = input_data.get("script", {})
        validation = input_data.get("validation_report", {})
        subtitles = input_data.get("subtitles", {})
        output_video = input_data.get("output_video", "")
        platform = (
            script.get("global_settings", {}).get("target_platform", "?")
        )
        segments = script.get("segments", [])

        summary = {
            "has_output_video": bool(output_video),
            "has_subtitles_ca": bool(subtitles.get("ca")),
            "has_subtitles_es": bool(subtitles.get("es")),
            "has_subtitles_en": bool(subtitles.get("en")),
            "validation_score": validation.get("overall_match_score", 0),
            "validation_recommendation": validation.get("recommendation", "?"),
            "platform": platform,
            "segment_count": len(segments),
            "duplicate_segments": sum(
                1 for s in segments if s.get("is_duplicate", False)
            ),
        }

        prompt = f"""Review this video production result and provide quality assessment.

PIPELINE SUMMARY:
{json.dumps(summary, ensure_ascii=False, indent=2)}

VALIDATION ISSUES:
{json.dumps(validation.get("missing_content", []) + validation.get("extra_content", []), ensure_ascii=False)}

Evaluate completeness, quality, and platform compliance.
For Instagram: max 3 minutes, English subtitles required.
For YouTube: .srt files required.

Return JSON:
{{
  "quality_score": 0.0-1.0,
  "issues": ["list of problems found"],
  "passed_checks": ["list of things that are correct"],
  "recommendation": "approve|review|reject",
  "notes": "1-2 sentence summary"
}}"""

        try:
            start = time.perf_counter()
            result = self._call_thinking(prompt)
            dur = int((time.perf_counter() - start) * 1000)
            parsed = self._parse_json(result)
            score = float(parsed.get("quality_score", 0.7))
            return self._make_result(parsed, dur, score)
        except Exception as exc:
            # Fallback assessment
            fallback = {
                "quality_score": 0.7 if summary["has_output_video"] else 0.3,
                "issues": [] if summary["has_output_video"] else ["Output video missing"],
                "passed_checks": ["Pipeline completed"] if summary["has_output_video"] else [],
                "recommendation": "approve" if summary["has_output_video"] else "reject",
                "notes": "Automated assessment (AI check failed).",
            }
            return self._make_result(fallback, 0, fallback["quality_score"])
