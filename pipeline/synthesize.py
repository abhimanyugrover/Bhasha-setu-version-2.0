"""
Bhasha-Setu — Speech Synthesis Service
Two-engine strategy with per-chunk progress callbacks.

Engine strategy:
  edge  → Microsoft edge-tts Neural → Hindi, Tamil, Telugu, Kannada, Malayalam,
                                       Bengali, Marathi, Gujarati, Urdu
  gtts  → Google TTS               → Punjabi, Odia, Assamese

FIX: Fallback now uses the correct language config (lang_cfg) instead of
hardcoded Hindi ("hi"), so a failed engine falls back in the same language.
"""

import os
import asyncio
import logging
import subprocess
import tempfile
from typing import Callable, Optional

from pipeline.config import (
    LANGUAGES,
    EDGE_CHUNK_CHARS,
    GTTS_CHUNK_CHARS,
)

log = logging.getLogger(__name__)


def _chunk_text(text: str, max_chars: int) -> list:
    """Split text into chunks at sentence boundaries."""
    if len(text) <= max_chars:
        return [text]

    chunks, current = [], ""
    normalized = text.replace("| ", "|\n").replace(". ", ".\n")

    for sentence in normalized.splitlines():
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 <= max_chars:
            current = (current + " " + sentence).strip()
        else:
            if current:
                chunks.append(current)
            current = sentence

    if current:
        chunks.append(current)
    return chunks


def _concat_mp3_files(mp3_files: list, output_path: str) -> None:
    """Concatenate multiple MP3 chunks into one using FFmpeg."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        list_file = f.name
        for p in mp3_files:
            abs_path = os.path.abspath(p).replace("\\", "\\\\")
            f.write(f"file '{abs_path}'\n")
    try:
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", list_file, "-c", "copy", output_path
        ], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        log.error(f"Concat failed: {e.stderr.decode()}")
        raise
    finally:
        if os.path.exists(list_file):
            os.unlink(list_file)


# ── EDGE-TTS ─────────────────────────────────────────────────────────────────

async def _edge_tts_chunk_async(text: str, voice: str, out_path: str, pitch_hz: str = "+0Hz") -> None:
    import edge_tts
    comm = edge_tts.Communicate(text, voice, pitch=pitch_hz)
    await comm.save(out_path)


def _pitch_percent_to_hz(pitch_percent: int) -> str:
    hz = int(round(pitch_percent * 2))
    hz = max(-200, min(200, hz))
    return f"{'+' if hz >= 0 else ''}{hz}Hz"


def _synthesize_edge(
    text: str,
    lang_cfg: dict,
    output_mp3: str,
    progress_cb=None,
    pitch_percent: int = 0,
) -> str:
    voice    = lang_cfg["edge_voice"]
    pitch_hz = _pitch_percent_to_hz(pitch_percent)
    chunks   = _chunk_text(text, EDGE_CHUNK_CHARS)
    total    = len(chunks)
    log.info(f"edge-tts | voice={voice} | pitch={pitch_hz} | {total} chunk(s)")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    chunk_files = []

    try:
        for i, chunk in enumerate(chunks):
            if progress_cb:
                progress_cb(i, total)
            tmp = output_mp3.replace(".mp3", f"_chunk{i}.mp3")
            loop.run_until_complete(_edge_tts_chunk_async(chunk, voice, tmp, pitch_hz))
            chunk_files.append(tmp)
    finally:
        loop.close()

    if progress_cb:
        progress_cb(total, total)

    _concat_mp3_files(chunk_files, output_mp3)
    for f in chunk_files:
        try: os.remove(f)
        except Exception: pass
    return output_mp3


# ── GTTS ──────────────────────────────────────────────────────────────────────

def _synthesize_gtts(
    text: str,
    lang_cfg: dict,
    output_mp3: str,
    progress_cb=None,
    pitch_percent: int = 0,   # gTTS does not support pitch control
) -> str:
    from gtts import gTTS, lang as gtts_lang

    target_lang     = lang_cfg.get("gtts_lang", "hi")
    supported_langs = gtts_lang.tts_langs()

    if target_lang not in supported_langs:
        log.warning(f"gTTS: '{target_lang}' not supported. Falling back to Hindi ('hi').")
        target_lang = "hi"

    chunks      = _chunk_text(text, GTTS_CHUNK_CHARS)
    total       = len(chunks)
    chunk_files = []

    for i, chunk in enumerate(chunks):
        if progress_cb:
            progress_cb(i, total)
        tmp = output_mp3.replace(".mp3", f"_chunk{i}.mp3")
        gTTS(text=chunk, lang=target_lang, slow=False).save(tmp)
        chunk_files.append(tmp)

    if progress_cb:
        progress_cb(total, total)

    _concat_mp3_files(chunk_files, output_mp3)
    for f in chunk_files:
        try: os.remove(f)
        except Exception: pass
    return output_mp3


# ── PUBLIC API ────────────────────────────────────────────────────────────────

def synthesize_speech(
    text: str,
    output_mp3: str,
    lang_name: str,
    progress_cb=None,
    pitch_percent: int = 0,
    gender: str = "Female",
) -> str:
    """
    Synthesize speech for the given text and language.

    Args:
        text:          Text to synthesize.
        output_mp3:    Output MP3 file path.
        lang_name:     Language name from LANGUAGES registry (e.g. "Hindi").
        progress_cb:   Optional callable(chunk_index, total_chunks).
        pitch_percent: Pitch offset percent (-20 to +20).
        gender:        Estimated speaker gender ("Male" or "Female").

    Returns:
        output_mp3 path
    """
    if not text or not text.strip():
        raise ValueError("TTS text is empty.")

    lang_cfg = LANGUAGES[lang_name].copy()  # copy config to avoid mutating registry globally
    engine   = lang_cfg["tts"]

    # Swap voice dynamically for edge-tts based on gender detection
    if engine == "edge":
        if gender == "Male" and "edge_male_voice" in lang_cfg:
            log.info(f"Gender classification: MALE. Swapping edge voice to: {lang_cfg['edge_male_voice']}")
            lang_cfg["edge_voice"] = lang_cfg["edge_male_voice"]
        elif gender == "Female" and "edge_female_voice" in lang_cfg:
            log.info(f"Gender classification: FEMALE. Using edge voice: {lang_cfg['edge_female_voice']}")
            lang_cfg["edge_voice"] = lang_cfg["edge_female_voice"]

    try:
        if engine == "edge":
            return _synthesize_edge(text, lang_cfg, output_mp3, progress_cb, pitch_percent)
        elif engine == "gtts":
            return _synthesize_gtts(text, lang_cfg, output_mp3, progress_cb, pitch_percent)
        else:
            raise ValueError(f"Unknown TTS engine: {engine!r}")
    except Exception as e:
        log.error(f"TTS Synthesis with {engine} failed: {e}")
        # Dynamic fallback to gtts using standard configurations
        if engine == "edge" and lang_cfg.get("gtts_lang"):
            log.info(f"Attempting fallback to gTTS engine for lang: {lang_cfg['gtts_lang']}")
            fallback_cfg = lang_cfg.copy()
            fallback_cfg["tts"] = "gtts"
            try:
                return _synthesize_gtts(text, fallback_cfg, output_mp3, progress_cb, pitch_percent)
            except Exception as fe:
                log.error(f"TTS Fallback engine also failed: {fe}")
                raise RuntimeError(f"All TTS engines failed for {lang_name}. Last error: {e}") from fe
        raise RuntimeError(f"All TTS engines failed for {lang_name}. Last error: {e}")
