from pydantic import BaseModel
from typing import Optional
from enum import Enum


class JobStatus(str, Enum):
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'


class DubRequest(BaseModel):
    target_language: str
    video_url: Optional[str] = None
    generate_srt: bool = False
    voice_pitch: int = 0
    vol_boost: float = 2.0
    bg_music_vol: float = 0.0
    words_per_subtitle: int = 8


class DubResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: float = 0.0
    current_stage: int = 0
    stage_message: str = ''
    output_ready: bool = False
    transcript: Optional[str] = None
    translation: Optional[str] = None
    detected_language: Optional[str] = None
    error: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    transcript_context: Optional[str] = None
    language: str = 'English'
    history: list = []


class ChatResponse(BaseModel):
    reply: str


class TranslateRequest(BaseModel):
    text: str
    source_lang: str
    target_lang: str


class TranslateResponse(BaseModel):
    translated_text: str


class LanguageInfo(BaseModel):
    name: str
    native_name: str
    flag: str
    tts_engine: str
