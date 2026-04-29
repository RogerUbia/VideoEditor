import json
import time
import logging
import re
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import types as genai_types

# Only models confirmed working — update if quota changes
WORKING_MODELS = ["gemini-2.5-flash", "gemini-2.5-pro"]

# Global quota status cache: model -> "ok" | "exhausted" | "unknown"
_quota_status: dict[str, str] = {}


def get_quota_status() -> dict[str, str]:
    return dict(_quota_status)


def _mark_quota(model: str, status: str):
    _quota_status[model] = status


@dataclass
class AgentResult:
    agent_name: str
    success: bool
    output: Any
    confidence: float = 1.0
    tokens_used: int = 0
    duration_ms: int = 0
    error: str | None = None


class BaseVideoAgent:
    MODEL: str = "gemini-2.5-flash"
    SYSTEM_PROMPT: str = ""
    MAX_RETRIES: int = 2

    def __init__(self, api_key: str, memory=None):
        self.api_key = api_key
        self.memory = memory
        self._logger = logging.getLogger(self.__class__.__name__)
        self._client = genai.Client(api_key=api_key)

    def run(self, input_data: dict) -> AgentResult:
        raise NotImplementedError(f"{self.__class__.__name__} must implement run()")

    # ── Core call ─────────────────────────────────────────────────────────────

    def _call(self, prompt: str, files: list = None, json_mode: bool = False,
              model: str | None = None) -> str:
        model_name = model or self.MODEL
        return self._call_with_fallback(prompt, files, json_mode, model_name)

    def _call_json(self, prompt: str, files: list = None,
                   model: str | None = None) -> dict:
        raw = self._call(prompt, files=files, json_mode=True, model=model)
        return self._parse_json(raw)

    def _call_thinking(self, prompt: str) -> str:
        return self._call(prompt, model="gemini-2.5-flash")

    # ── Call with automatic model fallback ───────────────────────────────────

    def _call_with_fallback(self, prompt: str, files, json_mode: bool,
                            preferred_model: str) -> str:
        # Build ordered list: preferred first, then others
        models = [preferred_model] + [m for m in WORKING_MODELS if m != preferred_model]

        last_error = ""
        for model_name in models:
            if _quota_status.get(model_name) == "exhausted":
                self._logger.warning("Skipping %s (quota exhausted)", model_name)
                continue

            try:
                result = self._direct_call(model_name, prompt, files, json_mode)
                _mark_quota(model_name, "ok")
                return result
            except Exception as exc:
                last_error = str(exc)
                if self._is_quota_exhausted(exc):
                    _mark_quota(model_name, "exhausted")
                    self._logger.warning("Model %s daily quota exhausted", model_name)
                    continue
                elif self._is_rate_limited(exc):
                    delay = min(self._extract_retry_delay(exc) or 10, 15)
                    _mark_quota(model_name, "rate_limited")
                    self._logger.warning("Model %s rate limited — wait %ds", model_name, int(delay))
                    time.sleep(delay)
                    continue
                elif "404" in last_error or "not found" in last_error.lower():
                    _mark_quota(model_name, "not_available")
                    continue
                elif "503" in last_error or "unavailable" in last_error.lower() or "high demand" in last_error.lower():
                    _mark_quota(model_name, "unavailable")
                    self._logger.warning("Model %s unavailable (503) — trying next", model_name)
                    time.sleep(2)
                    continue
                else:
                    raise

        # All Gemini models exhausted → try Groq Llama (text only, no files)
        if not files:
            groq_key = __import__("os").environ.get("GROQ_API_KEY", "")
            if groq_key:
                try:
                    result = self._call_groq_llama(prompt, json_mode, groq_key)
                    _mark_quota("groq-llama", "ok")
                    self._logger.info("Used Groq Llama fallback")
                    return result
                except Exception as exc:
                    _mark_quota("groq-llama", "exhausted")
                    last_error = str(exc)

        raise RuntimeError(
            f"No working AI model available. Quota exhausted.\n"
            f"Check: https://ai.dev/rate-limit\nLast error: {last_error}"
        )

    def _call_groq_llama(self, prompt: str, json_mode: bool, api_key: str) -> str:
        from groq import Groq
        client = Groq(api_key=api_key)

        system = self.SYSTEM_PROMPT or "You are a helpful assistant."
        if json_mode:
            system += " Always respond with valid JSON only, no markdown."

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.7,
            max_tokens=8192,
        )
        return response.choices[0].message.content

    def _direct_call(self, model_name: str, prompt: str,
                     files: list | None, json_mode: bool) -> str:
        contents = []
        if files:
            contents.extend(files)
        contents.append(prompt)

        config_kwargs: dict = {}
        if self.SYSTEM_PROMPT:
            config_kwargs["system_instruction"] = self.SYSTEM_PROMPT
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"

        kwargs: dict = {"model": model_name, "contents": contents}
        if config_kwargs:
            kwargs["config"] = genai_types.GenerateContentConfig(**config_kwargs)

        response = self._client.models.generate_content(**kwargs)
        return response.text

    # ── Files API ─────────────────────────────────────────────────────────────

    def _upload_audio(self, audio_path: str) -> Any:
        return self._client.files.upload(
            file=audio_path,
            config=genai_types.UploadFileConfig(mime_type="audio/wav")
        )

    def _delete_file(self, file_obj: Any):
        try:
            self._client.files.delete(name=file_obj.name)
        except Exception:
            pass

    # ── Quota detection ───────────────────────────────────────────────────────

    @staticmethod
    def _is_quota_exhausted(exc: Exception) -> bool:
        msg = str(exc)
        if "429" not in msg and "RESOURCE_EXHAUSTED" not in msg:
            return False
        # Daily quota exhausted — regardless of what the limit number is
        return "PerDay" in msg or "per_day" in msg.lower()

    @staticmethod
    def _is_rate_limited(exc: Exception) -> bool:
        msg = str(exc)
        if "429" not in msg and "RESOURCE_EXHAUSTED" not in msg:
            return False
        # Rate limit (per minute) but NOT daily quota
        return "PerDay" not in msg and "per_day" not in msg.lower()

    @staticmethod
    def _extract_retry_delay(exc: Exception) -> float | None:
        msg = str(exc)
        m = re.search(r'seconds["\s:]+(\d+)', msg)
        if m:
            return float(m.group(1)) + 1
        m = re.search(r'retry in ([\d.]+)', msg, re.IGNORECASE)
        if m:
            return float(m.group(1)) + 1
        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _retry(self, fn, max_retries: int | None = None):
        retries = max_retries if max_retries is not None else self.MAX_RETRIES
        last_exc = None
        for attempt in range(retries):
            try:
                return fn()
            except Exception as exc:
                last_exc = exc
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        raise last_exc

    def _parse_json(self, response: str) -> dict:
        text = response.strip()
        if text.startswith("```"):
            inner, in_block = [], False
            for line in text.split("\n"):
                if line.startswith("```"):
                    in_block = not in_block
                    continue
                inner.append(line)
            text = "\n".join(inner).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except json.JSONDecodeError:
                    pass
            raise ValueError(f"Cannot parse JSON: {text[:300]}")

    def _make_result(self, output, duration_ms: int = 0,
                     confidence: float = 1.0) -> AgentResult:
        return AgentResult(
            agent_name=self.__class__.__name__,
            success=True, output=output,
            confidence=confidence, duration_ms=duration_ms,
        )

    def _make_error(self, error: str) -> AgentResult:
        self._logger.error("Agent error: %s", error)
        return AgentResult(
            agent_name=self.__class__.__name__,
            success=False, output=None, error=error,
        )
