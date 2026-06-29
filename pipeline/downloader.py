"""
Bhasha Setu — Video URL Downloader
Downloads videos from YouTube and 1000+ other sites using yt-dlp.

Supports: YouTube, Vimeo, Instagram, Twitter/X, Facebook, Dailymotion,
          TED, Bilibili, Reddit, and most public video platforms.

Quality cap: 720p MP4 — keeps file sizes manageable for the dubbing pipeline.

Public API:
    get_video_info(url)        → metadata dict (no download, instant)
    download_to_temp(url, ...) → local temp path (pipeline handles S3 upload)
"""

import os
import tempfile
import logging
from typing import Callable, Optional

log = logging.getLogger(__name__)

MAX_HEIGHT = 720

_PLATFORM_MAP = {
    "youtube":     "YouTube",
    "vimeo":       "Vimeo",
    "instagram":   "Instagram",
    "twitter":     "Twitter / X",
    "facebook":    "Facebook",
    "dailymotion": "Dailymotion",
    "ted":         "TED",
    "bilibili":    "Bilibili",
    "reddit":      "Reddit",
}

_FORMAT = (
    f"bestvideo[height<={MAX_HEIGHT}][ext=mp4]+bestaudio[ext=m4a]"
    f"/bestvideo[height<={MAX_HEIGHT}]+bestaudio"
    f"/best[height<={MAX_HEIGHT}][ext=mp4]"
    f"/best[height<={MAX_HEIGHT}]"
    f"/best"
)

# Realistic Chrome user-agent — avoids most platform bot-detection
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def _platform(info: dict) -> str:
    extractor = info.get("extractor_key", "").lower()
    return next(
        (v for k, v in _PLATFORM_MAP.items() if k in extractor),
        extractor.capitalize() or "Unknown"
    )


def _friendly_error(e) -> str:
    msg = str(e)
    if "Private video"    in msg: return "This video is private and cannot be accessed."
    if "age"              in msg.lower(): return "This video is age-restricted."
    if "unavailable"      in msg.lower(): return "This video is unavailable or has been removed."
    if "removed"          in msg.lower(): return "This video has been removed."
    if "copyright"        in msg.lower(): return "Video unavailable due to copyright restrictions."
    if "confirm your age" in msg.lower(): return "This video requires sign-in to watch."
    if "403"              in msg: return "YouTube blocked the request (403). Try updating yt-dlp: pip install --upgrade yt-dlp"
    return f"Could not access video: {msg[:200]}"


def _make_opts(extra: dict = {}) -> dict:
    """Base yt-dlp options shared by all calls."""
    opts = {
        "quiet":       True,
        "no_warnings": True,
        "noplaylist":  True,
        "http_headers": {"User-Agent": _UA},
        "extractor_args": {"youtube": {"player_client": ["android", "ios"]}},
        **extra,
    }
    
    # Auto-detect cookies.txt uploaded by the user to bypass YouTube datacenter blocks
    for path in ["cookies.txt", "/content/cookies.txt"]:
        if os.path.exists(path):
            log.info(f"Using cookies file: {path}")
            opts["cookiefile"] = path
            break
            
    return opts


def _with_cookie_fallback(build_opts_fn, run_fn):
    """
    Try run_fn(opts_with_chrome_cookies), fall back to run_fn(opts_without_cookies)
    if Chrome is not installed or cookies can't be read.
    """
    try:
        opts = build_opts_fn(cookies=True)
        return run_fn(opts)
    except Exception as e:
        err = str(e).lower()
        # If the error is about cookies/browser, retry without them
        if any(w in err for w in ("chrome", "cookie", "browser", "keyring")):
            log.warning(f"Cookie read failed ({e}), retrying without cookies…")
            opts = build_opts_fn(cookies=False)
            return run_fn(opts)
        raise


# ── Public: metadata fetch ────────────────────────────────────────────────────

