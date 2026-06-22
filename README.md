---
title: Bhasha Setu
emoji: 🪷
colorFrom: indigo
colorTo: red
sdk: docker
app_port: 7860
pinned: true
---

# 🪷 Bhasha Setu — AI Video Dubbing for India

> *भाषा सेतु — Language Bridge*

**Bhasha Setu** automatically translates and dubs videos into 12 Indian regional languages using a fully open-source AI pipeline. Upload a video, select a language, and get a fully dubbed video in minutes — completely free.

Built for the **AI for Bharat Hackathon 2026** by **Abhimanyu**, J.C. Bose University of Science & Technology, YMCA Faridabad.

---

## ✨ Features

- 🎬 **End-to-end pipeline** — Upload MP4 → Get dubbed MP4, fully automated
- 🗣️ **12 Indian languages** — Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi, Urdu, Odia, Assamese
- 🧠 **OpenAI Whisper** — State-of-the-art speech recognition for 99+ languages
- 🌐 **Meta NLLB-200** — High-quality neural translation for 200+ languages
- 🔊 **Neural TTS** — Microsoft edge-tts Neural voices for natural speech
- 🔄 **Smart audio sync** — FFmpeg atempo filter matches dubbed audio to video duration
- 💬 **Video-aware AI Chat** — Ask questions about your dubbed video content
- 💾 **Transcription caching** — Avoid re-transcribing the same video
- 🆓 **100% Free** — No API keys, no paid services, no usage limits

---

## 🏗️ Architecture

```
Source Video / URL
    │
    ▼ Stage 1: Fetch
Local temp storage
    │
    ▼ Stage 2: Transcribe
OpenAI Whisper (faster-whisper) → Text (cached)
    │
    ▼ Stage 3: Translate
Meta NLLB-200 → Target language text
    │
    ▼ Stage 4: Synthesize
edge-tts / gTTS → MP3 audio
    │
    ▼ Stage 5: Mux
FFmpeg: atempo sync + merge → Dubbed MP4
```

---

## 🚀 Quick Start

### Run Locally

```bash
# Clone
git clone https://github.com/abhimanyugrover/Bhasha-Setu-AI-Bharat.git
cd Bhasha-Setu-AI-Bharat

# Install dependencies
pip install -r requirements.txt

# Make sure FFmpeg is installed and on PATH

# Run the server
uvicorn backend.main:app --host 0.0.0.0 --port 7860

# Open http://localhost:7860 in your browser
```

### Run with Docker

```bash
docker build -t bhasha-setu .
docker run -p 7860:7860 bhasha-setu
```

### Deploy to Hugging Face Spaces

1. Create a new Space on [huggingface.co/spaces](https://huggingface.co/spaces)
2. Choose **Docker** as the SDK
3. Push this repo to the Space
4. The app will auto-build and deploy

---

## 📁 Project Structure

```
bhasha-setu/
├── Dockerfile              # HF Spaces Docker deployment
├── requirements.txt        # Python dependencies
├── backend/                # FastAPI backend
│   ├── main.py             # API routes, WebSocket, file serving
│   ├── chat.py             # AI Chat via HF Inference API
│   └── models.py           # Pydantic request/response schemas
├── pipeline/               # Core dubbing pipeline
│   ├── config.py           # Language registry, model settings
│   ├── transcribe.py       # Whisper speech-to-text
│   ├── translate.py        # NLLB-200 translation
│   ├── synthesize.py       # edge-tts + gTTS synthesis
│   ├── mux.py              # FFmpeg audio-video mux
│   ├── downloader.py       # yt-dlp video downloader
│   └── main.py             # Pipeline orchestrator
├── frontend/               # Static web app
│   ├── index.html          # Single-page application
│   ├── css/style.css       # Design system
│   └── js/                 # App logic, API client, components
├── output/                 # Temp dubbed videos (auto-cleanup)
├── cache/                  # Transcription cache
└── logs/                   # Rotating log files
```

---

## 🧠 TTS Engine Assignment

| Language | Engine | Voice |
|---|---|---|
| **Hindi** | edge-tts Neural | hi-IN-SwaraNeural |
| Tamil | edge-tts Neural | ta-IN-PallaviNeural |
| Telugu | edge-tts Neural | te-IN-MohanNeural |
| Kannada | edge-tts Neural | kn-IN-SapnaNeural |
| Malayalam | edge-tts Neural | ml-IN-SobhanaNeural |
| Bengali | edge-tts Neural | bn-IN-TanishaaNeural |
| Marathi | edge-tts Neural | mr-IN-AarohiNeural |
| Gujarati | edge-tts Neural | gu-IN-NiranjanNeural |
| Urdu | edge-tts Neural | ur-PK-AsadNeural |
| Punjabi | Google TTS | pa |
| Odia | Google TTS | or |
| Assamese | Google TTS | as |

---

## 🛠️ Tech Stack

| Component | Technology | Cost |
|---|---|---|
| Frontend | HTML/CSS/JS (vanilla) | Free |
| Backend | FastAPI + Uvicorn | Free |
| Transcription | OpenAI Whisper (faster-whisper) | Free |
| Translation | Meta NLLB-200 | Free |
| TTS | Microsoft edge-tts + Google gTTS | Free |
| Audio/Video | FFmpeg | Free |
| Video Download | yt-dlp | Free |
| AI Chat | HuggingFace Inference API | Free |
| Hosting | Hugging Face Spaces | Free |

**Total monthly cost: $0** | **API keys required: 0**

---

## 👨‍💻 Author

**Abhimanyu**
B.Tech Computer Science · J.C. Bose University of Science & Technology, YMCA Faridabad

Built for **AI for Bharat Hackathon 2026** 🏆

---

## 📄 License

MIT License — free to use, modify, and share.
