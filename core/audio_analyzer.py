"""
AudioAnalyzer: FFmpeg-based silence detection + PIL waveform visualization.
Replaces pydub which used a simple RMS threshold with 10ms seek step.
"""
import re
import os
import struct
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont


class AudioAnalyzer:
    def __init__(self, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe"):
        self.ffmpeg  = ffmpeg
        self.ffprobe = ffprobe

    # ── Silence detection via FFmpeg ──────────────────────────────────────────

    def detect_silences_ffmpeg(
        self,
        audio_path: str,
        threshold_db: float = -35.0,
        min_duration_s: float = 0.6,
        mono: bool = True,
    ) -> list[dict]:
        """
        Use FFmpeg's silencedetect filter — frame-accurate, no seek_step limitation.
        Returns list of {start_s, end_s, duration_s}.
        """
        noise_flag = f"{threshold_db}dB"
        af = f"silencedetect=noise={noise_flag}:duration={min_duration_s}"
        if mono:
            af = f"pan=mono|c0=c0,{af}"

        result = subprocess.run(
            [self.ffmpeg, "-i", audio_path, "-af", af, "-f", "null", "-"],
            capture_output=True, text=True
        )
        output = result.stderr  # FFmpeg writes filter info to stderr

        silences = []
        start = None
        for line in output.splitlines():
            m_start = re.search(r"silence_start:\s*([\d.]+)", line)
            m_end   = re.search(r"silence_end:\s*([\d.]+)", line)
            if m_start:
                start = float(m_start.group(1))
            if m_end and start is not None:
                end = float(m_end.group(1))
                silences.append({
                    "start_s":    start,
                    "end_s":      end,
                    "duration_s": end - start,
                    "start_ms":   int(start * 1000),
                    "end_ms":     int(end   * 1000),
                })
                start = None

        # Handle audio that ends during silence (no silence_end logged)
        if start is not None:
            dur_s = self._get_duration(audio_path)
            silences.append({
                "start_s":    start,
                "end_s":      dur_s,
                "duration_s": dur_s - start,
                "start_ms":   int(start  * 1000),
                "end_ms":     int(dur_s  * 1000),
            })

        return silences

    def compute_keep_intervals(
        self,
        silences: list[dict],
        total_duration_s: float,
        margin_s: float = 0.15,
        min_segment_s: float = 1.0,
    ) -> list[dict]:
        """
        Convert silence list to speech (keep) intervals.
        - Adds margin around each silence boundary
        - Guarantees no overlapping intervals
        - Removes segments shorter than min_segment_s
        """
        if not silences:
            return [{
                "start_s": 0.0, "end_s": total_duration_s,
                "duration_s": total_duration_s,
                "start_ms": 0, "end_ms": int(total_duration_s * 1000),
            }]

        keep = []
        cursor = 0.0

        for silence in silences:
            # Speech ends margin_s before silence starts
            speech_end = max(cursor, silence["start_s"] - margin_s)
            speech_start = cursor

            if speech_end > speech_start and (speech_end - speech_start) >= min_segment_s:
                keep.append({
                    "start_s":    round(speech_start, 4),
                    "end_s":      round(speech_end,   4),
                    "duration_s": round(speech_end - speech_start, 4),
                    "start_ms":   int(speech_start * 1000),
                    "end_ms":     int(speech_end   * 1000),
                })

            # Next speech starts margin_s after silence ends
            cursor = min(total_duration_s, silence["end_s"] + margin_s)

        # Final segment after last silence
        if cursor < total_duration_s:
            seg_dur = total_duration_s - cursor
            if seg_dur >= min_segment_s:
                keep.append({
                    "start_s":    round(cursor,             4),
                    "end_s":      round(total_duration_s,   4),
                    "duration_s": round(seg_dur,            4),
                    "start_ms":   int(cursor            * 1000),
                    "end_ms":     int(total_duration_s  * 1000),
                })

        return keep

    # ── Waveform visualization ────────────────────────────────────────────────

    def generate_waveform_png(
        self,
        audio_path: str,
        silences: list[dict],
        keep_intervals: list[dict],
        output_png: str,
        width: int = 1800,
        height: int = 300,
    ) -> str:
        """
        Generate a waveform PNG with silence/speech regions color-coded.
        - Red   = detected silence
        - Green = kept speech segment
        - White = waveform
        """
        samples, sample_rate = self._read_wav_samples(audio_path)
        if samples is None or len(samples) == 0:
            return ""

        total_s = len(samples) / sample_rate

        img  = Image.new("RGB", (width, height), (18, 18, 18))
        draw = ImageDraw.Draw(img, "RGBA")

        # Draw silence regions (red)
        for sil in silences:
            x1 = int(sil["start_s"] / total_s * width)
            x2 = int(sil["end_s"]   / total_s * width)
            draw.rectangle([x1, 0, x2, height], fill=(180, 40, 40, 120))

        # Draw keep intervals (green)
        for iv in keep_intervals:
            x1 = int(iv["start_s"] / total_s * width)
            x2 = int(iv["end_s"]   / total_s * width)
            draw.rectangle([x1, 0, x2, height], fill=(40, 180, 80, 60))

        # Draw waveform
        step = max(1, len(samples) // width)
        mid  = height // 2

        for x in range(width):
            idx_start = x * step
            idx_end   = min(idx_start + step, len(samples))
            if idx_start >= len(samples):
                break
            chunk = samples[idx_start:idx_end]
            peak  = float(np.max(np.abs(chunk))) if len(chunk) > 0 else 0.0
            amp   = int(peak * (height // 2 - 4))
            draw.line([(x, mid - amp), (x, mid + amp)], fill=(220, 220, 220, 255))

        # Draw cut lines (white vertical)
        for iv in keep_intervals:
            for t in (iv["start_s"], iv["end_s"]):
                x = int(t / total_s * width)
                draw.line([(x, 0), (x, height)], fill=(255, 255, 0, 200), width=1)

        # Center line
        draw.line([(0, mid), (width, mid)], fill=(80, 80, 80, 200), width=1)

        # Time labels every 5s
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 11)
        except Exception:
            font = ImageFont.load_default()

        interval = max(1, int(total_s / 20))
        for t in range(0, int(total_s) + 1, interval):
            x = int(t / total_s * width)
            draw.text((x + 2, 2), f"{t}s", fill=(180, 180, 180), font=font)

        # Legend
        draw.rectangle([8, height - 20, 22, height - 8], fill=(180, 40, 40, 200))
        draw.text((26, height - 20), "Silence", fill=(200, 200, 200), font=font)
        draw.rectangle([90, height - 20, 104, height - 8], fill=(40, 180, 80, 200))
        draw.text((108, height - 20), "Speech kept", fill=(200, 200, 200), font=font)
        draw.rectangle([210, height - 20, 224, height - 8], fill=(255, 255, 0, 200))
        draw.text((228, height - 20), "Cut points", fill=(200, 200, 200), font=font)

        # Stats
        n_cuts  = len(keep_intervals)
        sil_dur = sum(s["duration_s"] for s in silences)
        stats   = (f"  {n_cuts} segments | "
                   f"{sil_dur:.1f}s silence removed | "
                   f"threshold: {keep_intervals[0].get('threshold_db', '?')}dB" if keep_intervals else "")
        draw.text((8, height - 36), stats, fill=(150, 150, 150), font=font)

        img.save(output_png, "PNG")
        return output_png

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_duration(self, audio_path: str) -> float:
        result = subprocess.run(
            [self.ffprobe, "-v", "quiet", "-show_entries",
             "format=duration", "-of", "csv=p=0", audio_path],
            capture_output=True, text=True
        )
        try:
            return float(result.stdout.strip())
        except ValueError:
            return 0.0

    def _read_wav_samples(self, audio_path: str):
        """Read WAV as normalized float32 numpy array."""
        try:
            with open(audio_path, "rb") as f:
                data = f.read()

            # Parse RIFF WAV header
            if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
                return None, 0

            pos = 12
            sample_rate = 16000
            bits = 16
            channels = 1
            while pos < len(data) - 8:
                chunk_id   = data[pos:pos+4]
                chunk_size = struct.unpack_from("<I", data, pos+4)[0]
                pos += 8
                if chunk_id == b"fmt ":
                    channels    = struct.unpack_from("<H", data, pos+2)[0]
                    sample_rate = struct.unpack_from("<I", data, pos+4)[0]
                    bits        = struct.unpack_from("<H", data, pos+14)[0]
                elif chunk_id == b"data":
                    raw = data[pos:pos+chunk_size]
                    if bits == 16:
                        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                    elif bits == 8:
                        samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128.0
                    else:
                        return None, 0
                    if channels > 1:
                        samples = samples.reshape(-1, channels).mean(axis=1)
                    return samples, sample_rate
                pos += chunk_size + (chunk_size % 2)

        except Exception:
            pass
        return None, 0
