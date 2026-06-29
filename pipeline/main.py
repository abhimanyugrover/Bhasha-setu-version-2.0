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


def _get_wav_duration(wav_path: str) -> float:
    """Return wave file duration in seconds."""
    import wave
    try:
        with wave.open(wav_path, 'rb') as f:
            frames = f.getnframes()
            rate = f.getframerate()
            return frames / float(rate) if rate > 0 else 0.0
    except Exception:
        return 0.0


def _segmented_dubbing(
    video_path: str,
    segments: list,
    target_language: str,
    tts_engine: str,
    voice_pitch: int,
    progress_cb,
    job_id: str,
) -> str:
    """
    Segmented translation, synthesis, speed-matching, and concatenation.
    Returns the path to the final concatenated audio MP3 file.
    """
    import subprocess
    import shutil

    # 1. Extract 30s general voice reference in case local segments are too short
    general_speaker_wav = os.path.join(OUTPUT_DIR, f"{job_id}_speaker_general.wav")
    try:
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", video_path, "-vn", "-ac", "1", "-ar", "16000",
            "-t", "30", "-acodec", "pcm_s16le", general_speaker_wav
        ], check=True)
    except Exception as e:
        log.warning(f"Failed to extract general speaker reference: {e}")
        general_speaker_wav = ""

    # Get original video's audio duration using ffprobe
    video_duration = 0.0
    try:
        res = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", video_path
        ], capture_output=True, text=True, check=True)
        video_duration = float(res.stdout.strip())
    except Exception as e:
        log.warning(f"Failed to get video duration: {e}")
        if segments:
            video_duration = segments[-1]["end"] + 2.0

    concat_list_file = os.path.join(OUTPUT_DIR, f"{job_id}_concat_list.txt")
    temp_files_to_clean = []

    concat_files = []
    current_time = 0.0

    total_segments = len(segments)

    for idx, seg in enumerate(segments):
        start = seg["start"]
        end = seg["end"]
        orig_text = seg["text"]

        # A. Handle silence gap before the segment
        if start > current_time:
            silence_dur = start - current_time
            silence_wav = os.path.join(OUTPUT_DIR, f"{job_id}_silence_{idx}.wav")
            subprocess.run([
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                "-t", f"{silence_dur:.3f}", silence_wav
            ], check=True)
            concat_files.append(silence_wav)
            temp_files_to_clean.append(silence_wav)

        # B. Translate this segment's text
        from pipeline.translate import translate_text
        try:
            translated_text = translate_text(orig_text, target_language)
        except Exception as e:
            log.warning(f"Translation failed for segment {idx}: {e}")
            translated_text = orig_text

        # C. Extract this specific segment's audio from video as reference voice
        seg_ref_wav = os.path.join(OUTPUT_DIR, f"{job_id}_seg_ref_{idx}.wav")
        ref_used = ""
        try:
            subprocess.run([
                "ffmpeg", "-y", "-loglevel", "error",
                "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                "-i", video_path, "-vn", "-ac", "1", "-ar", "16000",
                "-acodec", "pcm_s16le", seg_ref_wav
            ], check=True)
            ref_used = seg_ref_wav
            temp_files_to_clean.append(seg_ref_wav)
        except Exception:
            ref_used = general_speaker_wav

        # If extracted audio is too short, use general voice instead
        if ref_used and ref_used == seg_ref_wav:
            if _get_wav_duration(seg_ref_wav) < 1.0:
                ref_used = general_speaker_wav

        # D. Synthesize segment text
        seg_synth_mp3 = os.path.join(OUTPUT_DIR, f"{job_id}_seg_synth_{idx}.mp3")
        seg_synth_wav = os.path.join(OUTPUT_DIR, f"{job_id}_seg_synth_{idx}.wav")
        temp_files_to_clean.append(seg_synth_mp3)
        temp_files_to_clean.append(seg_synth_wav)

        synthesize_speech(
            text=translated_text,
            output_mp3=seg_synth_mp3,
            lang_name=target_language,
            pitch_percent=voice_pitch,
            tts_engine=tts_engine,
            speaker_wav=ref_used,
            ref_text=orig_text
        )

        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", seg_synth_mp3, seg_synth_wav
        ], check=True)

        # E. Timing alignment: Speed adjust and Pad/Trim
        target_dur = end - start
        synth_dur = _get_wav_duration(seg_synth_wav)

        speed_adjusted_wav = os.path.join(OUTPUT_DIR, f"{job_id}_seg_adjusted_{idx}.wav")
        temp_files_to_clean.append(speed_adjusted_wav)

        if synth_dur > 0 and target_dur > 0:
            speed_factor = synth_dur / target_dur
            speed_factor = min(1.5, max(0.8, speed_factor))

            filter_str = f"atempo={speed_factor}"
            if speed_factor > 2.0:
                filter_str = f"atempo=2.0,atempo={speed_factor/2.0}"
            elif speed_factor < 0.5:
                filter_str = f"atempo=0.5,atempo={speed_factor/0.5}"

            subprocess.run([
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", seg_synth_wav,
                "-filter:a", filter_str,
                speed_adjusted_wav
            ], check=True)
        else:
            shutil.copyfile(seg_synth_wav, speed_adjusted_wav)

        seg_final_wav = os.path.join(OUTPUT_DIR, f"{job_id}_seg_final_{idx}.wav")
        temp_files_to_clean.append(seg_final_wav)

        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", speed_adjusted_wav,
            "-af", "apad", "-t", f"{target_dur:.3f}",
            seg_final_wav
        ], check=True)

        concat_files.append(seg_final_wav)
        current_time = end

        if progress_cb:
            progress_cb(4, 10 + ((idx + 1) / total_segments) * 85, f"Synthesized segment {idx+1}/{total_segments}…")

    # F. Handle trailing silence if needed
    if video_duration > current_time:
        trailing_dur = video_duration - current_time
        trailing_wav = os.path.join(OUTPUT_DIR, f"{job_id}_trailing_silence.wav")
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-t", f"{trailing_dur:.3f}", trailing_wav
        ], check=True)
        concat_files.append(trailing_wav)
        temp_files_to_clean.append(trailing_wav)

    # G. Concatenate all files
    final_dubbed_wav = os.path.join(OUTPUT_DIR, f"{job_id}_dubbed_aligned.wav")
    with open(concat_list_file, "w", encoding="utf-8") as f:
        for p in concat_files:
            abs_path = os.path.abspath(p).replace("\\", "\\\\")
            f.write(f"file '{abs_path}'\n")

    try:
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", concat_list_file, "-c", "copy", final_dubbed_wav
        ], check=True)
    finally:
        if os.path.exists(concat_list_file):
            try: os.unlink(concat_list_file)
            except Exception: pass

        if general_speaker_wav and os.path.exists(general_speaker_wav):
            try: os.unlink(general_speaker_wav)
            except Exception: pass

        for f in temp_files_to_clean:
            if os.path.exists(f):
                try: os.unlink(f)
                except Exception: pass

    final_dubbed_mp3 = os.path.join(OUTPUT_DIR, f"{job_id}_dubbed.mp3")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", final_dubbed_wav, "-codec:a", "libmp3lame", "-qscale:a", "2",
        final_dubbed_mp3
    ], check=True)

    if os.path.exists(final_dubbed_wav):
        try: os.unlink(final_dubbed_wav)
        except Exception: pass

    return final_dubbed_mp3


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
    align_timing:        bool  = True,
    tts_engine:          str   = "edge",
) -> dict:
    """
    Run the full Bhasha-Setu any-to-any dubbing pipeline.
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

    transcript, word_timestamps, detected_lang, segments_list = transcribe_video(
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

    mp3_path = os.path.join(OUTPUT_DIR, f"{job_id}_dubbed.mp3")

    if align_timing and segments_list:
        _prog(4, 10, "Starting timing-aligned segmented synthesis…")
        _segmented_dubbing(
            video_path=video_path,
            segments=segments_list,
            target_language=target_language,
            tts_engine=tts_engine,
            voice_pitch=voice_pitch,
            progress_cb=_prog,
            job_id=job_id,
        )
    else:
        def synth_progress(chunk_i: int, total_chunks: int):
            pct = 10 + (chunk_i / max(1, total_chunks)) * 85
            _prog(4, pct, f"Synthesizing chunk {chunk_i}/{total_chunks}…")

        speaker_ref_wav = ""
        if tts_engine == "omnivoice":
            speaker_ref_wav = os.path.join(OUTPUT_DIR, f"{job_id}_speaker_ref.wav")
            subprocess.run([
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", video_path, "-vn", "-ac", "1", "-ar", "16000",
                "-t", "30", "-acodec", "pcm_s16le", speaker_ref_wav
            ], check=True)

        synthesize_speech(
            translation, mp3_path, target_language,
            progress_cb=synth_progress, pitch_percent=voice_pitch,
            gender=detected_gender, tts_engine=tts_engine,
            speaker_wav=speaker_ref_wav, ref_text=transcript,
        )

        if speaker_ref_wav and os.path.exists(speaker_ref_wav):
            try: os.unlink(speaker_ref_wav)
            except Exception: pass

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