def get_video_info(url: str) -> dict:
    """
    Fetch video metadata WITHOUT downloading. Fast (~1-2 seconds).

    Returns dict: title, duration (seconds|None), thumbnail (url|None),
                  uploader (str|None), platform (str), url (str)

    Raises ValueError for private/unavailable/bad URLs.
    Raises RuntimeError if yt-dlp is not installed.
    """
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("yt-dlp not installed. Run: pip install yt-dlp")

    def _build(cookies: bool):
        o = _make_opts({"skip_download": True})
        if cookies:
            o["cookiesfrombrowser"] = ("chrome",)
        return o

    def _run(opts):
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise ValueError("Could not fetch video information.")
            return info

    try:
        info = _with_cookie_fallback(_build, _run)
        return {
            "title":     info.get("title", "Untitled Video"),
            "duration":  info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "uploader":  info.get("uploader") or info.get("channel"),
            "platform":  _platform(info),
            "url":       url,
        }
    except yt_dlp.utils.DownloadError as e:
        raise ValueError(_friendly_error(e))


# ── Public: download to temp ──────────────────────────────────────────────────

def download_to_temp(
    url:         str,
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> str:
    """
    Download a video from URL to a system temp file. Returns the local path.

    The CALLER must delete the file after use.
    The pipeline's Stage 1 calls this then immediately uploads to S3.

    Args:
        url:         Public video URL.
        progress_cb: Optional callable(percent: float, message: str).

    Returns:
        Absolute path to downloaded MP4 temp file.

    Raises:
        ValueError  : private / unavailable / bad URL
        RuntimeError: yt-dlp not installed, or unexpected failure
    """
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("yt-dlp not installed. Run: pip install yt-dlp")

    tmp_dir  = tempfile.mkdtemp(prefix="bhasha_setu_")
    out_tmpl = os.path.join(tmp_dir, "%(id)s.%(ext)s")
    _last    = [-1.0]

    def _hook(d: dict):
        if not progress_cb:
            return
        status = d.get("status", "")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done  = d.get("downloaded_bytes", 0)
            pct   = min(95.0, (done / total * 100) if total else _last[0] + 0.5)
            if pct - _last[0] >= 1.0:
                _last[0] = pct
                speed = (d.get("speed") or 0) / (1024 * 1024)
                eta   = d.get("eta") or 0
                msg   = f"Fetching video… {pct:.0f}%"
                if speed > 0.01: msg += f" · {speed:.1f} MB/s"
                if eta   > 0:    msg += f" · ~{eta}s left"
                progress_cb(pct, msg)
        elif status == "finished":
            progress_cb(97.0, "Merging audio & video streams…")

    def _build(cookies: bool):
        o = _make_opts({
            "format":              _FORMAT,
            "outtmpl":             out_tmpl,
            "progress_hooks":      [_hook],
            "merge_output_format": "mp4",
            "retries":             5,
            "fragment_retries":    5,
        })
        if cookies:
            o["cookiesfrombrowser"] = ("chrome",)
        return o

    def _run(opts):
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=True)

    try:
        if progress_cb:
            progress_cb(0.0, "Connecting to video source…")

        info = _with_cookie_fallback(_build, _run)

        if not info:
            raise ValueError("Download returned no information.")

        # Find the output file in tmp_dir
        mp4s = sorted(
            [os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir)
             if f.endswith(".mp4")],
            key=os.path.getmtime,
        )
        if not mp4s:
            # Check for any video file if mp4 merge didn't happen
            all_vids = sorted(
                [os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir)
                 if os.path.splitext(f)[1] in (".mp4", ".mkv", ".webm")],
                key=os.path.getmtime,
            )
            if not all_vids:
                raise RuntimeError("Download finished but no output file found.")
            actual = all_vids[-1]
        else:
            actual = mp4s[-1]

        size_mb = os.path.getsize(actual) / (1024 * 1024)
        if progress_cb:
            progress_cb(100.0, f"Video ready — {size_mb:.1f} MB")
        log.info(f"Temp download: {actual} ({size_mb:.1f} MB)")
        return actual

    except yt_dlp.utils.DownloadError as e:
        raise ValueError(_friendly_error(e))
    except Exception as e:
        raise RuntimeError(f"Unexpected download error: {e}") from e
