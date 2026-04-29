import os
import subprocess
from pathlib import Path


def _time_to_s(t: str) -> float:
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


class EffectsEngine:
    def __init__(self, config: dict):
        self.ffmpeg = config.get("ffmpeg_path", "ffmpeg")
        self.width = 1920
        self.height = 1080
        self.fps = 30

    # ── Public API ────────────────────────────────────────────────────────────

    def process_segment(
        self,
        segment: dict,
        input_path: str,
        output_path: str,
        pip_path: str | None = None,
        music_path: str | None = None,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
    ) -> str:
        self.width = width
        self.height = height
        self.fps = fps

        has_pip = bool(pip_path and os.path.exists(pip_path))
        has_music = bool(music_path and os.path.exists(music_path))
        seg_dur = _time_to_s(segment.get("time_end", "0:05")) - _time_to_s(segment.get("time_start", "0:00"))

        # Seek to segment start — CRITICAL: without this, all segments
        # would be extracted from second 0 of the input video
        seg_start = _time_to_s(segment.get("time_start", "0:00"))

        cmd = [self.ffmpeg, "-y",
               "-ss", str(seg_start),   # seek before -i (fast input seeking)
               "-i", input_path]
        if has_pip:
            cmd += ["-i", pip_path]
        if has_music:
            cmd += ["-i", music_path]

        filter_complex, video_out_label, audio_out_label = self._build_filters(
            segment, seg_dur, has_pip, has_music
        )

        if filter_complex:
            cmd += ["-filter_complex", filter_complex]
            cmd += ["-map", video_out_label]
            if audio_out_label:
                cmd += ["-map", audio_out_label]
            else:
                cmd += ["-map", "0:a?"]
        else:
            cmd += ["-map", "0:v", "-map", "0:a?"]

        cmd += [
            "-vcodec", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-acodec", "aac", "-b:a", "192k",
            "-t", str(max(0.1, seg_dur)),
            "-reset_timestamps", "1",   # ensure output timestamps start at 0
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg effects failed:\n{result.stderr[-800:]}")
        return output_path

    def concatenate_segments(
        self, segment_paths: list[str], output_path: str, temp_dir: str
    ) -> str:
        concat_list = os.path.join(temp_dir, "effects_concat.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for p in segment_paths:
                normalized = p.replace("\\", "/")
                f.write(f"file '{normalized}'\n")

        result = subprocess.run(
            [self.ffmpeg, "-y", "-f", "concat", "-safe", "0",
             "-i", concat_list, "-c", "copy",
             "-reset_timestamps", "1",   # continuous timestamps in final video
             output_path],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Concat failed:\n{result.stderr[-500:]}")
        return output_path

    # ── Filter builder ────────────────────────────────────────────────────────

    def _build_filters(
        self,
        segment: dict,
        seg_dur: float,
        has_pip: bool,
        has_music: bool,
    ) -> tuple[str, str, str | None]:
        parts: list[str] = []
        current = "[0:v]"
        audio_out: str | None = None

        # ── Zoom / video effect ───────────────────────────────────────────────
        zoom = segment.get("zoom", {})
        vfx = segment.get("video_effect", {}).get("type", "none")

        if zoom.get("enabled") and seg_dur > 0:
            factor = max(1.0, min(2.0, float(zoom.get("factor", 1.3))))
            frames = max(1, int(seg_dur * self.fps))
            f = self._zoom_in_filter(factor, frames)
            parts.append(f"{current}{f}[v_zoom]")
            current = "[v_zoom]"
        elif vfx == "zoom_in" and seg_dur > 0:
            frames = max(1, int(seg_dur * self.fps))
            f = self._zoom_in_filter(1.25, frames)
            parts.append(f"{current}{f}[v_zoom]")
            current = "[v_zoom]"
        elif vfx == "zoom_out" and seg_dur > 0:
            frames = max(1, int(seg_dur * self.fps))
            f = self._zoom_out_filter(frames)
            parts.append(f"{current}{f}[v_zoom]")
            current = "[v_zoom]"
        elif vfx == "shake":
            intensity = segment["video_effect"].get("intensity", 1.0)
            f = self._shake_filter(intensity)
            parts.append(f"{current}{f}[v_shake]")
            current = "[v_shake]"

        # ── Text overlay ──────────────────────────────────────────────────────
        text_cfg = segment.get("text_overlay", {})
        if text_cfg.get("enabled") and text_cfg.get("text", "").strip():
            f = self._text_filter(text_cfg)
            parts.append(f"{current}{f}[v_text]")
            current = "[v_text]"

        # ── Fade transitions ──────────────────────────────────────────────────
        ti = segment.get("transition_in", {})
        if ti.get("type") in ("fade", "dissolve"):
            d = ti.get("duration_s", 0.5)
            parts.append(f"{current}fade=t=in:st=0:d={d}[v_fi]")
            current = "[v_fi]"

        to_ = segment.get("transition_out", {})
        if to_.get("type") in ("fade", "dissolve"):
            d = to_.get("duration_s", 0.5)
            fade_start = max(0, seg_dur - d)
            parts.append(f"{current}fade=t=out:st={fade_start:.3f}:d={d}[v_fo]")
            current = "[v_fo]"

        # ── PiP overlay ───────────────────────────────────────────────────────
        if has_pip:
            pip_cfg = segment.get("pip", {})
            pip_w = int(self.width * pip_cfg.get("size_pct", 0.25))
            pip_h = int(pip_w * 9 / 16)
            x, y = self._pip_position(
                pip_cfg.get("position", "bottom_right"), pip_w, pip_h
            )
            parts.append(f"[1:v]scale={pip_w}:{pip_h}[pip_s]")
            parts.append(f"{current}[pip_s]overlay={x}:{y}[v_pip]")
            current = "[v_pip]"

        # ── Music / audio mix ─────────────────────────────────────────────────
        music_cfg = segment.get("music", {})
        if has_music and music_cfg.get("enabled", False):
            vol_db = music_cfg.get("volume_db", -12.0)
            vol_linear = 10 ** (vol_db / 20)
            music_idx = 2 if has_pip else 1
            fi = music_cfg.get("fade_in_s", 1.0)
            fo = music_cfg.get("fade_out_s", 1.0)
            fade_out_start = max(0, seg_dur - fo)
            parts.append(
                f"[{music_idx}:a]volume={vol_linear:.4f},"
                f"afade=t=in:st=0:d={fi},"
                f"afade=t=out:st={fade_out_start:.2f}:d={fo}[mus]"
            )
            parts.append(f"[0:a][mus]amix=inputs=2:duration=shortest[aout]")
            audio_out = "[aout]"

        # Rename final video label
        if current != "[0:v]":
            parts.append(f"{current}copy[vout]")
            video_out = "[vout]"
        else:
            video_out = "0:v"
            parts = []

        return ";".join(parts), video_out, audio_out

    # ── FFmpeg filter strings ─────────────────────────────────────────────────

    def _zoom_in_filter(self, factor: float, frames: int) -> str:
        step = (factor - 1.0) / frames
        return (
            f"zoompan=z='min(zoom+{step:.6f},{factor})'"
            f":d={frames}"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":s={self.width}x{self.height}:fps={self.fps}"
        )

    def _zoom_out_filter(self, frames: int) -> str:
        factor = 1.25
        step = (factor - 1.0) / frames
        return (
            f"zoompan=z='max(zoom-{step:.6f},1.0)'"
            f":d={frames}"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":s={self.width}x{self.height}:fps={self.fps}"
        )

    def _shake_filter(self, intensity: float) -> str:
        amp = max(2, int(8 * intensity))
        return (
            f"crop={self.width - amp}:{self.height - amp}"
            f":x='sin(t*20)*{amp // 2}':y='cos(t*17)*{amp // 2}',"
            f"scale={self.width}:{self.height}"
        )

    def _text_filter(self, cfg: dict) -> str:
        text = cfg.get("text", "")
        text = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
        font_file = self._find_font(cfg.get("font_family", "Arial"))
        font_size = cfg.get("font_size_pt", 36)
        color = cfg.get("color", "#FFFFFF").lstrip("#")
        bg = cfg.get("bg_color", "#00000080").lstrip("#")
        x_expr, y_expr = self._text_position(cfg.get("position", "bottom_center"))

        parts = [
            f"drawtext=text='{text}'",
            f"fontsize={font_size}",
            f"fontcolor=#{color}",
            "box=1",
            f"boxcolor=#{bg}",
            "boxborderw=8",
            f"x={x_expr}",
            f"y={y_expr}",
        ]
        if font_file:
            ff = font_file.replace("\\", "/")
            if len(ff) > 1 and ff[1] == ":":
                ff = ff[0] + "\\:" + ff[2:]
            parts.insert(1, f"fontfile='{ff}'")

        return "," + ",".join(parts)

    @staticmethod
    def _text_position(pos: str) -> tuple[str, str]:
        return {
            "bottom_center": ("(w-text_w)/2", "h-text_h-40"),
            "top_center": ("(w-text_w)/2", "40"),
            "center": ("(w-text_w)/2", "(h-text_h)/2"),
            "bottom_left": ("20", "h-text_h-40"),
            "bottom_right": ("w-text_w-20", "h-text_h-40"),
        }.get(pos, ("(w-text_w)/2", "h-text_h-40"))

    def _pip_position(self, pos: str, pw: int, ph: int) -> tuple[str, str]:
        m = 20
        w, h = self.width, self.height
        return {
            "bottom_right": (str(w - pw - m), str(h - ph - m)),
            "bottom_left": (str(m), str(h - ph - m)),
            "top_right": (str(w - pw - m), str(m)),
            "top_left": (str(m), str(m)),
        }.get(pos, (str(w - pw - m), str(h - ph - m)))

    @staticmethod
    def _find_font(font_name: str) -> str | None:
        base = "C:/Windows/Fonts"
        name_lower = font_name.lower().replace(" ", "")
        for suffix in ("", "bd", "bi", "i"):
            p = f"{base}/{name_lower}{suffix}.ttf"
            if os.path.exists(p):
                return p
        fallback = f"{base}/arial.ttf"
        return fallback if os.path.exists(fallback) else None
