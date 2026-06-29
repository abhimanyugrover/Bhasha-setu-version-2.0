"""
Bhasha-Setu — Whisper Transcription Service
Extracts speech from video in ANY language with word-level timestamps
using faster-whisper (CTranslate2 backend).
Generates SRT subtitle files from the timestamps.
Results are cached by file hash to avoid re-transcribing.
"""

import os
import json
import hashlib
import logging
from typing import Callable, Optional

from pipeline.config import CACHE_DIR

log = logging.getLogger(__name__)
os.makedirs(CACHE_DIR, exist_ok=True)

# ── Lazy-loaded singleton Whisper model ──────────────────────────────────────
_model = None


def _get_model():
    """Load the faster-whisper model once and reuse it."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        from pipeline.config import WHISPER_MODEL
        import os

        # Auto-detect GPU: use CUDA if available, else CPU
        device = os.environ.get("WHISPER_DEVICE", "cpu")
        compute = os.environ.get("WHISPER_COMPUTE", "int8")

        # Fallback: try CUDA detection if env vars not set
        if device == "cpu":
            try:
                import torch
                if torch.cuda.is_available():
                    device = "cuda"
                    compute = "float16"
            except ImportError:
                pass

        log.info(f"Loading Whisper model: {WHISPER_MODEL} (device={device}, compute={compute})")
        _model = WhisperModel(WHISPER_MODEL, compute_type=compute, device=device)
    return _model


def _file_hash(path: str) -> str:
    """Compute MD5 hash of a file for cache keying."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):   # 1 MB chunks
            h.update(chunk)
    return h.hexdigest()


def _cache_path(file_hash: str) -> str:
    """Return the JSON cache file path for a given file hash."""
    return os.path.join(CACHE_DIR, f"whisper_{file_hash}.json")


# ─────────────────────────────────────────────────────────────────────────────
#  TRANSCRIPTION
# ─────────────────────────────────────────────────────────────────────────────

def transcribe_video(
    video_path: str,
    progress_cb=None,
    return_timestamps: bool = False,
) -> tuple:
    """
    Transcribe speech from a local video/audio file in ANY language.

    Args:
        video_path:        Local path to the video or audio file.
        progress_cb:       Optional callable(elapsed_pct: float, status: str).
        return_timestamps: If True, return word-level timestamp data.

    Returns:
        (transcript: str, word_items: list, detected_language_code: str)

        word_items format (only populated when return_timestamps=True):
        [{'content': str, 'start_time': float, 'end_time': float,
          'confidence': float}, ...]
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    # 1. Check cache
    fhash = _file_hash(video_path)
    cache_file = _cache_path(fhash)

    if os.path.exists(cache_file):
        log.info(f"Transcribe cache hit: {cache_file}")
        with open(cache_file, "r", encoding="utf-8") as f:
            cached = json.load(f)
        transcript = cached["transcript"]
        detected   = cached.get("detected_language_code", "en")
        word_items = cached.get("word_items", []) if return_timestamps else []
        return transcript, word_items, detected

    # 2. Load model
    if progress_cb:
        progress_cb(5.0, "Loading Whisper model…")
    model = _get_model()

    # 3. Transcribe
    if progress_cb:
        progress_cb(15.0, "Transcribing audio…")

    segments_gen, info = model.transcribe(
        video_path,
        word_timestamps=return_timestamps,
        beam_size=5,
    )

    detected_lang = info.language          # short ISO code, e.g. "en", "hi"
    log.info(
        f"Whisper detected language: {detected_lang} "
        f"(probability {info.language_probability:.2f})"
    )

    # 4. Collect segments
    transcript_parts = []
    word_items = []
    segments_list = list(segments_gen)      # materialize generator
    total_segments = len(segments_list)

    for idx, segment in enumerate(segments_list):
        transcript_parts.append(segment.text.strip())

        # 5. Word-level timestamps
        if return_timestamps and segment.words:
            for w in segment.words:
                word_items.append({
                    "content":    w.word.strip(),
                    "start_time": round(w.start, 3),
                    "end_time":   round(w.end, 3),
                    "confidence": round(w.probability, 4),
                })

        if progress_cb and total_segments > 0:
            pct = 15.0 + (idx + 1) / total_segments * 80.0
            progress_cb(min(95.0, pct), f"Processing segment {idx + 1}/{total_segments}")

    transcript = " ".join(transcript_parts)

    # 6. Save to cache
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({
            "video_path":             video_path,
            "file_hash":              fhash,
            "transcript":             transcript,
            "word_items":             word_items,
            "detected_language_code": detected_lang,
        }, f, ensure_ascii=False, indent=2)

    log.info(
        f"Transcription complete. "
        f"Detected: {detected_lang} | {len(transcript)} chars | {len(word_items)} words."
    )
    if progress_cb:
        progress_cb(100.0, "Transcription complete")

    # 7. Return
    return transcript, (word_items if return_timestamps else []), detected_lang


# ─────────────────────────────────────────────────────────────────────────────
#  SRT GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def _seconds_to_srt_time(s: float) -> str:
    h   = int(s) // 3600
    m   = (int(s) % 3600) // 60
    sec = int(s) % 60
    ms  = int(round((s - int(s)) * 1000))
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def generate_srt_file(
    word_items: list,
    output_path: str,
    words_per_subtitle: int = 8,
    max_duration: float = 5.0,
) -> str:
    """
    Generate an SRT subtitle file from word-level timestamps.

    Args:
        word_items:         List of {content, start_time, end_time} dicts.
        output_path:        Where to write the .srt file.
        words_per_subtitle: Max words per subtitle block.
        max_duration:       Max seconds per subtitle block.

    Returns:
        output_path
    """
    if not word_items:
        log.warning("No word items - writing empty SRT.")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("")
        return output_path

    blocks      = []
    block_words = []
    block_start = None

    for item in word_items:
        if block_start is None:
            block_start = item["start_time"]

        block_words.append(item["content"])
        block_end = item["end_time"]

        should_break = (
            len(block_words) >= words_per_subtitle or
            (block_end - block_start) >= max_duration
        )

        if should_break:
            blocks.append({
                "start": block_start,
                "end":   block_end,
                "text":  " ".join(block_words),
            })
            block_words = []
            block_start = None

    if block_words and block_start is not None:
        blocks.append({
            "start": block_start,
            "end":   word_items[-1]["end_time"],
            "text":  " ".join(block_words),
        })

    lines = []
    for i, block in enumerate(blocks, 1):
        lines.append(str(i))
        lines.append(f"{_seconds_to_srt_time(block['start'])} --> {_seconds_to_srt_time(block['end'])}")
        lines.append(block["text"])
        lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    log.info(f"SRT written: {output_path} ({len(blocks)} subtitle blocks)")
    return output_path
