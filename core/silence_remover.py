import os
import json
import subprocess
import tempfile
from pathlib import Path
from pydub import AudioSegment
from pydub.silence import detect_silence


class SilenceRemover:
    def __init__(self, config: dict):
        self.ffmpeg = config.get("ffmpeg_path", "ffmpeg")
        self.ffprobe = config.get("ffprobe_path", "ffprobe")

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

    def extract_audio(self, video_path: str, output_path: str) -> str:
        subprocess.run(
            [self.ffmpeg, "-y", "-i", video_path,
             "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
             output_path],
            capture_output=True, check=True
        )
        return output_path

    def detect_silences(
        self,
        audio_path: str,
        threshold_db: float = -40.0,
        min_duration_ms: int = 500
    ) -> list[dict]:
        audio = AudioSegment.from_file(audio_path)
        silent_ranges = detect_silence(
            audio,
            min_silence_len=min_duration_ms,
            silence_thresh=threshold_db,
            seek_step=10
        )
        return [
            {"start_ms": s, "end_ms": e, "duration_ms": e - s}
            for s, e in silent_ranges
        ]

    def compute_keep_intervals(
        self,
        silences: list[dict],
        total_duration_ms: int,
        margin_ms: int = 100
    ) -> list[dict]:
        keep = []
        cursor = 0
        for silence in silences:
            end_keep = max(cursor, silence["start_ms"] + margin_ms)
            if end_keep > cursor:
                keep.append({
                    "start_ms": cursor,
                    "end_ms": end_keep,
                    "start_s": cursor / 1000.0,
                    "end_s": end_keep / 1000.0,
                    "duration_s": (end_keep - cursor) / 1000.0
                })
            cursor = max(cursor, silence["end_ms"] - margin_ms)
        # Final segment
        if cursor < total_duration_ms:
            keep.append({
                "start_ms": cursor,
                "end_ms": total_duration_ms,
                "start_s": cursor / 1000.0,
                "end_s": total_duration_ms / 1000.0,
                "duration_s": (total_duration_ms - cursor) / 1000.0
            })
        return [k for k in keep if k["duration_s"] > 0.05]

    def cut_video(
        self,
        input_path: str,
        keep_intervals: list[dict],
        output_path: str,
        temp_dir: str,
        progress_callback=None
    ) -> str:
        os.makedirs(temp_dir, exist_ok=True)
        segment_paths = []
        total = len(keep_intervals)

        for i, interval in enumerate(keep_intervals):
            seg_path = os.path.join(temp_dir, f"seg_{i:04d}.mp4")
            subprocess.run(
                [self.ffmpeg, "-y",
                 "-ss", str(interval["start_s"]),
                 "-i", input_path,
                 "-t", str(interval["duration_s"]),
                 "-c", "copy",
                 seg_path],
                capture_output=True, check=True
            )
            segment_paths.append(seg_path)
            if progress_callback:
                progress_callback(int((i + 1) / total * 80))

        concat_list = os.path.join(temp_dir, "concat_list.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for p in segment_paths:
                f.write(f"file '{p.replace(chr(92), '/')}'\n")

        subprocess.run(
            [self.ffmpeg, "-y",
             "-f", "concat", "-safe", "0",
             "-i", concat_list,
             "-c", "copy",
             output_path],
            capture_output=True, check=True
        )

        if progress_callback:
            progress_callback(100)

        for p in segment_paths:
            try:
                os.remove(p)
            except OSError:
                pass

        return output_path

    def process(
        self,
        video_path: str,
        output_path: str,
        temp_dir: str,
        threshold_db: float = -40.0,
        min_duration_ms: int = 500,
        margin_ms: int = 100,
        progress_callback=None
    ) -> tuple[str, list[dict]]:
        audio_path = os.path.join(temp_dir, "audio_for_silence.wav")
        self.extract_audio(video_path, audio_path)

        duration_s = self.get_duration(video_path)
        total_ms = int(duration_s * 1000)

        silences = self.detect_silences(audio_path, threshold_db, min_duration_ms)
        keep_intervals = self.compute_keep_intervals(silences, total_ms, margin_ms)

        output = self.cut_video(video_path, keep_intervals, output_path, temp_dir, progress_callback)

        try:
            os.remove(audio_path)
        except OSError:
            pass

        return output, keep_intervals
