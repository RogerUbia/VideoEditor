import os
import json
import shutil
import subprocess
import threading
import concurrent.futures
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


def _t2s(t: str) -> float:
    t = t.replace(",", ".")
    parts = t.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
    except (ValueError, IndexError):
        pass
    return 0.0


class PipelineWorker(QThread):
    step_started   = pyqtSignal(int, str)
    step_finished  = pyqtSignal(int, str)
    step_failed    = pyqtSignal(int, str)
    progress       = pyqtSignal(int)
    log_message    = pyqtSignal(str, str)   # (level, message)
    awaiting_approval = pyqtSignal()
    finished_all   = pyqtSignal(dict)
    interim_update = pyqtSignal(dict)        # intermediate data for timeline

    STEPS = [
        "Import & Validate",
        "Remove Silences",
        "Transcribe Audio",
        "Correct Transcription",
        "Validate vs Script",
        "Detect Duplicates",
        "Apply Effects",
        "Export & Subtitles",
    ]

    def __init__(
        self,
        project: dict,
        config: dict,
        api_key: str,
        mode: str = "manual",
    ):
        super().__init__()
        self.project = project
        self.config = config
        self.api_key = api_key
        self.mode = mode          # "full_auto" | "manual"
        self._cancelled = False
        self._approval = threading.Event()
        self._tmp: dict = {}      # intermediate file paths & data

    def cancel(self):
        self._cancelled = True
        self._approval.set()

    def resume(self):
        """Called from GUI to continue after manual approval step."""
        self._approval.set()

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self):
        base_dir = Path(self.project.get("base_dir", "."))
        project_name = self.project.get("project_name", "project")
        video_path = self.project.get("video_path", "")

        temp_dir = base_dir / self.config.get("temp_dir", "data/temp") / project_name
        temp_dir.mkdir(parents=True, exist_ok=True)
        self._tmp["temp_dir"] = str(temp_dir)

        steps = [
            self._step_import,
            self._step_silence,
            self._step_transcribe,
            self._step_correct,
            self._step_validate,
            self._step_dedup,
            self._step_effects,
            self._step_export,
        ]

        for i, fn in enumerate(steps):
            if self._cancelled:
                self._log("WARNING", "Pipeline cancelled by user")
                return

            # Manual mode: pause before Step 6 (dedup), after validation
            if self.mode == "manual" and i == 5:
                self.awaiting_approval.emit()
                self._log("INFO",
                    "⏸ Awaiting approval — review the script table, then click Resume.")
                self._approval.wait()
                self._approval.clear()
                if self._cancelled:
                    return

            name = self.STEPS[i]
            self.step_started.emit(i, name)
            self._log("STEP", f"[{i+1}/8] {name}")

            try:
                msg = fn(temp_dir, video_path, project_name)
                self.step_finished.emit(i, msg)
                self.progress.emit(int((i + 1) / 8 * 100))
                self._log("SUCCESS", f"✓ {name}: {msg}")
            except Exception as exc:
                self.step_failed.emit(i, str(exc))
                self._log("ERROR", f"✗ {name} failed: {exc}")
                return

        if not self._cancelled:
            self.finished_all.emit(self._collect_outputs())

    def _log(self, level: str, msg: str):
        self.log_message.emit(level, msg)

    def _collect_outputs(self) -> dict:
        return {
            "output_video":       self._tmp.get("final_output", ""),
            "subtitles": {
                "ca": self._tmp.get("srt_ca", ""),
                "es": self._tmp.get("srt_es", ""),
                "en": self._tmp.get("srt_en", ""),
            },
            "validation_report":  self._tmp.get("validation_report", {}),
            "script":             self._tmp.get("final_script", {}),
        }

    # ── Step 1: Import ────────────────────────────────────────────────────────

    def _step_import(self, temp_dir: Path, video_path: str, _: str) -> str:
        if not video_path or not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")

        ffprobe = self.config.get("ffprobe_path", "ffprobe")
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json",
             "-show_streams", "-show_format", video_path],
            capture_output=True, text=True, check=True,
        )
        meta = json.loads(result.stdout)

        w, h, fps, dur = 1920, 1080, 30, 0.0
        for s in meta.get("streams", []):
            if s.get("codec_type") == "video":
                w = s.get("width", 1920)
                h = s.get("height", 1080)
                num, den = s.get("r_frame_rate", "30/1").split("/")
                fps = max(1, int(num) // max(1, int(den)))
                dur_raw = s.get("duration") or meta.get("format", {}).get("duration", "0")
                dur = float(dur_raw)
                break

        self._tmp.update({"width": w, "height": h, "fps": fps,
                          "duration": dur, "source_video": video_path})
        return f"{os.path.basename(video_path)} ({dur:.1f}s, {w}x{h} @ {fps}fps)"

    # ── Auto-segmentation ─────────────────────────────────────────────────────

    def _auto_segment_from_intervals(self) -> list[dict]:
        """Create script segments from silence-removal keep_intervals."""
        import uuid

        intervals = self._tmp.get("keep_intervals", [])
        if not intervals:
            dur = self._tmp.get("duration", 60.0)
            intervals = [{"start_s": 0.0, "end_s": dur, "duration_s": dur}]

        def fmt(s: float) -> str:
            h = int(s) // 3600
            m = (int(s) % 3600) // 60
            sec = s % 60
            return f"{h:02d}:{m:02d}:{sec:06.3f}"

        # Build cumulative (consecutive) timestamps — no gaps
        cursor = 0.0
        segments = []
        for i, iv in enumerate(intervals):
            dur   = iv.get("duration_s", iv["end_s"] - iv["start_s"])
            start = cursor
            end   = cursor + dur
            cursor = end
            segments.append({
                "id": str(uuid.uuid4()),
                "order": i,
                "time_start": fmt(start),
                "time_end":   fmt(end),
                "content":    "",
                "message":    f"Segment {i + 1}",
                "video_effect":   {"type": "none", "intensity": 1.0},
                "zoom":           {"enabled": False, "factor": 1.0},
                "transition_in":  {"type": "none", "duration_s": 0.5},
                "transition_out": {"type": "none", "duration_s": 0.5},
                "pip":            {"enabled": False, "source": "none"},
                "music":          {"enabled": False, "file_path": ""},
                "text_overlay":   {"enabled": False, "text": ""},
                "notes":          "Auto-generated from silence detection",
                "transcription":  "",
                "validated":      False,
                "validation_score": 0.0,
                "is_duplicate":   False,
                "is_best_take":   True,
                "effects_ffmpeg": ""
            })
        return segments

    def _distribute_transcription(self, transcript: str):
        """Split transcription text across segments proportionally by duration."""
        segments = self.project.get("segments", [])
        if not segments or not transcript:
            return

        words = transcript.split()
        if not words:
            return

        total_dur = sum(
            max(0, _t2s(s.get("time_end", "0")) - _t2s(s.get("time_start", "0")))
            for s in segments
        )
        if total_dur <= 0:
            return

        word_idx = 0
        for seg in segments:
            seg_dur = max(0, _t2s(seg.get("time_end", "0")) - _t2s(seg.get("time_start", "0")))
            word_count = max(1, int(len(words) * seg_dur / total_dur))
            seg_words = words[word_idx: word_idx + word_count]
            seg["content"] = " ".join(seg_words)
            word_idx = min(word_idx + word_count, len(words))

        # Give any remaining words to the last segment
        if word_idx < len(words):
            segments[-1]["content"] += " " + " ".join(words[word_idx:])

    # ── Step 2: Silence removal ───────────────────────────────────────────────

    def _step_silence(self, temp_dir: Path, video_path: str, _: str) -> str:
        from core.silence_remover import SilenceRemover

        remover = SilenceRemover(self.config)
        output = str(temp_dir / "01_silence_removed.mp4")
        threshold  = self.config.get("silence_threshold_db",    -40)
        min_dur    = self.config.get("silence_min_duration_ms",  500)
        margin     = self.config.get("silence_margin_ms",        100)

        def cb(p):
            self.progress.emit(int((1 + p / 100) / 8 * 100))

        min_seg = self.config.get("silence_min_segment_ms", 1000)
        png_path = str(temp_dir / "waveform_analysis.png")

        out, intervals, waveform_png = remover.process(
            video_path, output, str(temp_dir),
            threshold_db=threshold, min_duration_ms=min_dur,
            margin_ms=margin, min_segment_ms=min_seg,
            progress_callback=cb, waveform_png_path=png_path,
        )
        self._tmp["silence_removed"] = out
        self._tmp["keep_intervals"]  = intervals
        self._tmp["waveform_png"]    = waveform_png

        self._log("INFO",
            f"Silence removal: {len(intervals)} segments, "
            f"waveform → {waveform_png or 'N/A'}"
        )

        # Auto-create segments if none defined
        if not self.project.get("segments"):
            auto_segs = self._auto_segment_from_intervals()
            self.project = {**self.project, "segments": auto_segs}
            self._log("INFO", f"Auto-segmentat: {len(auto_segs)} segments des del silenci")

        self.interim_update.emit({
            "step": "silence",
            "script": self.project,
            "silence_removed_path": out,
            "waveform_png": waveform_png,
        })

        return f"{len(intervals)} segments kept"

    # ── Step 3: Transcription ─────────────────────────────────────────────────

    def _step_transcribe(self, temp_dir: Path, video_path: str, _: str) -> str:
        from core.agents.orchestrator import AgentOrchestrator
        from core.silence_remover import SilenceRemover

        source     = self._tmp.get("silence_removed", video_path)
        audio_path = str(temp_dir / "02_audio.wav")
        SilenceRemover(self.config).extract_audio(source, audio_path)

        orch   = AgentOrchestrator(self.api_key, self.config)
        result = orch.transcribe_audio(audio_path, language="ca")

        if not result.success:
            raise RuntimeError(f"Transcription failed: {result.error}")

        path = str(temp_dir / "03_transcript_raw.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"transcript": result.output}, f, ensure_ascii=False)

        self._tmp["transcript_raw"] = result.output

        # If segments were auto-created (no content yet), distribute transcription
        if all(not s.get("content") for s in self.project.get("segments", [])):
            self._distribute_transcription(result.output)
            self.interim_update.emit({"step": "transcribe", "script": self.project})
            self._log("INFO", "Transcripció distribuïda entre els segments automàtics")

        return f"{len(result.output)} chars transcribed"

    # ── Step 4: Correction ────────────────────────────────────────────────────

    def _step_correct(self, temp_dir: Path, *_) -> str:
        from core.agents.orchestrator import AgentOrchestrator

        raw = self._tmp.get("transcript_raw", "")
        if not raw:
            return "No transcription to correct"

        orch      = AgentOrchestrator(self.api_key, self.config)
        result    = orch.correct_text(raw, language="ca")
        corrected = result.output if result.success else raw

        path = str(temp_dir / "04_transcript_corrected.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"transcript": corrected}, f, ensure_ascii=False)

        self._tmp["transcript_corrected"] = corrected
        return "Transcription corrected"

    # ── Step 5: Validation ────────────────────────────────────────────────────

    def _step_validate(self, temp_dir: Path, *_) -> str:
        segments   = self.project.get("segments", [])
        transcript = self._tmp.get("transcript_corrected", "")

        # Skip AI validation if there is no script to compare against
        if not segments:
            self._log("INFO", "No script segments — skipping validation (auto-approve)")
            report = {"overall_match_score": 1.0, "recommendation": "approve",
                      "notes": "No script provided — validation skipped"}
            self._tmp["validation_report"] = report
            path = str(temp_dir / "05_validation_report.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False)
            return "Skipped (no script)"

        from core.agents.orchestrator import AgentOrchestrator
        orch   = AgentOrchestrator(self.api_key, self.config)
        result = orch.validate_script(self.project, transcript)
        report = result.output if result.success else {}

        path = str(temp_dir / "05_validation_report.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False)

        self._tmp["validation_report"] = report
        score = report.get("overall_match_score", 0)
        rec   = report.get("recommendation", "?")
        if rec == "reject":
            self._log("WARNING", f"Validation score {score:.0%} → {rec}")
        return f"Match {score:.0%} → {rec}"

    # ── Step 6: Duplicate detection ───────────────────────────────────────────

    def _step_dedup(self, temp_dir: Path, *_) -> str:
        from core.agents.orchestrator import AgentOrchestrator

        segments = self.project.get("segments", [])
        if not segments:
            self._tmp["final_script"] = self.project
            return "No segments"

        orch   = AgentOrchestrator(self.api_key, self.config)
        result = orch.detect_duplicates(segments)

        final_segs = result.output if result.success else segments
        dup_count  = sum(1 for s in final_segs if s.get("is_duplicate"))

        final_script = {**self.project, "segments": final_segs}
        path = str(temp_dir / "06_segments_final.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(final_script, f, ensure_ascii=False)

        self._tmp["final_script"] = final_script
        return f"{len(segments)} segments, {dup_count} duplicates marked"

    # ── Step 7: Effects ───────────────────────────────────────────────────────

    def _step_effects(self, temp_dir: Path, video_path: str, _: str) -> str:
        from core.agents.orchestrator import AgentOrchestrator
        from core.effects_engine import EffectsEngine

        script = self._tmp.get("final_script", self.project)
        source = self._tmp.get("silence_removed", video_path)

        # AI plans effects
        orch = AgentOrchestrator(self.api_key, self.config)
        ef   = orch.plan_effects(script)
        if ef.success:
            script = ef.output

        engine   = EffectsEngine(self.config)
        segments = [
            s for s in script.get("segments", [])
            if not s.get("is_duplicate", False)
        ]

        if not segments:
            out = str(temp_dir / "07_effects_applied.mp4")
            shutil.copy2(source, out)
            self._tmp["effects_applied"] = out
            return "No segments — video passed through"

        seg_paths = []
        total = len(segments)
        for i, seg in enumerate(segments):
            seg_out = str(temp_dir / f"fx_{i:04d}.mp4")
            pip_path   = None
            music_path = None
            if seg.get("pip", {}).get("enabled"):
                src = seg["pip"].get("source", "")
                if src and os.path.exists(src):
                    pip_path = src
            if seg.get("music", {}).get("enabled"):
                src = seg["music"].get("file_path", "")
                if src and os.path.exists(src):
                    music_path = src
            try:
                engine.process_segment(
                    seg, source, seg_out,
                    pip_path=pip_path, music_path=music_path,
                    width=self._tmp.get("width", 1920),
                    height=self._tmp.get("height", 1080),
                    fps=self._tmp.get("fps", 30),
                )
            except Exception as exc:
                self._log("WARNING", f"Segment {i} effects skipped: {exc}")
                self._extract_segment(source, seg, seg_out)
            seg_paths.append(seg_out)
            self.progress.emit(int((6 + (i + 1) / total) / 8 * 100))

        out = str(temp_dir / "07_effects_applied.mp4")
        if len(seg_paths) > 1:
            engine.concatenate_segments(seg_paths, out, str(temp_dir))
        else:
            shutil.copy2(seg_paths[0], out)

        self._tmp["effects_applied"] = out
        return f"Effects applied to {len(seg_paths)} segments"

    def _extract_segment(self, source: str, seg: dict, output: str):
        start = _t2s(seg.get("time_start", "0:00"))
        end   = _t2s(seg.get("time_end",   "0:05"))
        dur   = max(0.1, end - start)
        subprocess.run(
            [self.config.get("ffmpeg_path", "ffmpeg"), "-y",
             "-ss", str(start), "-i", source,
             "-t", str(dur), "-c", "copy", output],
            capture_output=True, check=True,
        )

    # ── Step 8: Export ────────────────────────────────────────────────────────

    def _step_export(self, temp_dir: Path, video_path: str, project_name: str) -> str:
        from core.subtitle_generator import SubtitleGenerator
        from core.export_manager import ExportManager
        from core.agents.orchestrator import AgentOrchestrator

        script   = self._tmp.get("final_script", self.project)
        segments = [s for s in script.get("segments", [])
                    if not s.get("is_duplicate", False)]
        source   = self._tmp.get("effects_applied", video_path)

        # Generate Catalan SRT
        gen = SubtitleGenerator()
        srt_ca = gen.generate_srt(segments, "ca")
        p_ca   = str(temp_dir / "subs_ca.srt")
        gen.save_srt(srt_ca, p_ca)
        self._tmp["srt_ca"] = p_ca

        # Translate ES + EN in parallel
        orch = AgentOrchestrator(self.api_key, self.config)

        def translate(lang: str) -> tuple[str, str]:
            r = orch.translate_subtitle(srt_ca, "ca", lang)
            return lang, r.output if r.success else srt_ca

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            for lang, translated in ex.map(translate, ("es", "en")):
                p = str(temp_dir / f"subs_{lang}.srt")
                gen.save_srt(translated, p)
                self._tmp[f"srt_{lang}"] = p

        # Encode final
        platform   = script.get("global_settings", {}).get("target_platform", "youtube")
        output_dir = str(temp_dir / "output")
        exp        = ExportManager(self.config)

        if platform == "instagram":
            sub_cfg = {
                "subtitle_font": script["global_settings"].get("subtitle_font", "Arial"),
                "subtitle_size": script["global_settings"].get("subtitle_font_size", 28),
            }
            out = exp.export_instagram(
                source, self._tmp.get("srt_en"), output_dir, project_name, sub_cfg
            )
            for w in out.get("warnings", []):
                self._log("WARNING", w)
        else:
            out = exp.export_youtube(
                source,
                {"ca": self._tmp.get("srt_ca"),
                 "es": self._tmp.get("srt_es"),
                 "en": self._tmp.get("srt_en")},
                output_dir, project_name,
            )

        self._tmp["final_output"] = out.get("output_video", "")

        # Quality check
        qc = orch.quality_check({
            "script":             script,
            "validation_report":  self._tmp.get("validation_report", {}),
            "subtitles":          out.get("subtitles", {}),
            "output_video":       out.get("output_video", ""),
        })
        if qc.success:
            q = qc.output
            self._log("INFO",
                f"QC {q.get('quality_score', 0):.0%} — "
                f"{q.get('recommendation')} — {q.get('notes', '')}"
            )

        return f"[{platform}] {os.path.basename(out.get('output_video', ''))}"
