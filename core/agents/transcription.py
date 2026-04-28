import os
import time
from .base_agent import BaseVideoAgent, AgentResult, FALLBACK_MODELS

LANG_NAMES = {
    "ca": "Catalan",
    "es": "Spanish",
    "en": "English",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
}


class TranscriptionAgent(BaseVideoAgent):
    MODEL = "gemini-2.5-flash"
    SYSTEM_PROMPT = (
        "You are an expert transcriptionist. "
        "Transcribe audio accurately. Return only the spoken text."
    )

    def run(self, input_data: dict) -> AgentResult:
        audio_path = input_data.get("audio_path", "")
        language   = input_data.get("language", "ca")

        if not audio_path or not os.path.exists(audio_path):
            return self._make_error(f"Audio file not found: {audio_path}")

        lang_name = LANG_NAMES.get(language, language)
        prompt = (
            f"Transcribe this audio accurately in {lang_name}. "
            "Return ONLY the spoken text. No timestamps, no speaker labels, "
            "no formatting. Preserve natural sentence structure with periods."
        )

        # Upload audio once, reuse across model attempts
        audio_file = None
        try:
            audio_file = self._upload_audio(audio_path)
            start = time.perf_counter()

            # Try each model until one works
            last_error = ""
            for model_name in FALLBACK_MODELS:
                try:
                    self._logger.info("Transcribing with model: %s", model_name)
                    result = self._direct_call(
                        model_name, prompt, [audio_file], json_mode=False
                    )
                    dur = int((time.perf_counter() - start) * 1000)
                    return self._make_result(result.strip(), dur)
                except Exception as exc:
                    last_error = str(exc)
                    if "429" in last_error or "quota" in last_error.lower():
                        delay = self._extract_retry_delay(exc) or 5
                        self._logger.warning(
                            "Quota on %s. Trying next model in %ds…",
                            model_name, int(min(delay, 15))
                        )
                        time.sleep(min(delay, 15))
                        continue
                    elif "404" in last_error or "not found" in last_error.lower():
                        self._logger.warning("Model %s not available", model_name)
                        continue
                    else:
                        return self._make_error(last_error)

            return self._make_error(
                f"All models failed for transcription. Last: {last_error}"
            )
        except Exception as exc:
            return self._make_error(str(exc))
        finally:
            if audio_file:
                self._delete_file(audio_file)
