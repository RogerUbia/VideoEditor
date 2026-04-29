import os
import json
import subprocess
from core.audio_analyzer import AudioAnalyzer


class SilenceRemover:
    def __init__(self, config: dict):
        self.ffmpeg  = config.get("ffmpeg_path",  "ffmpeg")
        self.ffprobe = config.get("ffprobe_path", "ffprobe")
        self._analyzer = AudioAnalyzer(self.ffmpeg, self.ffprobe)

    def get_duration(self, video_path: str) -> float:
        result = subprocess.run(
            [self.ffprobe, "-v", "quiet", "-show_entries",
             "format=duration", "-of", "csv=p=0", video_path],
            capture_output=True, text=True
        )
        try:
            return float(result.stdout.strip())
        except ValueError:
            pass
        # Fallback via streams
        result = subprocess.run(
            [self.ffprobe, "-v", "quiet", "-print_format", "json",
             "-show_streams", video_path],
            capture_output=True, text=True
        )
        try:
            data = json.loads(result.stdout)
            for s in data.get("streams", []):
                if "duration" in s:
                    return float(s["duration"])
        except Exception:
            pass
        return 0.0

    def extract_audio(self, video_path: str, output_path: str) -> str:
        subprocess.run(
            [self.ffmpeg, "-y", "-i", video_path,
             "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
             output_path],
            capture_output=True, check=True
        )
        return output_path

    def cut_video(
        self,
        input_path: str,
        keep_intervals: list[dict],
        output_path: str,
        temp_dir: str,
        progress_callback=None,
    ) -> str:
        os.makedirs(temp_dir, exist_ok=True)
        segment_paths = []
        total = len(keep_intervals)

        for i, iv in enumerate(keep_intervals):
            seg_path = os.path.join(temp_dir, f"seg_{i:04d}.mp4")

            # OUTPUT seeking (-ss after -i) = frame-accurate, no keyframe drift
            # Re-encode to avoid audio duplication at cut boundaries
            result = subprocess.run(
                [self.ffmpeg, "-y",
                 "-i", input_path,
                 "-ss", str(iv["start_s"]),
                 "-to", str(iv["end_s"]),
                 "-avoid_negative_ts", "make_zero",
                 "-vf", "setpts=PTS-STARTPTS",
                 "-af", "asetpts=PTS-STARTPTS",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                 "-c:a", "aac", "-b:a", "192k",
                 seg_path],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Cut segment {i} failed:\n{result.stderr[-600:]}"
                )
            segment_paths.append(seg_path)
            if progress_callback:
                progress_callback(int((i + 1) / total * 80))

        # Concatenate — all segments already start at 0
        concat_list = os.path.join(temp_dir, "concat_list.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for p in segment_paths:
                f.write(f"file '{p.replace(chr(92), '/')}'\n")

        result = subprocess.run(
            [self.ffmpeg, "-y",
             "-f", "concat", "-safe", "0",
             "-i", concat_list,
             "-c", "copy",
             "-reset_timestamps", "1",
             output_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Concat failed:\n{result.stderr[-600:]}")

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
        threshold_db: float  = -35.0,
        min_duration_ms: int = 600,
        margin_ms: int       = 150,
        min_segment_ms: int  = 1000,
        progress_callback=None,
        waveform_png_path: str = "",
    ) -> tuple[str, list[dict], str]:
        """
        Returns: (output_video_path, keep_intervals, waveform_png_path)
        """
        os.makedirs(temp_dir, exist_ok=True)
        audio_path = os.path.join(temp_dir, "audio_for_silence.wav")
        self.extract_audio(video_path, audio_path)

        duration_s     = self.get_duration(video_path)
        min_duration_s = min_duration_ms / 1000.0
        margin_s       = margin_ms / 1000.0
        min_segment_s  = min_segment_ms / 1000.0

        # FFmpeg-based detection (replaces pydub)
        silences = self._analyzer.detect_silences_ffmpeg(
            audio_path,
            threshold_db=threshold_db,
            min_duration_s=min_duration_s,
        )

        keep_intervals = self._analyzer.compute_keep_intervals(
            silences,
            total_duration_s=duration_s,
            margin_s=margin_s,
            min_segment_s=min_segment_s,
        )

        # Generate waveform visualization
        png_out = waveform_png_path or os.path.join(temp_dir, "waveform_analysis.png")
        try:
            self._analyzer.generate_waveform_png(
                audio_path, silences, keep_intervals, png_out
            )
        except Exception as e:
            print(f"Waveform PNG failed: {e}")
            png_out = ""

        # Cut video with accurate output seeking + re-encode
        output = self.cut_video(
            video_path, keep_intervals, output_path, temp_dir, progress_callback
        )

        try:
            os.remove(audio_path)
        except OSError:
            pass

        return output, keep_intervals, png_out
