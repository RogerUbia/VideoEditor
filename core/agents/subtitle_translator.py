import time
from .base_agent import BaseVideoAgent, AgentResult

LANG_NAMES = {
    "ca": "Catalan",
    "es": "Spanish (Castilian)",
    "en": "English",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
}

MAX_CHUNK_ENTRIES = 50


class SubtitleTranslatorAgent(BaseVideoAgent):
    MODEL = "gemini-2.0-flash-lite"
    SYSTEM_PROMPT = (
        "You are a professional subtitle translator. "
        "Translate SRT files accurately while preserving all timing codes exactly. "
        "Return only the translated SRT content."
    )

    def run(self, input_data: dict) -> AgentResult:
        srt_content = input_data.get("srt_content", "").strip()
        source_lang = input_data.get("source_lang", "ca")
        target_lang = input_data.get("target_lang", "en")

        if not srt_content:
            return self._make_result("", 0)

        src_name = LANG_NAMES.get(source_lang, source_lang)
        tgt_name = LANG_NAMES.get(target_lang, target_lang)

        try:
            start = time.perf_counter()

            blocks = srt_content.strip().split("\n\n")
            # Process in chunks to stay within token limits
            chunks = [
                blocks[i:i + MAX_CHUNK_ENTRIES]
                for i in range(0, len(blocks), MAX_CHUNK_ENTRIES)
            ]

            translated_chunks = []
            for chunk in chunks:
                chunk_text = "\n\n".join(chunk)
                translated = self._translate_chunk(chunk_text, src_name, tgt_name)
                translated_chunks.append(translated)

            result = "\n\n".join(translated_chunks)
            dur = int((time.perf_counter() - start) * 1000)
            return self._make_result(result.strip(), dur)
        except Exception as exc:
            return self._make_error(str(exc))

    def _translate_chunk(self, chunk: str, src_name: str, tgt_name: str) -> str:
        prompt = (
            f"Translate this SRT subtitle content from {src_name} to {tgt_name}.\n"
            "CRITICAL RULES:\n"
            "1. Preserve ALL index numbers exactly\n"
            "2. Preserve ALL timing codes exactly (HH:MM:SS,mmm --> HH:MM:SS,mmm)\n"
            "3. Only translate the text lines\n"
            "4. Return ONLY the translated SRT content, nothing else\n\n"
            f"SRT CONTENT:\n{chunk}"
        )
        return self._call(prompt)
