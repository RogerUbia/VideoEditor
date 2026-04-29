import os
import time
import subprocess
from .base_agent import BaseVideoAgent, AgentResult, WORKING_MODELS

LANG_NAMES = {
    "ca": "ca", "es": "es", "en": "en",
    "fr": "fr", "de": "de", "it": "it", "pt": "pt",
}

GROQ_AUDIO_LIMIT_BYTES = 24 * 1024 * 1024  # 24 MB Groq limit


class TranscriptionAgent(BaseVideoAgent):
    MODEL = "gemini-2.5-flash"
    SYSTEM_PROMPT = "You are an expert transcriptionist. Return only the spoken text."

    def run(self, input_data: dict) -> AgentResult:
        audio_path = input_data.get("audio_path", "")
        language   = input_data.get("language", "ca")

        if not audio_path or not os.path.exists(audio_path):
            return self._make_error(f"Audio file not found: {audio_path}")

        start = time.perf_counter()

        # 1. Try Groq Whisper (fast, generous free limits)
        groq_key = os.environ.get("GROQ_API_KEY", "")
        if groq_key:
            try:
                transcript = self._transcribe_groq(audio_path, language, groq_key)
                dur = int((time.perf_counter() - start) * 1000)
                self._logger.info("Groq Whisper transcription OK (%d chars)", len(transcript))
                return self._make_result(transcript.strip(), dur)
            except Exception as exc:
                self._logger.warning("Groq transcription failed: %s — trying Gemini", exc)

        # 2. Fallback: Gemini audio understanding
        audio_file = None
        try:
            audio_file = self._upload_audio(audio_path)
            lang_name = {
                "ca": "Catalan", "es": "Spanish", "en": "English",
                "fr": "French", "de": "German",
            }.get(language, language)
            prompt = (
                f"Transcribe this audio accurately in {lang_name}. "
                "Return ONLY the spoken text, no timestamps, no labels."
            )
            last_error = ""
            for model_name in WORKING_MODELS:
                try:
                    result = self._direct_call(model_name, prompt, [audio_file], False)
                    dur = int((time.perf_counter() - start) * 1000)
                    return self._make_result(result.strip(), dur)
                except Exception as exc:
                    last_error = str(exc)
                    if self._is_quota_exhausted(exc):
                        self._logger.warning("Gemini %s quota exhausted", model_name)
                        continue
                    raise
            return self._make_error(f"All models failed: {last_error}")
        except Exception as exc:
            return self._make_error(str(exc))
        finally:
            if audio_file:
                self._delete_file(audio_file)

    # ── Groq Whisper ──────────────────────────────────────────────────────────

    def _transcribe_groq(self, audio_path: str, language: str, api_key: str) -> str:
        from groq import Groq

        # Convert to MP3 if WAV is too big
        file_to_send = audio_path
        if os.path.getsize(audio_path) > GROQ_AUDIO_LIMIT_BYTES:
            file_to_send = audio_path.replace(".wav", "_compressed.mp3")
            self._convert_to_mp3(audio_path, file_to_send)

        client = Groq(api_key=api_key)
        with open(file_to_send, "rb") as f:
            response = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=f,
                language=LANG_NAMES.get(language, language),
                response_format="text",
            )

        # Cleanup compressed file if created
        if file_to_send != audio_path and os.path.exists(file_to_send):
            os.remove(file_to_send)

        return response if isinstance(response, str) else response.text

    @staticmethod
    def _convert_to_mp3(input_path: str, output_path: str):
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_path,
             "-ar", "16000", "-ac", "1", "-b:a", "64k", output_path],
            capture_output=True, check=True,
        )
