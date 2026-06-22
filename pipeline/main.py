"""
Bhasha-Setu — Pipeline Orchestrator
Runs all 5 stages with granular sub-stage progress reporting.
Supports: SRT generation, preview mode, any-source → any-target.

Fully open-source stack — no AWS services:
  - Whisper (faster-whisper)  for transcription  (auto-detects language)
  - NLLB-200                  for translation
  - edge-tts / gTTS           for speech synthesis
"""

import os
import uuid
import logging
import logging.handlers

from pipeline.config import (
    OUTPUT_DIR, LOG_DIR, LANGUAGES,
    WHISPER_TO_NLLB,
)
from pipeline.transcribe import transcribe_video
from pipeline.translate  import translate_text
from pipeline.synthesize import synthesize_speech
from pipeline.mux        import mux

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(LOG_DIR,    exist_ok=True)


def _setup_logging():
    fmt  = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        root.addHandler(ch)
        fh = logging.handlers.RotatingFileHandler(
            os.path.join(LOG_DIR, "pipeline.log"),
            maxBytes=5_000_000, backupCount=3,
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)


log = logging.getLogger(__name__)


def run_transcribe_and_translate(
    video_path:          str  = "",
    target_language:     str  = "",
    progress_cb=None,
    generate_srt:        bool = False,
    video_url:           str  = "",
    words_per_subtitle:  int  = 8,
) -> dict:
    """
    Phase 1 of the pipeline for human-in-the-loop review:
    fetch video → transcribe (Whisper, auto-detect) → translate (NLLB) → optional SRT.

    Accepts either a local video_path OR a video_url.

    Returns a dict with transcript, translation, detected_language,
    SRT path, and video_path for HIL Phase 2.
    """
    _setup_logging()

    _url_mode    = bool(video_url and not video_path)
    _temp_to_del = ""

    if not _url_mode and not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    if target_language not in LANGUAGES:
        raise ValueError(f"Unsupported target language: {target_language!r}")

    job_id    = uuid.uuid4().hex[:8]
    src_label = video_url if _url_mode else video_path
    log.info(f"=== HIL PHASE-1 {job_id} | → {target_language} | {src_label} ===")

    def _prog(stage: int, pct: float, msg: str):
        log.info(f"[Stage {stage}/5 | {pct:.0f}%] {msg}")
        if progress_cb:
            try: progress_cb(stage, pct, msg)
            except Exception: pass

    # Stage 1: Fetch video (download from URL or use uploaded file as-is)
    if _url_mode:
        _prog(1, 5, "Connecting to video source…")
        def _dl_prog(pct: float, msg: str):
            _prog(1, 5 + pct * 0.90, msg)
        from pipeline.downloader import download_to_temp
        video_path   = download_to_temp(video_url, progress_cb=_dl_prog)
        _temp_to_del = video_path
        _prog(1, 100, "Video downloaded")
    else:
        _prog(1, 50, f"Using local file: {os.path.basename(video_path)}")
        _prog(1, 100, "Video ready")

    # Stage 2: Transcribe (Whisper — auto-detects language)
    _prog(2, 5, "Starting transcription (Whisper)…")

    def transcribe_progress(elapsed_pct: float, status: str):
        _prog(2, min(95, elapsed_pct), f"Whisper: {status}")

    transcript, word_timestamps, detected_lang = transcribe_video(
        video_path,
        progress_cb=transcribe_progress,
        return_timestamps=generate_srt,
    )
    _prog(2, 100, f"Transcript ready ({len(transcript)} chars) — detected: {detected_lang}")

    if not transcript or not transcript.strip():
        raise ValueError(
            "No speech detected in this video.\n\n"
            "Possible reasons:\n"
            "• The video has background music but no spoken words\n"
            "• The audio is too quiet or muffled\n"
            "• The video has no audio track\n\n"
            "Please use a video with clear spoken speech."
        )

    # Resolve source NLLB code from Whisper's detected language
    source_nllb_code = WHISPER_TO_NLLB.get(detected_lang, "eng_Latn")
    log.info(f"Whisper lang: {detected_lang} → NLLB source: {source_nllb_code}")

    # Stage 3: Translate (NLLB — any → any)
    _prog(3, 5, f"Translating {source_nllb_code} → {target_language}…")

    def translate_progress(chunk_i: int, total_chunks: int):
        pct = 10 + (chunk_i / max(1, total_chunks)) * 85
        _prog(3, pct, f"Translating chunk {chunk_i}/{total_chunks}…")

    translation = translate_text(
        transcript,
        target_language=target_language,
        source_nllb_code=source_nllb_code,
        progress_cb=translate_progress,
    )
    _prog(3, 100, f"Translation ready ({len(translation)} chars)")

    srt_path = ""
    if generate_srt and word_timestamps:
        try:
            from pipeline.transcribe import generate_srt_file
            srt_path = os.path.join(OUTPUT_DIR, f"{job_id}_subtitles.srt")
            generate_srt_file(word_timestamps, srt_path, words_per_subtitle=words_per_subtitle)
        except Exception as e:
            log.warning(f"SRT generation failed (non-fatal): {e}")

    return {
        "job_id":                  job_id,
        "video_path":              video_path,
        "language":                target_language,
        "detected_language_code":  detected_lang,
        "transcript":              transcript,
        "translation":             translation,
        "srt_path":                srt_path,
        "_temp_path":              _temp_to_del,
    }


