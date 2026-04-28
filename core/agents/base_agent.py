import json
import time
import logging
import re
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import types as genai_types


@dataclass
class AgentResult:
    agent_name: str
    success: bool
    output: Any
    confidence: float = 1.0
    tokens_used: int = 0
    duration_ms: int = 0
    error: str | None = None


# Models available — ordered by preference when quota fails
FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-001",
]


class BaseVideoAgent:
    MODEL: str = "gemini-2.5-flash"
    SYSTEM_PROMPT: str = ""
    MAX_RETRIES: int = 3

    def __init__(self, api_key: str, memory=None):
        self.api_key = api_key
        self.memory = memory
        self._logger = logging.getLogger(self.__class__.__name__)
        self._client = genai.Client(api_key=api_key)

    def run(self, input_data: dict) -> AgentResult:
        raise NotImplementedError(f"{self.__class__.__name__} must implement run()")

    # ── Core call methods ─────────────────────────────────────────────────────

    def _call(self, prompt: str, files: list = None, json_mode: bool = False,
              model: str | None = None) -> str:
        model_name = model or self.MODEL
        contents = []
        if files:
            contents.extend(files)
        contents.append(prompt)

        config_kwargs = {}
        if self.SYSTEM_PROMPT:
            config_kwargs["system_instruction"] = self.SYSTEM_PROMPT
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"

        cfg = genai_types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        def attempt():
            kwargs = {"model": model_name, "contents": contents}
            if cfg:
                kwargs["config"] = cfg
            response = self._client.models.generate_content(**kwargs)
            return response.text

        return self._retry_with_fallback(attempt, prompt=prompt, files=files,
                                         json_mode=json_mode, preferred_model=model_name)

    def _call_json(self, prompt: str, files: list = None, model: str | None = None) -> dict:
        raw = self._call(prompt, files=files, json_mode=True, model=model)
        return self._parse_json(raw)

    def _call_thinking(self, prompt: str) -> str:
        """Use a more capable model for reasoning-heavy tasks."""
        thinking_model = "gemini-2.5-pro"
        return self._call(prompt, model=thinking_model)

    def _upload_audio(self, audio_path: str) -> Any:
        """Upload audio file using the Files API."""
        return self._client.files.upload(
            file=audio_path,
            config=genai_types.UploadFileConfig(mime_type="audio/wav")
        )

    def _delete_file(self, file_obj: Any):
        try:
            self._client.files.delete(name=file_obj.name)
        except Exception:
            pass

    # ── Retry logic ───────────────────────────────────────────────────────────

    def _retry_with_fallback(self, attempt_fn, prompt="", files=None,
                              json_mode=False, preferred_model: str | None = None) -> str:
        models_to_try = [preferred_model or self.MODEL] + [
            m for m in FALLBACK_MODELS if m != (preferred_model or self.MODEL)
        ]
        seen = set()
        last_exc = None

        for model_name in models_to_try:
            if model_name in seen:
                continue
            seen.add(model_name)

            for attempt in range(self.MAX_RETRIES):
                try:
                    if model_name == (preferred_model or self.MODEL) and attempt == 0:
                        return attempt_fn()
                    else:
                        # Rebuild call for fallback model
                        return self._direct_call(
                            model_name, prompt, files, json_mode
                        )
                except Exception as exc:
                    last_exc = exc
                    msg = str(exc)
                    if "429" in msg or "quota" in msg.lower():
                        delay = self._extract_retry_delay(exc) or (2 ** attempt)
                        self._logger.warning(
                            "Quota on %s (attempt %d). Wait %ds…",
                            model_name, attempt + 1, int(delay)
                        )
                        time.sleep(min(delay, 30))
                        if attempt == self.MAX_RETRIES - 1:
                            # Move to next model
                            self._logger.warning("Switching from %s to next model", model_name)
                            break
                    elif "404" in msg or "not found" in msg.lower():
                        self._logger.warning("Model %s not available, trying next", model_name)
                        break
                    else:
                        # Non-quota/404 error — retry same model
                        if attempt < self.MAX_RETRIES - 1:
                            time.sleep(2 ** attempt)
                        else:
                            raise

        raise RuntimeError(
            f"All models failed. Last error: {last_exc}"
        )

    def _direct_call(self, model_name: str, prompt: str,
                     files: list | None, json_mode: bool) -> str:
        contents = []
        if files:
            contents.extend(files)
        contents.append(prompt)

        config_kwargs = {}
        if self.SYSTEM_PROMPT:
            config_kwargs["system_instruction"] = self.SYSTEM_PROMPT
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"

        kwargs = {"model": model_name, "contents": contents}
        if config_kwargs:
            kwargs["config"] = genai_types.GenerateContentConfig(**config_kwargs)

        response = self._client.models.generate_content(**kwargs)
        return response.text

    def _retry(self, fn, max_retries: int | None = None):
        retries = max_retries if max_retries is not None else self.MAX_RETRIES
        last_exc = None
        for attempt in range(retries):
            try:
                return fn()
            except Exception as exc:
                last_exc = exc
                if attempt < retries - 1:
                    wait = self._extract_retry_delay(exc) or (2 ** attempt)
                    self._logger.warning("Attempt %d/%d failed. Retry in %ds",
                                         attempt + 1, retries, int(wait))
                    time.sleep(wait)
        raise last_exc

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _parse_json(self, response: str) -> dict:
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            inner, in_block = [], False
            for line in lines:
                if line.startswith("```"):
                    in_block = not in_block
                    continue
                inner.append(line)
            text = "\n".join(inner).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            raise ValueError(f"Cannot parse JSON: {text[:300]}")

    @staticmethod
    def _extract_retry_delay(exc: Exception) -> float | None:
        msg = str(exc)
        m = re.search(r'seconds:\s*(\d+)', msg)
        if m:
            return float(m.group(1)) + 2
        m = re.search(r'retry in ([\d.]+)', msg, re.IGNORECASE)
        if m:
            return float(m.group(1)) + 2
        return None

    def _make_result(self, output, duration_ms: int = 0,
                     confidence: float = 1.0) -> AgentResult:
        return AgentResult(
            agent_name=self.__class__.__name__,
            success=True,
            output=output,
            confidence=confidence,
            duration_ms=duration_ms,
        )

    def _make_error(self, error: str) -> AgentResult:
        self._logger.error("Agent error: %s", error)
        return AgentResult(
            agent_name=self.__class__.__name__,
            success=False,
            output=None,
            error=error,
        )
