import os
import uuid
import json
import shutil
import asyncio
import logging
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv
load_dotenv() # Load local .env variables securely

from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager

from backend.models import (
    DubResponse, JobStatusResponse, JobStatus,
    ChatRequest, ChatResponse,
    TranslateRequest, TranslateResponse,
    LanguageInfo,
)
from backend.chat import chat_with_ai
from pipeline.config import LANGUAGES, LANG_CODES, OUTPUT_DIR, JOB_EXPIRY_SECONDS

log = logging.getLogger(__name__)

# In-memory job store
jobs: Dict[str, dict] = {}
# WebSocket connections per job
ws_connections: Dict[str, list] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create dirs
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs('cache', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    # Start cleanup task
    cleanup_task = asyncio.create_task(_cleanup_loop())
    yield
    # Shutdown
    cleanup_task.cancel()


app = FastAPI(title='Bhasha Setu API', lifespan=lifespan)

# Serve frontend static files
FRONTEND_DIR = Path(__file__).parent.parent / 'frontend'

# In-memory HTML cache (for production performance)
_inlined_html_cache = None

def get_inlined_frontend():
    global _inlined_html_cache
    if os.environ.get("DEV") != "true" and _inlined_html_cache is not None:
        return _inlined_html_cache

    index_path = FRONTEND_DIR / 'index.html'
    if not index_path.exists():
        return None

    html = index_path.read_text(encoding='utf-8')

    # 1. Inline CSS
    css_path = FRONTEND_DIR / 'css' / 'style.css'
    if css_path.exists():
        css_content = css_path.read_text(encoding='utf-8')
        html = html.replace(
            '<link rel="stylesheet" href="css/style.css">',
            f'<style>\n{css_content}\n</style>'
        )

    # 2. Inline JS files
    for js_name in ['api.js', 'components.js', 'app.js']:
        js_path = FRONTEND_DIR / 'js' / js_name
        if js_path.exists():
            js_content = js_path.read_text(encoding='utf-8')
            html = html.replace(
                f'<script src="js/{js_name}" defer></script>',
                f'<script>\n{js_content}\n</script>'
            )
            html = html.replace(
                f'<script src="js/{js_name}"></script>',
                f'<script>\n{js_content}\n</script>'
            )

    _inlined_html_cache = html
    return html

from fastapi.responses import HTMLResponse

@app.get('/')
async def serve_frontend():
    html = get_inlined_frontend()
    if html:
        return HTMLResponse(
            content=html,
            status_code=200,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return JSONResponse({'error': 'Frontend not found'}, status_code=404)


@app.get('/api/debug/jobs')
async def debug_jobs():
    return jobs


if FRONTEND_DIR.exists():
    if (FRONTEND_DIR / 'css').exists():
        app.mount('/css', StaticFiles(directory=str(FRONTEND_DIR / 'css')), name='css')
    if (FRONTEND_DIR / 'js').exists():
        app.mount('/js', StaticFiles(directory=str(FRONTEND_DIR / 'js')), name='js')
    if (FRONTEND_DIR / 'assets').exists():
        app.mount('/assets', StaticFiles(directory=str(FRONTEND_DIR / 'assets')), name='assets')


# ── Languages endpoint ──
@app.get('/api/languages')
async def get_languages():
    result = []
    for name, cfg in LANGUAGES.items():
        result.append({
            'name': name,
            'native_name': cfg.get('native_name', ''),
            'flag': cfg.get('flag', ''),
            'tts_engine': cfg.get('tts', ''),
        })
    return result


# ── Dub endpoint ──
@app.post('/api/dub', response_model=DubResponse)
async def start_dubbing(
    video: UploadFile = File(None),
    target_language: str = Form(...),
    video_url: str = Form(''),
    generate_srt: bool = Form(False),
    voice_pitch: int = Form(0),
    vol_boost: float = Form(2.0),
    bg_music_vol: float = Form(0.0),
):
    if not video and not video_url:
        raise HTTPException(400, 'Provide either a video file or URL')
    if target_language not in LANGUAGES:
        raise HTTPException(400, f'Unsupported language: {target_language}')
    
    job_id = uuid.uuid4().hex[:8]
    video_path = ''
    
    if video:
        # Save uploaded file to temp
        tmp_dir = tempfile.mkdtemp(prefix=f'bhasha_{job_id}_')
        video_path = os.path.join(tmp_dir, video.filename or 'upload.mp4')
        with open(video_path, 'wb') as f:
            content = await video.read()
            f.write(content)
    
    # Initialize job
    jobs[job_id] = {
        'status': JobStatus.QUEUED,
        'progress': 0.0,
        'current_stage': 0,
        'stage_message': 'Queued...',
        'stages': [{'pct': 0, 'msg': ''} for _ in range(5)],
        'video_path': video_path,
        'video_url': video_url,
        'target_language': target_language,
        'generate_srt': generate_srt,
        'voice_pitch': voice_pitch,
        'vol_boost': vol_boost,
        'bg_music_vol': bg_music_vol,
        'output_path': '',
        'transcript': '',
        'translation': '',
        'detected_language': '',
        'srt_path': '',
        'error': None,
        'created_at': datetime.now().isoformat(),
    }
    
    # Run pipeline in background thread
    thread = threading.Thread(target=_run_job, args=(job_id,), daemon=True)
    thread.start()
    
    return DubResponse(job_id=job_id, status=JobStatus.QUEUED, message='Job queued')


def _run_job(job_id: str):
    """Run the dubbing pipeline in a background thread."""
    job = jobs[job_id]
    job['status'] = JobStatus.RUNNING
    
    def progress_cb(stage: int, pct: float, msg: str):
        job['current_stage'] = stage
        job['stages'][stage - 1] = {'pct': min(100, pct), 'msg': msg}
        overall = sum(s['pct'] for s in job['stages']) / 5
        job['progress'] = overall
        job['stage_message'] = msg
        # Notify WebSocket clients
        _notify_ws(job_id, {
            'type': 'progress',
            'stage': stage,
            'pct': pct,
            'message': msg,
            'overall': overall,
            'stages': job['stages'],
        })
    
    try:
        from pipeline.main import run_pipeline
        result = run_pipeline(
            video_path=job['video_path'],
            video_url=job['video_url'],
            target_language=job['target_language'],
            progress_cb=progress_cb,
            generate_srt=job['generate_srt'],
            voice_pitch=job['voice_pitch'],
            vol_boost=job['vol_boost'],
            bg_music_vol=job['bg_music_vol'],
        )
        job['status'] = JobStatus.COMPLETED
        job['output_path'] = result['output_path']
        job['transcript'] = result.get('transcript', '')
        job['translation'] = result.get('translation', '')
        job['detected_language'] = result.get('detected_language_code', '')
        job['srt_path'] = result.get('srt_path', '')
        job['progress'] = 100.0
        _notify_ws(job_id, {'type': 'complete', 'job_id': job_id})
    except Exception as e:
        log.error(f'Job {job_id} failed: {e}', exc_info=True)
        job['status'] = JobStatus.FAILED
        job['error'] = str(e)
        _notify_ws(job_id, {'type': 'error', 'message': str(e)})


def _notify_ws(job_id: str, data: dict):
    """Send data to all WebSocket clients watching this job."""
    if job_id in ws_connections:
        msg = json.dumps(data)
        for ws_queue in ws_connections[job_id]:
            try:
                ws_queue.put_nowait(msg)
            except Exception:
                pass


# ── Job status endpoint ──
@app.get('/api/dub/{job_id}', response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, 'Job not found')
    job = jobs[job_id]
    return JobStatusResponse(
        job_id=job_id,
        status=job['status'],
        progress=job['progress'],
        current_stage=job['current_stage'],
        stage_message=job['stage_message'],
        output_ready=job['status'] == JobStatus.COMPLETED,
        transcript=job.get('transcript'),
        translation=job.get('translation'),
        detected_language=job.get('detected_language'),
        error=job.get('error'),
    )


# ── Download endpoint ──
@app.get('/api/download/{job_id}')
async def download_output(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, 'Job not found')
    job = jobs[job_id]
    if job['status'] != JobStatus.COMPLETED:
        raise HTTPException(400, 'Job not completed yet')
    output_path = job['output_path']
    if not os.path.exists(output_path):
        raise HTTPException(404, 'Output file not found')
    filename = f'bhasha_setu_{job["target_language"]}_{job_id}.mp4'
    return FileResponse(output_path, filename=filename, media_type='video/mp4')


# ── Download SRT endpoint ──
@app.get('/api/download/{job_id}/srt')
async def download_srt(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, 'Job not found')
    job = jobs[job_id]
    srt_path = job.get('srt_path', '')
    if not srt_path or not os.path.exists(srt_path):
        raise HTTPException(404, 'SRT file not available')
    return FileResponse(srt_path, filename=f'subtitles_{job_id}.srt', media_type='text/plain')


# ── WebSocket for real-time progress ──
@app.websocket('/ws/progress/{job_id}')
async def ws_progress(websocket: WebSocket, job_id: str):
    await websocket.accept()
    
    import queue
    q = queue.Queue()
    
    if job_id not in ws_connections:
        ws_connections[job_id] = []
    ws_connections[job_id].append(q)
    
    try:
        # Send current status immediately
        if job_id in jobs:
            job = jobs[job_id]
            await websocket.send_json({
                'type': 'status',
                'status': job['status'],
                'progress': job['progress'],
                'stages': job['stages'],
            })
        
        while True:
            try:
                # Check for new messages from background thread
                msg = await asyncio.get_event_loop().run_in_executor(None, lambda: q.get(timeout=0.5))
                await websocket.send_text(msg)
                data = json.loads(msg)
                if data.get('type') in ('complete', 'error'):
                    break
            except queue.Empty:
                # Send heartbeat
                try:
                    await websocket.send_json({'type': 'heartbeat'})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        if job_id in ws_connections:
            try:
                ws_connections[job_id].remove(q)
            except ValueError:
                pass


# ── Chat endpoint ──
@app.post('/api/chat', response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    reply = chat_with_ai(
        message=req.message,
        transcript_context=req.transcript_context or '',
        language=req.language,
        history=req.history,
    )
    return ChatResponse(reply=reply)


# ── Text translate endpoint ──
@app.post('/api/translate', response_model=TranslateResponse)
async def translate_endpoint(req: TranslateRequest):
    if not req.text.strip():
        raise HTTPException(400, 'Text is empty')
    try:
        from pipeline.translate import translate_text_google
        result = translate_text_google(req.text, req.source_lang, req.target_lang)
        return TranslateResponse(translated_text=result)
    except Exception as e:
        raise HTTPException(500, f'Translation failed: {e}')


# ── Cleanup loop ──
async def _cleanup_loop():
    """Periodically clean up expired jobs and their temp files."""
    while True:
        await asyncio.sleep(300)  # every 5 minutes
        now = datetime.now()
        expired = []
        for jid, job in jobs.items():
            created = datetime.fromisoformat(job['created_at'])
            if (now - created).total_seconds() > JOB_EXPIRY_SECONDS:
                expired.append(jid)
        for jid in expired:
            job = jobs.pop(jid, {})
            # Clean temp files
            for key in ('video_path', 'output_path', 'srt_path'):
                path = job.get(key, '')
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception:
                        pass
                    # Try removing parent temp dir
                    parent = os.path.dirname(path)
                    if parent and 'bhasha_' in parent:
                        try:
                            shutil.rmtree(parent, ignore_errors=True)
                        except Exception:
                            pass
            log.info(f'Cleaned up expired job: {jid}')