def run_tts_and_mux(
    video_path:      str,
    target_language: str,
    final_text:      str,
    job_id:          str | None = None,
    progress_cb=None,
    srt_path:        str = "",
    voice_pitch:     int = 0,
    vol_boost:       float = 2.0,
    bg_music_vol:    float = 0.0,
) -> dict:
    """
    Phase 2 of the pipeline for human-in-the-loop:
    synthesize speech from reviewed text and mux with video.
    """
    _setup_logging()

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    if target_language not in LANGUAGES:
        raise ValueError(f"Unsupported language: {target_language!r}")

    if job_id is None:
        job_id = uuid.uuid4().hex[:8]

    lang_cfg = LANGUAGES[target_language]
    log.info(f"=== HIL PHASE-2 {job_id} | {target_language} | {video_path} ===")

    def _prog(stage: int, pct: float, msg: str):
        log.info(f"[Stage {stage}/5 | {pct:.0f}%] {msg}")
        if progress_cb:
            try: progress_cb(stage, pct, msg)
            except Exception: pass

    # Stage 4: Synthesize
    _prog(4, 5, f"Initializing {lang_cfg['tts'].upper()} engine…")

    def synth_progress(chunk_i: int, total_chunks: int):
        pct = 10 + (chunk_i / max(1, total_chunks)) * 85
        _prog(4, pct, f"Synthesizing chunk {chunk_i}/{total_chunks}…")

    mp3_path = os.path.join(OUTPUT_DIR, f"{job_id}_dubbed.mp3")
    synthesize_speech(
        final_text, mp3_path, target_language,
        progress_cb=synth_progress, pitch_percent=voice_pitch,
    )
    _prog(4, 100, "Audio synthesized")

    # Stage 5: Mux
    _prog(5, 10, "Converting MP3 → WAV and muxing…")

    def mux_progress(step_pct: float, msg: str):
        _prog(5, step_pct, msg)

    output_path = os.path.join(OUTPUT_DIR, f"{job_id}_dubbed.mp4")
    mux(video_path, mp3_path, output_path,
        progress_cb=mux_progress, vol_boost=vol_boost, bg_music_vol=bg_music_vol)
    _prog(5, 100, f"Mux complete → {os.path.basename(output_path)}")

    try: os.remove(mp3_path)
    except Exception: pass

    return {
        "job_id":      job_id,
        "output_path": output_path,
        "language":    target_language,
        "translation": final_text,
        "srt_path":    srt_path,
    }


