import re
from datetime import timedelta


class SubtitleGenerator:
    def __init__(self):
        pass

    def generate_srt(self, segments: list[dict], language: str = "ca") -> str:
        entries = []
        index = 1
        for seg in segments:
            content = seg.get("transcription", "").strip()
            if not content:
                content = seg.get("content", "").strip()
            if not content:
                continue
            start_s = self._time_to_seconds(seg.get("time_start", "00:00:00.000"))
            end_s = self._time_to_seconds(seg.get("time_end", "00:00:05.000"))
            if end_s <= start_s:
                end_s = start_s + 3.0
            # Split long content into ~42-char lines
            lines = self._wrap_text(content, max_chars=42)
            text = "\n".join(lines)
            entries.append(self._format_entry(index, start_s, end_s, text))
            index += 1
        return "\n".join(entries)

    def translate_srt(
        self,
        srt_content: str,
        source_lang: str,
        target_lang: str,
        translate_fn  # callable(text: str, src: str, dst: str) -> str
    ) -> str:
        blocks = self._parse_srt(srt_content)
        translated_blocks = []
        for block in blocks:
            try:
                translated_text = translate_fn(block["text"], source_lang, target_lang)
            except Exception:
                translated_text = block["text"]
            translated_blocks.append({
                "index": block["index"],
                "start": block["start"],
                "end": block["end"],
                "text": translated_text.strip()
            })
        return self._blocks_to_srt(translated_blocks)

    def _parse_srt(self, srt_content: str) -> list[dict]:
        blocks = []
        raw_blocks = re.split(r"\n\n+", srt_content.strip())
        for raw in raw_blocks:
            lines = raw.strip().split("\n")
            if len(lines) < 3:
                continue
            try:
                index = int(lines[0].strip())
                timecode = lines[1].strip()
                text = "\n".join(lines[2:])
                blocks.append({"index": index, "start": timecode.split(" --> ")[0],
                               "end": timecode.split(" --> ")[1], "text": text})
            except (ValueError, IndexError):
                continue
        return blocks

    def _blocks_to_srt(self, blocks: list[dict]) -> str:
        parts = []
        for b in blocks:
            parts.append(f"{b['index']}\n{b['start']} --> {b['end']}\n{b['text']}")
        return "\n\n".join(parts) + "\n"

    def _format_entry(self, index: int, start_s: float, end_s: float, text: str) -> str:
        start_tc = self._seconds_to_srt_time(start_s)
        end_tc = self._seconds_to_srt_time(end_s)
        return f"{index}\n{start_tc} --> {end_tc}\n{text}\n"

    @staticmethod
    def _seconds_to_srt_time(seconds: float) -> str:
        ms = int((seconds % 1) * 1000)
        td = timedelta(seconds=int(seconds))
        h, remainder = divmod(td.seconds, 3600)
        m, s = divmod(remainder, 60)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    @staticmethod
    def _time_to_seconds(time_str: str) -> float:
        time_str = time_str.replace(",", ".")
        parts = time_str.split(":")
        try:
            if len(parts) == 3:
                h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
                return h * 3600 + m * 60 + s
            elif len(parts) == 2:
                m, s = int(parts[0]), float(parts[1])
                return m * 60 + s
        except (ValueError, IndexError):
            pass
        return 0.0

    @staticmethod
    def _wrap_text(text: str, max_chars: int = 42) -> list[str]:
        words = text.split()
        lines = []
        current = ""
        for word in words:
            if len(current) + len(word) + 1 <= max_chars:
                current = (current + " " + word).strip()
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines if lines else [text]

    def save_srt(self, content: str, path: str):
        with open(path, "w", encoding="utf-8-sig") as f:
            f.write(content)
