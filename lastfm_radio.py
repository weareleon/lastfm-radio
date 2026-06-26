#!/usr/bin/env python3
"""
lastfm_radio.py — Personal Last.fm Radio Station
Streams your Last.fm top tracks to Icecast via ffmpeg.
Downloads tracks via yt-dlp, shuffles, streams continuously.
Auto-refreshes library when your top tracks change.
Includes a Flask dashboard API + web UI on port 5100.

Setup: copy config.example.py to config.py and fill in your details.
"""

import time
import random
import subprocess
import threading
import requests
import logging
from pathlib import Path
from flask import Flask, jsonify, send_file
from flask_cors import CORS

# ──────────────────────────────────────────────
# CONFIG — edit these values or use config.py
# ──────────────────────────────────────────────
try:
    from config import *
except ImportError:
    # Fallback defaults — copy config.example.py to config.py
    LASTFM_API_KEY   = "YOUR_LASTFM_API_KEY"
    LASTFM_USER      = "YOUR_LASTFM_USERNAME"
    LASTFM_PERIOD    = "1month"   # 7day | 1month | 3month | 6month | 12month | overall
    LASTFM_LIMIT     = 50        # max tracks to pull (up to 1000)

    ICECAST_HOST     = "localhost"
    ICECAST_PORT     = 8000
    ICECAST_PASSWORD = "hackme"
    ICECAST_MOUNT    = "/lastfmradio"
    ICECAST_NAME     = "My Last.fm Radio"
    ICECAST_GENRE    = "Mixed"

    MUSIC_DIR        = Path("lastfm_music")
    BLOCKED_WORDS    = Path("blocked-words.txt")
    REFRESH_INTERVAL = 1800   # seconds between Last.fm polls
    BITRATE          = "192k"
    DASHBOARD_PORT   = 5100

# ──────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("lastfm_radio")

# ──────────────────────────────────────────────
# SHARED STATE
# ──────────────────────────────────────────────
now_playing: dict       = {"artist": "", "title": "", "file": ""}
now_playing_lock        = threading.Lock()
library_state: list[dict] = []
library_lock            = threading.Lock()

def set_now_playing(path: Path):
    name   = path.stem
    parts  = name.split(" - ", 1)
    artist = parts[0].strip() if len(parts) == 2 else ""
    title  = parts[1].strip() if len(parts) == 2 else name
    with now_playing_lock:
        now_playing["artist"] = artist
        now_playing["title"]  = title
        now_playing["file"]   = path.name
    log.info(f"Now playing: {artist} - {title}")

def set_library(paths: list[Path]):
    entries = []
    for p in paths:
        name   = p.stem
        parts  = name.split(" - ", 1)
        artist = parts[0].strip() if len(parts) == 2 else ""
        title  = parts[1].strip() if len(parts) == 2 else name
        entries.append({"artist": artist, "title": title, "file": p.name})
    with library_lock:
        library_state.clear()
        library_state.extend(entries)

