"""
Bhasha-Setu — NLLB-200 Translation Service
Uses Meta's NLLB-200 (No Language Left Behind) for offline, free translation.
Handles chunking at sentence boundaries for the ~512 token NLLB limit.

Google Translate (via deep_translator) is kept as a simple helper for the
standalone text translator tab only.
"""

import logging
from typing import Callable, Optional

from pipeline.config import NLLB_LANG_MAP, NLLB_CHUNK_CHARS

log = logging.getLogger(__name__)

# ── Lazy-loaded singleton NLLB model + tokenizer ─────────────────────────────
_model = None
_tokenizer = None


def _get_nllb():
    """Load the NLLB-200 model and tokenizer once and reuse them."""
    global _model, _tokenizer
    if _model is None:
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        from pipeline.config import NLLB_MODEL
        import torch
        log.info(f"Loading NLLB model: {NLLB_MODEL}")
        _tokenizer = AutoTokenizer.from_pretrained(NLLB_MODEL)
        raw_model = AutoModelForSeq2SeqLM.from_pretrained(NLLB_MODEL)
        
        # Apply 8-bit dynamic quantization to speed up CPU translation by 2x-4x
        log.info("Applying dynamic quantization to NLLB model for CPU speedup...")
        _model = torch.quantization.quantize_dynamic(
            raw_model, {torch.nn.Linear}, dtype=torch.qint8
        )
        log.info("NLLB model loaded and quantized successfully.")
    return _model, _tokenizer


# ─────────────────────────────────────────────────────────────────────────────
#  TEXT CHUNKING
# ─────────────────────────────────────────────────────────────────────────────

def _split_into_chunks(text: str, max_chars: int = NLLB_CHUNK_CHARS) -> list:
    """
    Split text on sentence boundaries, staying within max_chars per chunk.
    Falls back to word-level splitting for very long sentences.
    """
    sentences = []
    buf = ""
    for char in text:
        buf += char
        if char in ".?!" and buf.strip():
            sentences.append(buf)
            buf = ""
    if buf.strip():
        sentences.append(buf)

    chunks, current = [], ""
    for sentence in sentences:
        candidate = current + sentence
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current.strip())
            if len(sentence) > max_chars:
                # Word-level fallback for very long sentences
                words, sub = sentence.split(), ""
                for word in words:
                    trial = sub + word + " "
                    if len(trial) <= max_chars:
                        sub = trial
                    else:
                        if sub:
                            chunks.append(sub.strip())
                        sub = word + " "
                current = sub
            else:
                current = sentence

    if current.strip():
        chunks.append(current.strip())
    return chunks


# ─────────────────────────────────────────────────────────────────────────────
#  NLLB TRANSLATION — primary pipeline translation engine
# ─────────────────────────────────────────────────────────────────────────────

def translate_text(
    text: str,
    target_language: str,
    source_nllb_code: str = "eng_Latn",
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> str:
    """
    Translate text using NLLB-200.

    Args:
        text:             Source text to translate.
        target_language:  Display name for target (e.g. 'Hindi', 'Tamil').
                          Looked up in NLLB_LANG_MAP to get the FLORES code.
        source_nllb_code: NLLB FLORES-200 code for the source language
                          (e.g. 'eng_Latn', 'hin_Deva').
        progress_cb:      Optional callable(chunk_index, total_chunks).

    Returns:
        Translated text as a single string.
    """
    if not text or not text.strip():
        raise ValueError("Input text for translation is empty.")

    target_nllb_code = NLLB_LANG_MAP.get(target_language)
    if not target_nllb_code:
        raise ValueError(f"Unsupported target language: {target_language!r}")

    # Same language — skip translation
    if source_nllb_code == target_nllb_code:
        log.info("Source and target language are the same — skipping translation.")
        return text

    model, tokenizer = _get_nllb()
    tokenizer.src_lang = source_nllb_code

    chunks = _split_into_chunks(text, NLLB_CHUNK_CHARS)
    total  = len(chunks)
    log.info(
        f"Translating '{source_nllb_code}' → '{target_nllb_code}' "
        f"via NLLB-200 | {total} chunk(s)"
    )

    target_token_id = tokenizer.convert_tokens_to_ids(target_nllb_code)

    translated_parts = []
    for i, chunk in enumerate(chunks):
        if progress_cb:
            progress_cb(i, total)

        inputs = tokenizer(
            chunk,
            return_tensors="pt",
            truncation=True,
            max_length=512,
        )
        outputs = model.generate(
            **inputs,
            forced_bos_token_id=target_token_id,
            max_new_tokens=512,
        )
        decoded = tokenizer.decode(outputs[0], skip_special_tokens=True)
        translated_parts.append(decoded)

    if progress_cb:
        progress_cb(total, total)

    result = " ".join(translated_parts)
    log.info(f"Translation complete: {len(text)} → {len(result)} chars")
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  GOOGLE TRANSLATE — lightweight wrapper for the text translator tab
# ─────────────────────────────────────────────────────────────────────────────

def translate_text_google(
    text: str,
    src_lang_code: str,
    tgt_lang_code: str,
) -> str:
    """
    Simple Google Translate wrapper for the standalone text translator tab.

    Args:
        text:          Text to translate.
        src_lang_code: Source language ISO code (e.g. 'en', 'auto').
        tgt_lang_code: Target language ISO code (e.g. 'hi', 'ta').

    Returns:
        Translated text.
    """
    from deep_translator import GoogleTranslator
    return GoogleTranslator(source=src_lang_code, target=tgt_lang_code).translate(text)
