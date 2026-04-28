import time
from .base_agent import BaseVideoAgent, AgentResult

LANG_NAMES = {
    "ca": "Catalan",
    "es": "Spanish",
    "en": "English",
    "fr": "French",
}


class TextCorrectorAgent(BaseVideoAgent):
    MODEL = "gemini-2.0-flash-lite"
    SYSTEM_PROMPT = (
        "You are a professional proofreader. "
        "Correct text spelling, grammar and punctuation. "
        "Return ONLY the corrected text, no explanations."
    )

    def run(self, input_data: dict) -> AgentResult:
        text = input_data.get("text", "").strip()
        language = input_data.get("language", "ca")

        if not text:
            return self._make_result("", 0)

        lang_name = LANG_NAMES.get(language, language)
        prompt = (
            f"Correct the spelling, grammar and punctuation of this {lang_name} text.\n"
            "Preserve the meaning and tone exactly. Return ONLY the corrected text.\n\n"
            f"TEXT:\n{text}"
        )

        try:
            start = time.perf_counter()
            result = self._call(prompt)
            dur = int((time.perf_counter() - start) * 1000)
            return self._make_result(result.strip(), dur)
        except Exception as exc:
            return self._make_error(str(exc))
