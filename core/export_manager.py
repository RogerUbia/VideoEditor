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
        project_name: str
    ) -> dict:
        os.makedirs(output_dir, exist_ok=True)
        safe_name = self._safe_name(project_name)

        # Copy video
        video_out = os.path.join(output_dir, f"{safe_name}_youtube.mp4")
        self._encode_final(processed_video, video_out, burn_filter=None)

        # Copy subtitle files
        sub_out = {}
        lang_labels = {"ca": "Catalan", "es": "Spanish", "en": "English"}
        for lang, srt_path in srt_files.items():
            if srt_path and os.path.exists(srt_path):
                dest = os.path.join(output_dir, f"{safe_name}_{lang}.srt")
                shutil.copy2(srt_path, dest)
                sub_out[lang] = dest

        return {
            "platform": "youtube",
            "output_video": video_out,
            "subtitles": sub_out,
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
        self._encode_final(processed_video, video_out,
                           burn_filter=burn_filter,
                           instagram_mode=True)

        return {
            "platform": "instagram",
            "output_video": video_out,
            "duration_s": duration,
            "warnings": warnings,
        }

    def _encode_final(
        self,
        input_path: str,
        output_path: str,
        burn_filter: str | None = None,
        instagram_mode: bool = False,
    ):
        cmd = [self.ffmpeg, "-y", "-i", input_path]

        if burn_filter:
            cmd += ["-vf", burn_filter]

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
        # Normalize path for FFmpeg (forward slashes, escape colons)
        srt_escaped = srt_path.replace("\\", "/")
        # On Windows, drive letter colon must be escaped: C:/... → C\:/...
        if len(srt_escaped) > 1 and srt_escaped[1] == ":":
            srt_escaped = srt_escaped[0] + "\\:" + srt_escaped[2:]

        font = config.get("subtitle_font", "Arial")
        size = config.get("subtitle_size", 28)
        color = config.get("subtitle_color", "#FFFFFF")
        # Convert hex to ASS color (ABGR format)
        ass_color = self._hex_to_ass(color)

        return (
            f"subtitles='{srt_escaped}'"
            f":force_style='Fontname={font},Fontsize={size},"
            f"PrimaryColour=&H{ass_color},"
            f"BackColour=&H80000000,"
            f"Bold=0,Outline=1,Shadow=0,Alignment=2,"
            f"MarginV=20'"
        )

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
