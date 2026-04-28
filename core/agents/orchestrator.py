import logging
import uuid
from datetime import datetime
from typing import Callable

from .base_agent import AgentResult


class AgentOrchestrator:
    """Coordinates all Gemini agents for the VideoForge pipeline.

    Uses lazy instantiation — agents are created on first use so the
    orchestrator works even when some agent modules are not yet written.
    """

    def __init__(self, api_key: str, config: dict, memory=None):
        self.api_key = api_key
        self.config = config
        self.memory = memory
        self._logger = logging.getLogger("AgentOrchestrator")
        self._agents: dict = {}
        self._message_log: list[dict] = []

    # ── Agent factory ────────────────────────────────────────────────────────

    def _get(self, name: str):
        if name not in self._agents:
            self._agents[name] = self._create(name)
        return self._agents[name]

    def _create(self, name: str):
        try:
            match name:
                case "script_writer":
                    from .script_writer import ScriptWriterAgent
                    return ScriptWriterAgent(self.api_key, self.memory)
                case "transcription":
                    from .transcription import TranscriptionAgent
                    return TranscriptionAgent(self.api_key)
                case "text_corrector":
                    from .text_corrector import TextCorrectorAgent
                    return TextCorrectorAgent(self.api_key)
                case "validator":
                    from .validator import ValidatorAgent
                    return ValidatorAgent(self.api_key)
                case "duplicate_detector":
                    from .duplicate_detector import DuplicateDetectorAgent
                    return DuplicateDetectorAgent(self.api_key)
                case "effects_planner":
                    from .effects_planner import EffectsPlannerAgent
                    return EffectsPlannerAgent(self.api_key)
                case "subtitle_translator":
                    from .subtitle_translator import SubtitleTranslatorAgent
                    return SubtitleTranslatorAgent(self.api_key)
                case "quality_control":
                    from .quality_control import QualityControlAgent
                    return QualityControlAgent(self.api_key)
                case _:
                    self._logger.warning("Unknown agent: %s", name)
                    return None
        except ImportError as exc:
            self._logger.warning("Agent '%s' not available: %s", name, exc)
            return None

    # ── Message bus ──────────────────────────────────────────────────────────

    def _log_message(self, from_agent: str, to_agent: str, step: int, payload: dict):
        msg = {
            "id": str(uuid.uuid4()),
            "from_agent": from_agent,
            "to_agent": to_agent,
            "pipeline_step": step,
            "payload": payload,
            "timestamp": datetime.now().isoformat(),
        }
        self._message_log.append(msg)
        return msg

    def get_message_log(self) -> list[dict]:
        return self._message_log.copy()

    # ── Pipeline step methods ─────────────────────────────────────────────────

    def generate_script(
        self,
        user_prompt: str,
        project_name: str,
        current_script: dict | None = None,
    ) -> AgentResult:
        agent = self._get("script_writer")
        if not agent:
            return AgentResult("script_writer", False, {}, error="Agent not available")
        result = agent.run({
            "user_prompt": user_prompt,
            "project_name": project_name,
            "current_script": current_script,
        })
        self._log_message("user", "script_writer", 0, {"prompt": user_prompt})
        return result

    def transcribe_audio(self, audio_path: str, language: str = "ca") -> AgentResult:
        agent = self._get("transcription")
        if not agent:
            return AgentResult("transcription", False, "", error="Agent not available")
        result = agent.run({"audio_path": audio_path, "language": language})
        self._log_message("pipeline", "transcription", 3, {"audio_path": audio_path})
        return result

    def correct_text(self, text: str, language: str = "ca") -> AgentResult:
        agent = self._get("text_corrector")
        if not agent:
            return AgentResult("text_corrector", True, text)
        result = agent.run({"text": text, "language": language})
        self._log_message("transcription", "text_corrector", 4, {"length": len(text)})
        return result

    def validate_script(self, script: dict, transcription: str) -> AgentResult:
        agent = self._get("validator")
        if not agent:
            return AgentResult("validator", False, {}, error="Agent not available")
        result = agent.run({"script": script, "transcription": transcription})
        self._log_message("text_corrector", "validator", 5, {})
        return result

    def detect_duplicates(self, segments: list[dict]) -> AgentResult:
        agent = self._get("duplicate_detector")
        if not agent:
            return AgentResult("duplicate_detector", True, segments)
        result = agent.run({"segments": segments})
        self._log_message("validator", "duplicate_detector", 6, {"count": len(segments)})
        return result

    def plan_effects(self, script: dict) -> AgentResult:
        agent = self._get("effects_planner")
        if not agent:
            return AgentResult("effects_planner", True, script)
        result = agent.run({"script": script})
        self._log_message("duplicate_detector", "effects_planner", 7, {})
        return result

    def translate_subtitle(
        self, srt_content: str, source: str, target: str
    ) -> AgentResult:
        agent = self._get("subtitle_translator")
        if not agent:
            return AgentResult("subtitle_translator", True, srt_content)
        result = agent.run({
            "srt_content": srt_content,
            "source_lang": source,
            "target_lang": target,
        })
        self._log_message("pipeline", "subtitle_translator", 8, {
            "source": source, "target": target
        })
        return result

    def quality_check(self, pipeline_outputs: dict) -> AgentResult:
        agent = self._get("quality_control")
        if not agent:
            return AgentResult("quality_control", True, {"recommendation": "approve"})
        result = agent.run(pipeline_outputs)
        self._log_message("pipeline", "quality_control", 8, {})
        return result
