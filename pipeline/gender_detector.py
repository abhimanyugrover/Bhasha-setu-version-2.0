"""
Bhasha Setu — Speaker Gender Detector
Estimates fundamental frequency (F0) from the original voice track using autocorrelation.
Requires only numpy (no heavy deep learning libraries).
"""

import wave
import logging
import numpy as np

log = logging.getLogger(__name__)

def detect_gender(wav_path: str) -> str:
    """
    Detect whether the speaker in a mono 16kHz WAV file is Male or Female.
    Uses autocorrelation to find the fundamental frequency (F0) in the human pitch range.
    """
    try:
        with wave.open(wav_path, "rb") as wf:
            fs = wf.getframerate()
            n_channels = wf.getnchannels()
            
            # Simple validation
            if n_channels != 1:
                log.warning("Gender detector expected mono audio, getnchannels=%d", n_channels)
            
            n_frames = wf.getnframes()
            audio_bytes = wf.readframes(n_frames)
            
        data = np.frombuffer(audio_bytes, dtype=np.int16).astype(float)
        if len(data) == 0:
            return "Female"
            
        # Analysis parameters: 30ms window, 15ms shift
        frame_size = int(0.03 * fs)
        hop_size = int(0.015 * fs)
        
        # Human vocal pitch range: 80Hz (deep male) to 300Hz (high female/child)
        min_lag = int(fs / 300)
        max_lag = int(fs / 80)
        
        pitches = []
        
        for i in range(0, len(data) - frame_size, hop_size):
            frame = data[i:i + frame_size]
            
            # Voice Activity Detection (VAD) using simple RMS threshold
            rms = np.sqrt(np.mean(frame ** 2))
            if rms < 150:  # skip silent or low-energy parts
                continue
                
            # Autocorrelation
            corr = np.correlate(frame, frame, mode='full')
            # Look at positive lags only
            corr = corr[len(corr) // 2:]
            
            lag_range = corr[min_lag:max_lag]
            if len(lag_range) == 0:
                continue
                
            peak_lag = np.argmax(lag_range) + min_lag
            
            # Check if autocorrelation peak is significant
            if corr[peak_lag] > 0.45 * corr[0]:
                f0 = fs / peak_lag
                # Safeguard boundaries
                if 80.0 <= f0 <= 300.0:
                    pitches.append(f0)
                    
        if not pitches:
            log.info("No voiced frames detected in gender analysis. Defaulting to Female.")
            return "Female"
            
        avg_pitch = float(np.median(pitches))
        log.info("Detected speaker average F0 pitch: %.1f Hz", avg_pitch)
        
        # Classification boundary:
        # Male speech typically is 85-180 Hz, Female is 165-255 Hz.
        # Threshold at 160Hz is optimal for auto-switching edge-tts voices.
        if avg_pitch < 160.0:
            return "Male"
        else:
            return "Female"
            
    except Exception as e:
        log.error("Error during speaker gender detection: %s. Defaulting to Female.", e, exc_info=True)
        return "Female"
