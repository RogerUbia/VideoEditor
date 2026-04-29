"""
TimelineEditor — bidirectional sync between pipeline output and timeline clips.
Converts: script segments + SRT files → TimelineClip list for the canvas.
Also converts clip edits back → updated segment timings.
"""
from __future__ import annotations

import re
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # avoid circular imports; TimelineClip imported at runtime


# ── Track indices ─────────────────────────────────────────────────────────────

TRACK_VIDEO = 0
TRACK_FX    = 1
TRACK_MUSIC = 2
TRACK_CA    = 3
TRACK_ES    = 4
TRACK_EN    = 5

TRACK_COLORS = {
    TRACK_VIDEO: "#3D2454",
    TRACK_FX:    "#2A1A40",
    TRACK_MUSIC: "#1A3A5C",
    TRACK_CA:    "#1A4731",
    TRACK_ES:    "#1A3A5C",
    TRACK_EN:    "#2C1A5C",
}

EFFECT_COLORS = {
    "zoom_in":  "#5C3BE4",
    "zoom_out": "#7B4CF0",
    "shake":    "#8B4513",
    "blur":     "#1A5C5C",
    "vignette": "#2C2C1A",
    "none":     "#3D2454",
}

SUB_TRACK_COLORS = {
    TRACK_CA: "#1A4731",
    TRACK_ES: "#1A3A5C",
    TRACK_EN: "#2C1A5C",
}


# ── SRT parser ────────────────────────────────────────────────────────────────

def parse_srt(path: str) -> list[dict]:
    """Parse an SRT file into a list of {index, start_s, end_s, text} dicts."""
    if not path or not os.path.exists(path):
        return []

    entries = []
    try:
        content = open(path, encoding="utf-8-sig").read()
    except Exception:
        try:
            content = open(path, encoding="utf-8").read()
        except Exception:
            return []

    blocks = re.split(r"\n\n+", content.strip())
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        try:
            index = int(lines[0].strip())
            tc_parts = lines[1].split(" --> ")
            start_s = _tc_to_s(tc_parts[0].strip())
            end_s   = _tc_to_s(tc_parts[1].strip())
            text    = " ".join(lines[2:]).strip()
            entries.append({
                "index":   index,
                "start_s": start_s,
                "end_s":   end_s,
                "text":    text,
            })
        except (ValueError, IndexError):
            continue
    return entries


def _tc_to_s(tc: str) -> float:
    """Convert SRT timecode HH:MM:SS,mmm to seconds."""
    tc = tc.replace(",", ".")
    parts = tc.split(":")
    try:
        h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
        return h * 3600 + m * 60 + s
    except (ValueError, IndexError):
        return 0.0


def _t2s(t: str) -> float:
    """Convert segment time string to seconds."""
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


def _s_to_t(s: float) -> str:
    """Convert seconds to HH:MM:SS.mmm string."""
    ms = int((s % 1) * 1000)
    total = int(s)
    h = total // 3600
    m = (total % 3600) // 60
    sec = total % 60
    return f"{h:02d}:{m:02d}:{sec:02d}.{ms:03d}"


# ── Main converter ────────────────────────────────────────────────────────────