# ──────────────────────────────────────────────
# LAST.FM API
# ──────────────────────────────────────────────
def fetch_top_tracks() -> list[dict]:
    url = "https://ws.audioscrobbler.com/2.0/"
    params = {
        "method":  "user.getTopTracks",
        "user":    LASTFM_USER,
        "api_key": LASTFM_API_KEY,
        "period":  LASTFM_PERIOD,
        "limit":   LASTFM_LIMIT,
        "format":  "json",
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        tracks = r.json()["toptracks"]["track"]
        return [{"artist": t["artist"]["name"], "title": t["name"]} for t in tracks]
    except Exception as e:
        log.error(f"Last.fm fetch failed: {e}")
        return []

def fetch_recent_scrobbles(limit: int = 10) -> list[dict]:
    url = "https://ws.audioscrobbler.com/2.0/"
    params = {
        "method":  "user.getRecentTracks",
        "user":    LASTFM_USER,
        "api_key": LASTFM_API_KEY,
        "limit":   limit,
        "format":  "json",
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        tracks = r.json()["recenttracks"]["track"]
        result = []
        for t in tracks:
            result.append({
                "artist": t["artist"]["#text"],
                "title":  t["name"],
                "album":  t["album"]["#text"],
                "image":  t["image"][-1]["#text"] if t.get("image") else "",
                "now":    bool(t.get("@attr", {}).get("nowplaying")),
            })
        return result
    except Exception as e:
        log.error(f"Last.fm scrobbles fetch failed: {e}")
        return []

def fetch_user_info() -> dict:
    url = "https://ws.audioscrobbler.com/2.0/"
    params = {
        "method":  "user.getInfo",
        "user":    LASTFM_USER,
        "api_key": LASTFM_API_KEY,
        "format":  "json",
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        u = r.json()["user"]
        return {
            "name":       u["name"],
            "realname":   u.get("realname", ""),
            "scrobbles":  u["playcount"],
            "registered": u["registered"]["#text"],
            "image":      u["image"][-1]["#text"] if u.get("image") else "",
            "url":        u["url"],
        }
    except Exception as e:
        log.error(f"Last.fm user info fetch failed: {e}")
        return {}

# ──────────────────────────────────────────────
# BLOCKED WORDS
# ──────────────────────────────────────────────
def track_filename(artist: str, title: str) -> str:
    safe = lambda s: "".join(c if c.isalnum() or c in " -_" else "_" for c in s).strip()
    return f"{safe(artist)} - {safe(title)}.mp3"

def load_blocked_words() -> list[str]:
    if not BLOCKED_WORDS.exists():
        return []
    words = []
    with open(BLOCKED_WORDS, "r", encoding="utf-8") as f:
        for line in f:
            word = line.strip().lower()
            if word and not word.startswith("#"):
                words.append(word)
    if words:
        log.info(f"Blocked words loaded: {words}")
    return words

def is_blocked(title: str, blocked: list[str]) -> bool:
    return any(word in title.lower() for word in blocked)

# ──────────────────────────────────────────────
# DOWNLOADER
# ──────────────────────────────────────────────
def download_track(artist: str, title: str) -> "Path | None":
    fname    = track_filename(artist, title)
    dest     = MUSIC_DIR / fname
    if dest.exists():
        return dest

    query       = f"{artist} {title} audio"
    temp_output = MUSIC_DIR / f"_tmp_{artist}_{title}.%(ext)s"
    temp_mp3    = MUSIC_DIR / f"_tmp_{artist}_{title}.mp3"

    cmd = [
        "python", "-m", "yt_dlp",
        f"ytsearch1:{query}",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--output", str(temp_output),
        "--no-playlist",
        "--quiet",
        "--no-warnings",
    ]
    try:
        log.info(f"Downloading: {artist} - {title}")
        subprocess.run(cmd, timeout=120, check=True)
        if temp_mp3.exists():
            temp_mp3.rename(dest)
            return dest
    except subprocess.TimeoutExpired:
        log.warning(f"Timeout downloading: {artist} - {title}")
    except subprocess.CalledProcessError as e:
        log.warning(f"yt-dlp error for {artist} - {title}: {e}")
    return None

def sync_library(tracks: list[dict]) -> list[Path]:
    MUSIC_DIR.mkdir(exist_ok=True)
    blocked   = load_blocked_words()
    available = []
    for t in tracks:
        if is_blocked(t["title"], blocked):
            log.info(f"Skipping blocked track: {t['artist']} - {t['title']}")
            continue
        path = download_track(t["artist"], t["title"])
        if path and path.exists():
            available.append(path)
    return available

# ──────────────────────────────────────────────
# STREAMER
# ──────────────────────────────────────────────
class RadioStreamer:
    def __init__(self):
        self.playlist: list[Path] = []
        self.lock               = threading.Lock()
        self._ffmpeg            = None
        self._stop_event        = threading.Event()
        self._playlist_updated  = threading.Event()

    def update_playlist(self, paths: list[Path]):
        shuffled = paths.copy()
        random.shuffle(shuffled)
        with self.lock:
            self.playlist = shuffled
        set_library(shuffled)
        self._playlist_updated.set()
        log.info(f"Playlist updated: {len(shuffled)} tracks")

    def _write_concat(self, paths: list[Path]) -> Path:
        """Write ffmpeg concat file, looped 999x for near-infinite playback."""
        concat_file = MUSIC_DIR / "playlist.txt"
        looped      = paths * 999
        with open(concat_file, "w", encoding="utf-8") as f:
            for p in looped:
                safe = str(p.resolve()).replace("\\", "/")
                f.write(f"file '{safe}'\n")
        return concat_file

    def _launch_ffmpeg(self, concat_file: Path) -> subprocess.Popen:
        icecast_url = (
            f"icecast://source:{ICECAST_PASSWORD}@"
            f"{ICECAST_HOST}:{ICECAST_PORT}{ICECAST_MOUNT}"
        )
        cmd = [
            "ffmpeg", "-re",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-vn",
            "-acodec", "libmp3lame",
            "-ab", BITRATE,
            "-ar", "44100", "-ac", "2",
            "-f", "mp3",
            "-content_type", "audio/mpeg",
            "-ice_name", ICECAST_NAME,
            "-ice_genre", ICECAST_GENRE,
            "-ice_public", "0",
            icecast_url, "-y",
        ]
        return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _now_playing_tracker(self, playlist: list[Path]):
        """Updates now_playing state by timing each track's duration."""
        try:
            import mutagen.mp3
            use_mutagen = True
        except ImportError:
            use_mutagen = False
            log.warning("mutagen not installed — using 3min fallback. Run: pip install mutagen")

        idx = 0
        while not self._stop_event.is_set():
            if not playlist:
                time.sleep(1)
                continue
            track = playlist[idx % len(playlist)]
            if track.exists():
                set_now_playing(track)
                if use_mutagen:
                    try:
                        import mutagen.mp3
                        duration = mutagen.mp3.MP3(str(track)).info.length
                    except Exception:
                        duration = 180
                else:
                    duration = 180
            else:
                duration = 0
            self._stop_event.wait(timeout=duration)
            idx += 1

    def run(self):
        log.info("Streamer started")
        while not self._stop_event.is_set():
            with self.lock:
                current_playlist = self.playlist.copy()

            if not current_playlist:
                log.info("Playlist empty, waiting...")
                time.sleep(5)
                continue

            concat_file  = self._write_concat(current_playlist)
            log.info(f"Starting continuous stream ({len(current_playlist)} tracks looping)")
            proc         = self._launch_ffmpeg(concat_file)
            self._ffmpeg = proc

            tracker = threading.Thread(
                target=self._now_playing_tracker,
                args=(current_playlist,),
                daemon=True,
            )
            tracker.start()

            self._playlist_updated.clear()
            while not self._stop_event.is_set():
                if proc.poll() is not None:
                    log.warning("ffmpeg exited unexpectedly, restarting...")
                    break
                if self._playlist_updated.is_set():
                    log.info("Playlist changed — restarting stream...")
                    proc.terminate()
                    proc.wait()
                    break
                time.sleep(2)

            self._ffmpeg = None

    def stop(self):
        self._stop_event.set()
        if self._ffmpeg:
            self._ffmpeg.terminate()

# ──────────────────────────────────────────────
# FLASK DASHBOARD API
# ──────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

@app.route("/")
def dashboard():
    return send_file("dashboard.html")

@app.route("/api/now-playing")
def api_now_playing():
    with now_playing_lock:
        data = dict(now_playing)
    return jsonify(data)

@app.route("/api/library")
def api_library():
    with library_lock:
        data = list(library_state)
    return jsonify(data)

@app.route("/api/scrobbles")
def api_scrobbles():
    return jsonify(fetch_recent_scrobbles(10))

@app.route("/api/user")
def api_user():
    return jsonify(fetch_user_info())

@app.route("/api/status")
def api_status():
    with now_playing_lock:
        np = dict(now_playing)
    with library_lock:
        count = len(library_state)
    return jsonify({
        "streaming":   bool(np["title"]),
        "track_count": count,
        "mount":       ICECAST_MOUNT,
        "stream_url":  f"http://{ICECAST_HOST}:{ICECAST_PORT}{ICECAST_MOUNT}",
        "user":        LASTFM_USER,
    })

def run_flask():
    log.info(f"Dashboard running on http://localhost:{DASHBOARD_PORT}")
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False, use_reloader=False)

# ──────────────────────────────────────────────
# REFRESH LOOP
# ──────────────────────────────────────────────
def refresh_loop(streamer: RadioStreamer):
    known_titles: set[str] = set()
    while True:
        log.info("Fetching top tracks from Last.fm...")
        tracks = fetch_top_tracks()
        if not tracks:
            time.sleep(60)
            continue

        new_tracks = [t for t in tracks if t["title"] not in known_titles]
        if new_tracks:
            log.info(f"{len(new_tracks)} new track(s) to download")

        all_paths    = sync_library(tracks)
        known_titles = {t["title"] for t in tracks}

        if all_paths:
            streamer.update_playlist(all_paths)

        log.info(f"Library: {len(all_paths)} tracks. Next refresh in {REFRESH_INTERVAL // 60}min.")
        time.sleep(REFRESH_INTERVAL)

# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
def main():
    log.info("=== Last.fm Radio ===")
    log.info(f"User: {LASTFM_USER} | Period: {LASTFM_PERIOD} | Limit: {LASTFM_LIMIT}")
    log.info(f"Mount: {ICECAST_MOUNT} on {ICECAST_HOST}:{ICECAST_PORT}")

    streamer = RadioStreamer()

    log.info("Initial library sync...")
    tracks = fetch_top_tracks()
    if tracks:
        paths = sync_library(tracks)
        streamer.update_playlist(paths)
    else:
        log.warning("No tracks fetched on startup — will retry in refresh loop")

    flask_thread   = threading.Thread(target=run_flask, daemon=True)
    refresh_thread = threading.Thread(target=refresh_loop, args=(streamer,), daemon=True)
    flask_thread.start()
    refresh_thread.start()

    try:
        streamer.run()
    except KeyboardInterrupt:
        log.info("Stopping...")
        streamer.stop()

if __name__ == "__main__":
    main()
