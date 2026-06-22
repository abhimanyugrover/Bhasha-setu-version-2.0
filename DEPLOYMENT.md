# Bhasha Setu — Deployment Guide
## Getting a Public URL for Hackathon Submission

---

## Option A — Streamlit Community Cloud ✅ RECOMMENDED
**Free, one-click, permanent public URL like `https://bhasha-setu.streamlit.app`**

### Step 1 — Push to GitHub
```bash
# In your project root
git init
git add .
git commit -m "Initial Bhasha Setu submission"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/bhasha-setu.git
git push -u origin main
```

### Step 2 — Connect to Streamlit Cloud
1. Go to **https://share.streamlit.io** → Sign in with GitHub
2. Click **"New app"**
3. Select your repo: `YOUR_USERNAME/bhasha-setu`
4. Main file path: `app.py`
5. Click **"Deploy"**

### Step 3 — Add AWS Secrets (CRITICAL)
Without this, the AWS pipeline won't work on the cloud.

1. In your deployed app's dashboard → **⚙️ Settings → Secrets**
2. Paste this (fill in your real values):

```toml
AWS_ACCESS_KEY_ID     = "AKIA..."
AWS_SECRET_ACCESS_KEY = "xxxx..."
AWS_DEFAULT_REGION    = "ap-south-1"

# Optional summarizer (pick one if you want summaries)
# GROQ_API_KEY   = "gsk_..."
# GEMINI_API_KEY = "AIza..."
```

### Step 4 — Add ffmpeg to Streamlit Cloud
Create this file in your repo root: **`packages.txt`**
```
ffmpeg
```
Streamlit Cloud reads `packages.txt` and installs apt packages automatically.

### Done!
Your app will be live at: `https://YOUR_USERNAME-bhasha-setu-app-XXXX.streamlit.app`

---

## Option B — AWS EC2 (Best for heavy workloads, uses IAM role)
**Ideal since the app already uses AWS — no credentials in code at all.**

### Step 1 — Launch EC2 Instance
- Instance type: `t3.medium` (2 vCPU, 4 GB RAM) or larger
- OS: Ubuntu 22.04 LTS
- Security group: open TCP port **8501** (Streamlit) and **443** (HTTPS)
- **Attach an IAM Role** with these policies:
  - `AmazonS3FullAccess` (or scoped to `bhasha-setu-videos` bucket)
  - `AmazonTranscribeFullAccess`
  - `TranslateReadOnly`
  - `AmazonPollyFullAccess`
  - `AmazonBedrockFullAccess` (optional, for LLM polish)

### Step 2 — Install dependencies
```bash
sudo apt update && sudo apt install -y python3-pip ffmpeg nginx certbot python3-certbot-nginx
pip3 install -r requirements.txt
```

### Step 3 — Clone and run
```bash
git clone https://github.com/YOUR_USERNAME/bhasha-setu.git
cd bhasha-setu
# No .env needed — IAM role provides credentials automatically

# Run with nohup so it stays alive after SSH disconnect
nohup streamlit run app.py --server.port 8501 --server.address 0.0.0.0 &
```

### Step 4 — Point a domain and get HTTPS (optional but looks professional)
```bash
# Add an A record in your DNS pointing yourdomain.com → EC2 public IP
sudo certbot --nginx -d yourdomain.com
```

Or just use the EC2 public IP: `http://3.X.X.X:8501`

---

## Option C — Railway.app (Easiest after Streamlit Cloud)
**Free tier, Docker-based, simple env var management.**

### Create `Dockerfile` in project root:
```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

1. Go to **https://railway.app** → New Project → Deploy from GitHub
2. Add environment variables:
   - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`
3. Railway gives you a URL like `https://bhasha-setu-production.up.railway.app`

---

## Option D — ngrok (Quick demo only, not stable)
```bash
# Install: https://ngrok.com/download
streamlit run app.py &
ngrok http 8501
# Copy the https://XXXX.ngrok.io URL
```
⚠️ Free ngrok URLs expire after 8 hours. Not recommended for final submission.

---

## Checklist Before Submitting

- [ ] App loads at the public URL without errors
- [ ] AWS credentials are set (Secrets on Streamlit Cloud / env vars / IAM role)
- [ ] `ffmpeg` is installed on the deployment server (`packages.txt` for Streamlit Cloud)
- [ ] S3 bucket `bhasha-setu-videos` exists in `ap-south-1`
- [ ] Test a short video dub end-to-end before submitting the link
- [ ] The Introduction tab explains the project clearly to judges

---

## Streamlit Secrets Template (`.streamlit/secrets.toml`)
Create this file locally for testing. **Never commit it to GitHub.**

```toml
AWS_ACCESS_KEY_ID     = "AKIA..."
AWS_SECRET_ACCESS_KEY = "xxxx..."
AWS_DEFAULT_REGION    = "ap-south-1"
```

Add `.streamlit/secrets.toml` to your `.gitignore`:
```
.streamlit/secrets.toml
output/
cache/
logs/
*.mp4
*.mp3
*.wav
```

---

## AWS IAM Policy — Minimum Required Permissions
If you want to create a scoped IAM user instead of full access:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::bhasha-setu-videos/*"
    },
    {
      "Effect": "Allow",
      "Action": ["transcribe:StartTranscriptionJob", "transcribe:GetTranscriptionJob"],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["translate:TranslateText"],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["polly:SynthesizeSpeech"],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel"],
      "Resource": "arn:aws:bedrock:ap-south-1::foundation-model/anthropic.claude-haiku-20240307-v1:0"
    }
  ]
}
```
