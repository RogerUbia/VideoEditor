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

        # 1. Try Groq Whisper with timestamps, fallback to plain text if needed
        groq_key = os.environ.get("GROQ_API_KEY", "")
        if groq_key:
            try:
                text, timed_segments = self._transcribe_groq_timed(
                    audio_path, language, groq_key
                )
                dur = int((time.perf_counter() - start) * 1000)
                self._logger.info(
                    "Groq Whisper OK: %d chars, %d timed segments",
                    len(text), len(timed_segments)
                )
                return self._make_result(
                    {"text": text, "timed_segments": timed_segments}, dur
                )
            except Exception as exc:
                self._logger.warning("Groq verbose_json failed (%s) — trying plain text", exc)
                try:
                    text = self._transcribe_groq_plain(audio_path, language, groq_key)
                    dur  = int((time.perf_counter() - start) * 1000)
                    self._logger.info("Groq plain text OK: %d chars", len(text))
                    return self._make_result({"text": text, "timed_segments": []}, dur)
                except Exception as exc2:
                    self._logger.warning("Groq plain also failed: %s — trying Gemini", exc2)

        # 2. Fallback: Gemini (no timestamps)
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
                    return self._make_result(
                        {"text": result.strip(), "timed_segments": []}, dur
                    )
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

    def _transcribe_groq_plain(self, audio_path: str, language: str, api_key: str) -> str:
        from groq import Groq
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
        if file_to_send != audio_path and os.path.exists(file_to_send):
            os.remove(file_to_send)
        return response if isinstance(response, str) else response.text

    # ── Groq Whisper with timestamps ──────────────────────────────────────────

    def _transcribe_groq_timed(
        self, audio_path: str, language: str, api_key: str
    ) -> tuple[str, list[dict]]:
        """
        Returns (full_text, timed_segments) where each segment is:
        {"start": float, "end": float, "text": str}
        """
        from groq import Groq

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
                response_format="verbose_json",  # gives us segment timestamps
            )

        if file_to_send != audio_path and os.path.exists(file_to_send):
            os.remove(file_to_send)

        full_text = response.text if hasattr(response, "text") else ""
        timed_segments = []
        if hasattr(response, "segments") and response.segments:
            for seg in response.segments:
                timed_segments.append({
                    "start": round(float(seg.start), 3),
                    "end":   round(float(seg.end),   3),
                    "text":  seg.text.strip(),
                })

        return full_text.strip(), timed_segments

    @staticmethod
    def _convert_to_mp3(input_path: str, output_path: str):
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_path,
             "-ar", "16000", "-ac", "1", "-b:a", "64k", output_path],
            capture_output=True, check=True,
        )
