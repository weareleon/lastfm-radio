# config.example.py
# Copy this file to config.py and fill in your details.
# config.py is in .gitignore — your secrets stay local.

from pathlib import Path

# ── Last.fm ──────────────────────────────────
# Get a free API key at https://www.last.fm/api/account/create
LASTFM_API_KEY   = "YOUR_LASTFM_API_KEY"
LASTFM_USER      = "YOUR_LASTFM_USERNAME"
LASTFM_PERIOD    = "1month"   # 7day | 1month | 3month | 6month | 12month | overall
LASTFM_LIMIT     = 50         # number of top tracks to pull (max 1000)

# ── Icecast ───────────────────────────────────
ICECAST_HOST     = "localhost"
ICECAST_PORT     = 8000
ICECAST_PASSWORD = "hackme"        # your Icecast source password
ICECAST_MOUNT    = "/lastfmradio"
ICECAST_NAME     = "My Last.fm Radio"
ICECAST_GENRE    = "Mixed"

# ── Paths & tuning ────────────────────────────
MUSIC_DIR        = Path("lastfm_music")
BLOCKED_WORDS    = Path("blocked-words.txt")
REFRESH_INTERVAL = 1800   # seconds between Last.fm polls (default: 30 min)
BITRATE          = "192k"
DASHBOARD_PORT   = 5100
