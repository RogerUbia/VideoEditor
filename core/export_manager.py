import os
import json
import shutil
import subprocess
from pathlib import Path


class ExportManager:
    def __init__(self, config: dict):
        self.ffmpeg = config.get("ffmpeg_path", "ffmpeg")
        self.ffprobe = config.get("ffprobe_path", "ffprobe")
        self.crf = config.get("output_video_crf", 18)
        self.preset = config.get("output_video_preset", "fast")
        self.audio_bitrate = config.get("output_audio_bitrate", "192k")
        self.instagram_max_s = config.get("instagram_max_duration_s", 180)

    def get_duration(self, video_path: str) -> float:
        result = subprocess.run(
            [self.ffprobe, "-v", "quiet", "-print_format", "json",
             "-show_streams", video_path],
            capture_output=True, text=True, check=True
        )
        data = json.loads(result.stdout)
        for stream in data.get("streams", []):
            if "duration" in stream:
                return float(stream["duration"])
        return 0.0

    def export_youtube(
        self,
        processed_video: str,
        srt_files: dict,
        output_dir: str,
        project_name: str,
        burn_srt: str | None = None,
        sub_cfg: dict | None = None,
    ) -> dict:
        os.makedirs(output_dir, exist_ok=True)
        safe_name = self._safe_name(project_name)

        # Build subtitle burn filter if requested
        burn_filter = None
        if burn_srt and os.path.exists(burn_srt):
            burn_filter = self._subtitle_filter(burn_srt, sub_cfg or {})

        video_out = os.path.join(output_dir, f"{safe_name}_youtube.mp4")
        # YouTube: 1920×1080 landscape (16:9)
        self._encode_final(
            processed_video, video_out,
            burn_filter=burn_filter,
            target_w=1920, target_h=1080,
        )

        # Copy .srt files alongside video
        sub_out = {}
        for lang, srt_path in srt_files.items():
            if srt_path and os.path.exists(srt_path):
                dest = os.path.join(output_dir, f"{safe_name}_{lang}.srt")
                shutil.copy2(srt_path, dest)
                sub_out[lang] = dest

        return {
            "platform": "youtube",
            "output_video": video_out,
            "subtitles": sub_out,
            "burned": burn_filter is not None,
        }

    def export_instagram(
        self,
        processed_video: str,
        srt_en_path: str,
        output_dir: str,
        project_name: str,
        subtitle_config: dict = None
    ) -> dict:
        os.makedirs(output_dir, exist_ok=True)
        safe_name = self._safe_name(project_name)
        subtitle_config = subtitle_config or {}

        # Check duration
        duration = self.get_duration(processed_video)
        warnings = []
        if duration > self.instagram_max_s:
            warnings.append(
                f"Video duration {duration:.0f}s exceeds Instagram limit of "
                f"{self.instagram_max_s}s"
            )

        # Build subtitle burn filter
        burn_filter = None
        if srt_en_path and os.path.exists(srt_en_path):
            burn_filter = self._subtitle_filter(srt_en_path, subtitle_config)

        video_out = os.path.join(output_dir, f"{safe_name}_instagram.mp4")
        # Instagram: 1080×1920 portrait (9:16)
        self._encode_final(
            processed_video, video_out,
            burn_filter=burn_filter,
            instagram_mode=True,
            target_w=1080, target_h=1920,
        )

        return {
            "platform": "instagram",
            "output_video": video_out,
            "duration_s": duration,
            "warnings": warnings,
        }

    def _scale_filter(self, target_w: int, target_h: int) -> str:
        """Scale + pad to exact target resolution, maintaining aspect ratio."""
        return (
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black,"
            f"setsar=1"
        )

    def _build_vf(
        self,
        scale_filter: str | None,
        burn_filter: str | None,
    ) -> str | None:
        """Chain scale and subtitle filters."""
        parts = []
        if scale_filter:
            parts.append(scale_filter)
        if burn_filter:
            parts.append(burn_filter)
        return ",".join(parts) if parts else None

    def _encode_final(
        self,
        input_path: str,
        output_path: str,
        burn_filter: str | None = None,
        instagram_mode: bool = False,
        target_w: int | None = None,
        target_h: int | None = None,
    ):
        cmd = [self.ffmpeg, "-y", "-i", input_path]

        # Build video filter: scale first, then burn subtitles
        scale_f = self._scale_filter(target_w, target_h) if (target_w and target_h) else None
        vf = self._build_vf(scale_f, burn_filter)
        if vf:
            cmd += ["-vf", vf]

        if instagram_mode:
            cmd += [
                "-vcodec", "libx264",
                "-preset", "slow",
                "-crf", "20",
                "-profile:v", "high",
                "-level", "4.0",
                "-pix_fmt", "yuv420p",
                "-acodec", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
            ]
        else:
            cmd += [
                "-vcodec", "libx264",
                "-preset", self.preset,
                "-crf", str(self.crf),
                "-pix_fmt", "yuv420p",
                "-acodec", "aac",
                "-b:a", self.audio_bitrate,
                "-movflags", "+faststart",
            ]

        cmd.append(output_path)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg encode failed:\n{result.stderr[-1000:]}"
            )

    def _subtitle_filter(self, srt_path: str, config: dict) -> str:
        """Build FFmpeg subtitle filter. Converts to ASS for animation support."""
        animation = config.get("subtitle_animation", "fade")

        if animation != "none":
            # Convert SRT → ASS with animation tags
            ass_path = srt_path.replace(".srt", "_animated.ass")
            self._srt_to_ass(srt_path, ass_path, config)
            return self._ass_filter(ass_path)
        else:
            return self._plain_subtitle_filter(srt_path, config)

    def _plain_subtitle_filter(self, srt_path: str, config: dict) -> str:
        srt_escaped = srt_path.replace("\\", "/")
        if len(srt_escaped) > 1 and srt_escaped[1] == ":":
            srt_escaped = srt_escaped[0] + "\\:" + srt_escaped[2:]
        font   = config.get("subtitle_font", "Arial")
        size   = config.get("subtitle_size", 28)
        bold   = 1 if config.get("subtitle_bold") else 0
        italic = 1 if config.get("subtitle_italic") else 0
        pos    = {"bottom_center": 2, "top_center": 8, "middle_center": 5}.get(
                     config.get("subtitle_position", "bottom_center"), 2)
        bg     = self._hex_to_ass(config.get("subtitle_bg_color", "#80000000"))
        return (
            f"subtitles='{srt_escaped}'"
            f":force_style='Fontname={font},Fontsize={size},"
            f"PrimaryColour=&H00FFFFFF,"
            f"BackColour=&H{bg},"
            f"Bold={bold},Italic={italic},"
            f"Outline=1,Shadow=0,Alignment={pos},MarginV=20'"
        )

    def _ass_filter(self, ass_path: str) -> str:
        ass_escaped = ass_path.replace("\\", "/")
        if len(ass_escaped) > 1 and ass_escaped[1] == ":":
            ass_escaped = ass_escaped[0] + "\\:" + ass_escaped[2:]
        return f"ass='{ass_escaped}'"

    def _srt_to_ass(self, srt_path: str, ass_path: str, config: dict):
        """Convert SRT to ASS format with animation tags."""
        import re

        animation = config.get("subtitle_animation", "fade")
        fade_ms   = config.get("subtitle_fade_ms", 250)
        font      = config.get("subtitle_font",   "Arial")
        size      = config.get("subtitle_size",    28)
        bold      = 1 if config.get("subtitle_bold") else 0
        italic    = 1 if config.get("subtitle_italic") else 0
        pos_map   = {"bottom_center": 2, "top_center": 8, "middle_center": 5}
        alignment = pos_map.get(config.get("subtitle_position", "bottom_center"), 2)

        # Animation override tag per entry
        if animation == "fade":
            anim_tag = f"{{\\fad({fade_ms},{fade_ms})}}"
        elif animation == "fade_in":
            anim_tag = f"{{\\fad({fade_ms},0)}}"
        elif animation == "slide_up":
            anim_tag = f"{{\\fad({fade_ms},0)\\move(320,320,320,288)}}"
        else:
            anim_tag = ""

        try:
            srt_content = open(srt_path, encoding="utf-8-sig").read()
        except Exception:
            return

        # Parse SRT
        blocks = re.split(r"\n\n+", srt_content.strip())
        events = []
        for block in blocks:
            lines = block.strip().splitlines()
            if len(lines) < 3:
                continue
            try:
                tc = lines[1].split(" --> ")
                start = self._srt_tc_to_ass(tc[0].strip())
                end   = self._srt_tc_to_ass(tc[1].strip())
                text  = "\\N".join(lines[2:])
                events.append((start, end, anim_tag + text))
            except Exception:
                continue

        ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,{bold},{italic},0,0,100,100,0,0,1,2,0,{alignment},10,10,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        event_lines = [
            f"Dialogue: 0,{s},{e},Default,,0,0,0,,{t}"
            for s, e, t in events
        ]
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass_header + "\n".join(event_lines) + "\n")

    @staticmethod
    def _srt_tc_to_ass(tc: str) -> str:
        """Convert SRT timecode (HH:MM:SS,mmm) to ASS (H:MM:SS.cc)."""
        tc = tc.replace(",", ".")
        parts = tc.split(":")
        h, m = int(parts[0]), int(parts[1])
        s_ms = parts[2].split(".")
        s    = int(s_ms[0])
        ms   = int(s_ms[1]) if len(s_ms) > 1 else 0
        cs   = ms // 10     # centiseconds
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    @staticmethod
    def _hex_to_ass(hex_color: str) -> str:
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 6:
            r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
            return f"00{b}{g}{r}".upper()  # ASS is ABGR
        return "00FFFFFF"

    @staticmethod
    def _safe_name(name: str) -> str:
        import re
        return re.sub(r'[^\w\-]', '_', name)