def run_pipeline(
    video_path:          str   = "",
    target_language:     str   = "",
    progress_cb=None,
    generate_srt:        bool  = False,
    voice_pitch:         int   = 0,
    vol_boost:           float = 2.0,
    video_url:           str   = "",
    bg_music_vol:        float = 0.0,
    words_per_subtitle:  int   = 8,
) -> dict:
    """
    Run the full Bhasha-Setu any-to-any dubbing pipeline.

    Accepts either video_path (upload) or video_url (YouTube/Vimeo/etc).

    Args:
        video_path:         Local path to source video.
        target_language:    Target language name (e.g. "Hindi", "Tamil").
        progress_cb:        Optional callable(stage, sub_pct, message).
        generate_srt:       Generate .srt subtitle file.
        voice_pitch:        Pitch shift percent (-20..+20).
        vol_boost:          Volume multiplier (default 2.0).
        video_url:          Public video URL.
        bg_music_vol:       Background music volume (0.0 = off).
        words_per_subtitle: Words per SRT block.

    Returns:
        dict: output_path, transcript, translation, job_id, language, srt_path,
              detected_language_code
    """
    _setup_logging()

    _url_mode    = bool(video_url and not video_path)
    _temp_to_del = ""

    if not _url_mode and not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    if target_language not in LANGUAGES:
        raise ValueError(f"Unsupported target language: {target_language!r}")

    job_id    = uuid.uuid4().hex[:8]
    lang_cfg  = LANGUAGES[target_language]
    src_label = video_url if _url_mode else video_path
    log.info(f"=== JOB {job_id} | → {target_language} | {src_label} ===")

    def _prog(stage: int, pct: float, msg: str):
        log.info(f"[Stage {stage}/5 | {pct:.0f}%] {msg}")
        if progress_cb:
            try: progress_cb(stage, pct, msg)
            except Exception: pass

    # Stage 1: Fetch video
    if _url_mode:
        _prog(1, 5, "Connecting to video source…")
        def _dl_prog(pct: float, msg: str):
            _prog(1, 5 + pct * 0.90, msg)
        from pipeline.downloader import download_to_temp
        video_path   = download_to_temp(video_url, progress_cb=_dl_prog)
        _temp_to_del = video_path
        _prog(1, 90, "Video downloaded")
    else:
        _prog(1, 40, f"Using local file: {os.path.basename(video_path)}")
        _prog(1, 90, "Video ready")

    # Stage 1.5: Detect speaker gender from vocal track
    _prog(1, 95, "Analyzing speaker gender...")
    detected_gender = "Female"
    try:
        import subprocess
        wav_path = os.path.join(OUTPUT_DIR, f"{job_id}_vocal_temp.wav")
        # Extract a 30s mono 16kHz audio sample from video using ffmpeg
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", video_path, "-vn", "-ac", "1", "-ar", "16000",
            "-t", "30", "-acodec", "pcm_s16le", wav_path
        ], check=True, capture_output=True)
        
        from pipeline.gender_detector import detect_gender
        detected_gender = detect_gender(wav_path)
        log.info(f"Auto-detected original speaker gender: {detected_gender}")
        try: os.remove(wav_path)
        except Exception: pass
    except Exception as e:
        log.warning(f"Speaker gender analysis failed (using fallback: Female): {e}")

    # Stage 2: Transcribe (Whisper — auto-detects language)
    _prog(2, 5, "Starting transcription (Whisper)…")

    def transcribe_progress(elapsed_pct: float, status: str):
        _prog(2, min(95, elapsed_pct), f"Whisper: {status}")

    transcript, word_timestamps, detected_lang = transcribe_video(
        video_path,
        progress_cb=transcribe_progress,
        return_timestamps=generate_srt,
    )
    _prog(2, 100, f"Transcript ready ({len(transcript)} chars) — detected: {detected_lang}")

    if not transcript or not transcript.strip():
        raise ValueError(
            "No speech detected in this video.\n\n"
            "Possible reasons:\n"
            "• The video has background music but no spoken words\n"
            "• The audio is too quiet or muffled\n\n"
            "Please use a video with clear spoken speech."
        )

    # Resolve NLLB source code from Whisper's detected language
    source_nllb_code = WHISPER_TO_NLLB.get(detected_lang, "eng_Latn")

    # Stage 3: Translate (NLLB — any → any)
    _prog(3, 5, f"Translating {source_nllb_code} → {target_language}…")

    def translate_progress(chunk_i: int, total_chunks: int):
        pct = 10 + (chunk_i / max(1, total_chunks)) * 75
        _prog(3, pct, f"Translating chunk {chunk_i}/{total_chunks}…")

    translation = translate_text(
        transcript,
        target_language=target_language,
        source_nllb_code=source_nllb_code,
        progress_cb=translate_progress,
    )
    _prog(3, 100, f"Translation ready ({len(translation)} chars)")

    srt_path = ""
    if generate_srt and word_timestamps:
        try:
            from pipeline.transcribe import generate_srt_file
            srt_path = os.path.join(OUTPUT_DIR, f"{job_id}_subtitles.srt")
            generate_srt_file(word_timestamps, srt_path, words_per_subtitle=words_per_subtitle)
        except Exception as e:
            log.warning(f"SRT generation failed: {e}")

    # Stage 4: Synthesize
    _prog(4, 5, f"Initializing {lang_cfg['tts'].upper()} engine…")

    def synth_progress(chunk_i: int, total_chunks: int):
        pct = 10 + (chunk_i / max(1, total_chunks)) * 85
        _prog(4, pct, f"Synthesizing chunk {chunk_i}/{total_chunks}…")

    mp3_path = os.path.join(OUTPUT_DIR, f"{job_id}_dubbed.mp3")
    synthesize_speech(
        translation, mp3_path, target_language,
        progress_cb=synth_progress, pitch_percent=voice_pitch,
        gender=detected_gender,
    )
    _prog(4, 100, "Audio synthesized")

    # Stage 5: Mux
    _prog(5, 10, "Converting MP3 → WAV…")

    def mux_progress(step_pct: float, msg: str):
        _prog(5, step_pct, msg)

    output_path = os.path.join(OUTPUT_DIR, f"{job_id}_dubbed.mp4")
    mux(video_path, mp3_path, output_path,
        progress_cb=mux_progress, vol_boost=vol_boost, bg_music_vol=bg_music_vol)
    _prog(5, 100, f"Mux complete → {os.path.basename(output_path)}")

    try: os.remove(mp3_path)
    except Exception: pass

    if _temp_to_del and os.path.exists(_temp_to_del):
        try:
            import shutil
            parent = os.path.dirname(_temp_to_del)
            if parent and os.path.isdir(parent):
                shutil.rmtree(parent, ignore_errors=True)
        except Exception:
            pass

    log.info(f"=== JOB {job_id} COMPLETE === Output: {output_path}")
    return {
        "job_id":                  job_id,
        "output_path":             output_path,
        "transcript":              transcript,
        "translation":             translation,
        "language":                target_language,
        "detected_language_code":  detected_lang,
        "srt_path":                srt_path,
    }


