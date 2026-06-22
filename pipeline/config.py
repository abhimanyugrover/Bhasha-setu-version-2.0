"""
Bhasha-Setu — Pipeline Configuration
Language registry, model settings, chunking limits.

Fully open-source / free stack:
  - Whisper (faster-whisper)  for transcription
  - NLLB-200                  for translation
  - edge-tts / gTTS           for speech synthesis

No AWS credentials or paid APIs required.
"""

import os
from dotenv import load_dotenv
load_dotenv()


# ── Whisper (transcription) ──────────────────────────────────────────────────
# Model size: tiny / base / small / medium  (larger = more accurate, slower)
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")

# ── NLLB-200 (translation) ──────────────────────────────────────────────────
NLLB_MODEL = "facebook/nllb-200-distilled-600M"

# ── Chunking limits ──────────────────────────────────────────────────────────
NLLB_CHUNK_CHARS = 400      # NLLB has ~512 token limit; keep char chunks small
EDGE_CHUNK_CHARS = 5_000
GTTS_CHUNK_CHARS = 5_000

# ── Directories ──────────────────────────────────────────────────────────────
OUTPUT_DIR = "output"
CACHE_DIR  = "cache"
LOG_DIR    = "logs"

# ── Job management ───────────────────────────────────────────────────────────
MAX_CONCURRENT_JOBS  = 3
JOB_EXPIRY_SECONDS   = 3600   # auto-cleanup after 1 hour

# ── NLLB FLORES-200 language code mapping ────────────────────────────────────
# Maps display name → NLLB FLORES-200 BCP code
NLLB_LANG_MAP = {
    "Hindi":      "hin_Deva",
    "Tamil":      "tam_Taml",
    "Telugu":     "tel_Telu",
    "Kannada":    "kan_Knda",
    "Malayalam":  "mal_Mlym",
    "Bengali":    "ben_Beng",
    "Marathi":    "mar_Deva",
    "Gujarati":   "guj_Gujr",
    "Punjabi":    "pan_Guru",
    "Urdu":       "urd_Arab",
    "Odia":       "ory_Orya",
    "Assamese":   "asm_Beng",
    "English":    "eng_Latn",
    "French":     "fra_Latn",
    "German":     "deu_Latn",
    "Spanish":    "spa_Latn",
    "Japanese":   "jpn_Jpan",
    "Korean":     "kor_Hang",
    "Portuguese": "por_Latn",
    "Italian":    "ita_Latn",
    "Chinese":    "zho_Hans",
    "Russian":    "rus_Cyrl",
    "Arabic":     "arb_Arab",
}

# ── Whisper language code → NLLB source code ─────────────────────────────────
# Whisper returns short ISO codes; map them to NLLB FLORES-200 codes so the
# translator knows what source language was detected.
WHISPER_TO_NLLB = {
    "en": "eng_Latn",
    "hi": "hin_Deva",
    "ta": "tam_Taml",
    "te": "tel_Telu",
    "kn": "kan_Knda",
    "ml": "mal_Mlym",
    "bn": "ben_Beng",
    "mr": "mar_Deva",
    "gu": "guj_Gujr",
    "pa": "pan_Guru",
    "ur": "urd_Arab",
    "or": "ory_Orya",
    "as": "asm_Beng",
    "fr": "fra_Latn",
    "de": "deu_Latn",
    "es": "spa_Latn",
    "ja": "jpn_Jpan",
    "ko": "kor_Hang",
    "pt": "por_Latn",
    "it": "ita_Latn",
    "zh": "zho_Hans",
    "ru": "rus_Cyrl",
    "ar": "arb_Arab",
}

# ── Target language registry ─────────────────────────────────────────────────
# TTS engine per language:
#   edge  → Microsoft edge-tts Neural (free, high quality)
#   gtts  → Google TTS (free fallback for languages edge-tts doesn't reliably support)
#
# Punjabi is set to gtts because pa-IN-OjaswanthNeural is inconsistently
# available on edge-tts depending on region/network, causing silent Hindi fallback.
# gTTS has solid pa (Punjabi) support and reliably produces correct Punjabi voice.