def load_pipeline_output(outputs: dict, duration_s: float) -> list:
    """
    Convert pipeline output dict to a list of TimelineClip objects.
    Import TimelineClip lazily to avoid circular imports.
    """
    from gui.timeline_panel import TimelineClip

    clips: list[TimelineClip] = []

    script    = outputs.get("script", {}) or {}
    segments  = script.get("segments", [])
    subtitles = outputs.get("subtitles", {}) or {}

    # ── VIDEO + FX + MUSIC clips from segments ────────────────────────────────
    for seg in segments:
        if seg.get("is_duplicate", False):
            continue

        seg_id  = seg.get("id", "")
        start_s = _t2s(seg.get("time_start", "0:00"))
        end_s   = _t2s(seg.get("time_end",   "0:05"))
        if end_s <= start_s:
            end_s = start_s + 3.0

        content = seg.get("content", "")[:30] or f"Seg {seg.get('order', 0) + 1}"

        # VIDEO clip
        vfx      = seg.get("video_effect", {}).get("type", "none")
        zoom_en  = seg.get("zoom", {}).get("enabled", False)
        pip_en   = seg.get("pip",  {}).get("enabled", False)
        ti_type  = seg.get("transition_in",  {}).get("type", "none")
        to_type  = seg.get("transition_out", {}).get("type", "none")
        ti_dur   = seg.get("transition_in",  {}).get("duration_s", 0.5)
        to_dur   = seg.get("transition_out", {}).get("duration_s", 0.5)
        mus_en   = seg.get("music", {}).get("enabled", False)
        txt_en   = seg.get("text_overlay", {}).get("enabled", False)

        vid_color = EFFECT_COLORS.get(vfx, EFFECT_COLORS["none"])

        clips.append(TimelineClip(
            id=seg_id,
            track=TRACK_VIDEO,
            start_s=start_s,
            end_s=end_s,
            label=content,
            color=vid_color,
            effect_type=vfx,
            has_transition_in=(ti_type not in ("none", "cut", "")),
            has_transition_out=(to_type not in ("none", "cut", "")),
            has_pip=pip_en,
            has_zoom=zoom_en,
            transition_in_dur=ti_dur,
            transition_out_dur=to_dur,
            is_duplicate=False,
            is_resizable=True,
            segment_data=seg,
        ))

        # FX chip: only if there are visible effects
        fx_parts = []
        if zoom_en:
            factor = seg.get("zoom", {}).get("factor", 1.0)
            fx_parts.append(f"⊕ ×{factor:.1f}")
        if vfx != "none":
            fx_parts.append(vfx.replace("_", " "))
        if pip_en:
            fx_parts.append("⊡PiP")
        if ti_type not in ("none", "cut", ""):
            fx_parts.append(f"↓{ti_type}")
        if txt_en:
            txt = seg.get("text_overlay", {}).get("text", "")[:12]
            fx_parts.append(f"T:{txt}")

        if fx_parts:
            clips.append(TimelineClip(
                id=f"{seg_id}_fx",
                track=TRACK_FX,
                start_s=start_s,
                end_s=end_s,
                label="  ".join(fx_parts),
                color="#4A2080",
                effect_type=vfx,
                is_resizable=False,
                segment_data=seg,
            ))

        # MUSIC clip
        if mus_en:
            music_file = seg.get("music", {}).get("file_path", "")
            music_label = f"♪ {os.path.basename(music_file)[:20]}" if music_file else "♪ música"
            clips.append(TimelineClip(
                id=f"{seg_id}_music",
                track=TRACK_MUSIC,
                start_s=start_s,
                end_s=end_s,
                label=music_label,
                color=TRACK_COLORS[TRACK_MUSIC],
                is_resizable=False,
                segment_data=seg,
            ))

    # ── Fallback: full-duration video clip if no segments ────────────────────
    if not any(c.track == TRACK_VIDEO for c in clips) and duration_s > 0:
        clips.append(TimelineClip(
            id="full_video",
            track=TRACK_VIDEO,
            start_s=0.0,
            end_s=duration_s,
            label="Video (sin segmentos)",
            color=EFFECT_COLORS["none"],
            is_resizable=False,
        ))

    # ── SUBTITLE clips from SRT files ─────────────────────────────────────────
    sub_track_map = {
        "ca": TRACK_CA,
        "es": TRACK_ES,
        "en": TRACK_EN,
    }
    for lang, track_idx in sub_track_map.items():
        srt_path = subtitles.get(lang, "")
        entries  = parse_srt(srt_path)
        color    = SUB_TRACK_COLORS[track_idx]
        for entry in entries:
            clips.append(TimelineClip(
                id=f"sub_{lang}_{entry['index']}",
                track=track_idx,
                start_s=entry["start_s"],
                end_s=entry["end_s"],
                label=entry["text"][:28],
                color=color,
                is_resizable=False,
                segment_data={"subtitle_text": entry["text"], "lang": lang},
            ))

    return clips


# ── Bidirectional sync ────────────────────────────────────────────────────────

def clips_to_segment_timings(clips: list) -> dict[str, tuple[float, float]]:
    """
    Extract updated timings from VIDEO track clips.
    Returns {segment_id: (new_start_s, new_end_s)}.
    """
    timings = {}
    for clip in clips:
        if clip.track == TRACK_VIDEO and clip.is_resizable:
            timings[clip.id] = (clip.start_s, clip.end_s)
    return timings


def apply_timings_to_segments(
    segments: list[dict],
    timings: dict[str, tuple[float, float]],
) -> list[dict]:
    """Update segment time_start/time_end from clip timings."""
    for seg in segments:
        seg_id = seg.get("id", "")
        if seg_id in timings:
            new_start, new_end = timings[seg_id]
            seg["time_start"] = _s_to_t(new_start)
            seg["time_end"]   = _s_to_t(new_end)
    return segments
