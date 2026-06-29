import logging
import os
from typing import Optional

log = logging.getLogger(__name__)


def chat_with_ai(message: str, transcript_context: str = '', language: str = 'English', history: list = None) -> str:
    """
    Chat using HuggingFace Inference API (free tier).
    Falls back to a simple response if unavailable.
    """
    if history is None:
        history = []

    # Build system prompt with video context
    system_prompt = (
        'You are Bhasha Setu AI — a helpful multilingual assistant for video dubbing. '
        'Help with education, languages, and questions about video content. '
        'Be friendly, concise, and helpful. '
    )
    if language != 'English':
        system_prompt += f'Always respond in {language} language. '
    if transcript_context:
        snippet = transcript_context[:2000]
        system_prompt += (
            f'\n\nThe user has just dubbed a video. Here is the transcript for context:\n'
            f'{snippet}\n\n'
            'If the user asks about the video, use this transcript to answer.'
        )

    # Build messages
    messages = [{'role': 'system', 'content': system_prompt}]
    for m in (history or [])[-6:]:
        messages.append({'role': m.get('role', 'user'), 'content': m.get('content', '')})
    messages.append({'role': 'user', 'content': message})

    # Try HuggingFace Inference API
    hf_token = os.environ.get('HF_TOKEN', '')
    try:
        from huggingface_hub import InferenceClient
        client = InferenceClient(token=hf_token if hf_token else None)
        response = client.chat_completion(
            model='Qwen/Qwen2.5-7B-Instruct',
            messages=messages,
            max_tokens=512,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log.warning(f'HF Inference API failed: {e}')

    # Try Groq as fallback (if API key is set)
    groq_key = os.environ.get('GROQ_API_KEY', '')
    if groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            resp = client.chat.completions.create(
                model='llama-3.1-8b-instant',
                messages=messages,
                max_tokens=512,
                temperature=0.7,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            log.warning(f'Groq fallback failed: {e}')

    return (
        'I\'m currently unable to connect to any AI backend. '
        'Please try again in a moment, or set HF_TOKEN or GROQ_API_KEY '
        'environment variable for better reliability.'
    )