LANGUAGES = {
    "Hindi": {
        "flag": "IN", "native_name": "हिन्दी",
        "tts": "edge",
        "edge_voice": "hi-IN-SwaraNeural",
        "edge_female_voice": "hi-IN-SwaraNeural",
        "edge_male_voice": "hi-IN-MadhurNeural",
        "gtts_lang": "hi",
    },
    "Tamil": {
        "flag": "IN", "native_name": "தமிழ்",
        "tts": "edge",
        "edge_voice": "ta-IN-PallaviNeural",
        "edge_female_voice": "ta-IN-PallaviNeural",
        "edge_male_voice": "ta-IN-ValluvarNeural",
        "gtts_lang": "ta",
    },
    "Telugu": {
        "flag": "IN", "native_name": "తెలుగు",
        "tts": "edge",
        "edge_voice": "te-IN-ShrutiNeural",
        "edge_female_voice": "te-IN-ShrutiNeural",
        "edge_male_voice": "te-IN-MohanNeural",
        "gtts_lang": "te",
    },
    "Kannada": {
        "flag": "IN", "native_name": "ಕನ್ನಡ",
        "tts": "edge",
        "edge_voice": "kn-IN-SapnaNeural",
        "edge_female_voice": "kn-IN-SapnaNeural",
        "edge_male_voice": "kn-IN-GaganNeural",
        "gtts_lang": "kn",
    },
    "Malayalam": {
        "flag": "IN", "native_name": "മലയാളം",
        "tts": "edge",
        "edge_voice": "ml-IN-SobhanaNeural",
        "edge_female_voice": "ml-IN-SobhanaNeural",
        "edge_male_voice": "ml-IN-MidhunNeural",
        "gtts_lang": "ml",
    },
    "Bengali": {
        "flag": "IN", "native_name": "বাংলা",
        "tts": "edge",
        "edge_voice": "bn-IN-TanishaaNeural",
        "edge_female_voice": "bn-IN-TanishaaNeural",
        "edge_male_voice": "bn-IN-BashkarNeural",
        "gtts_lang": "bn",
    },
    "Marathi": {
        "flag": "IN", "native_name": "मराठी",
        "tts": "edge",
        "edge_voice": "mr-IN-AarohiNeural",
        "edge_female_voice": "mr-IN-AarohiNeural",
        "edge_male_voice": "mr-IN-ManoharNeural",
        "gtts_lang": "mr",
    },
    "Gujarati": {
        "flag": "IN", "native_name": "ગુજરાતી",
        "tts": "edge",
        "edge_voice": "gu-IN-DhwaniNeural",
        "edge_female_voice": "gu-IN-DhwaniNeural",
        "edge_male_voice": "gu-IN-NiranjanNeural",
        "gtts_lang": "gu",
    },
    "Punjabi": {
        "flag": "IN", "native_name": "ਪੰਜਾਬੀ",
        "tts": "gtts",
        "edge_voice": "pa-IN-OjaswanthNeural",
        "edge_female_voice": "pa-IN-OjaswanthNeural",
        "edge_male_voice": "pa-IN-OjaswanthNeural",
        "gtts_lang": "pa",
    },
    "Urdu": {
        "flag": "IN", "native_name": "اردو",
        "tts": "edge",
        "edge_voice": "ur-PK-UzmaNeural",
        "edge_female_voice": "ur-PK-UzmaNeural",
        "edge_male_voice": "ur-PK-AsadNeural",
        "gtts_lang": "ur",
    },
    "Odia": {
        "flag": "IN", "native_name": "ଓଡ଼ିଆ",
        "tts": "gtts",
        "edge_voice": "or-IN-SubhasiniNeural",
        "edge_female_voice": "or-IN-SubhasiniNeural",
        "edge_male_voice": "or-IN-SubhasiniNeural",
        "gtts_lang": "or",
    },
    "Assamese": {
        "flag": "IN", "native_name": "অসমীয়া",
        "tts": "gtts",
        "edge_voice": "as-IN-PriyomNeural",
        "edge_female_voice": "as-IN-PriyomNeural",
        "edge_male_voice": "as-IN-PriyomNeural",
        "gtts_lang": "as",
    },
    "English": {
        "flag": "US", "native_name": "English",
        "tts": "edge",
        "edge_voice": "en-US-JennyNeural",
        "edge_female_voice": "en-US-JennyNeural",
        "edge_male_voice": "en-US-GuyNeural",
        "gtts_lang": "en",
    },
}

# ── Text translator language codes (for the standalone text translator tab) ──
LANG_CODES = {
    "Auto-detect": "auto",
    "English":     "en",
    "Hindi":       "hi",
    "Tamil":       "ta",
    "Telugu":      "te",
    "Kannada":     "kn",
    "Malayalam":   "ml",
    "Bengali":     "bn",
    "Marathi":     "mr",
    "Gujarati":    "gu",
    "Punjabi":     "pa",
    "Urdu":        "ur",
    "Odia":        "or",
    "Assamese":    "as",
    "French":      "fr",
    "German":      "de",
    "Spanish":     "es",
    "Japanese":    "ja",
    "Chinese":     "zh-CN",
    "Arabic":      "ar",
    "Russian":     "ru",
    "Portuguese":  "pt",
}
