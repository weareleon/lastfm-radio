# lastfm-radio

A personal internet radio station that streams your Last.fm top tracks to Icecast — automatically, continuously, and shuffled. Comes with a web dashboard showing now playing, your library, and recent scrobbles.

![Last.fm Radio Dashboard](https://ohzihhthelwvyakzpvdh.supabase.co/storage/v1/object/sign/cdn/57192593-3a1f-4b8c-a7e1-862d1f488178/lastfmradiodemo.png?token=eyJraWQiOiJzdG9yYWdlLXVybC1zaWduaW5nLWtleV80OTg0N2Y0Ny1iN2RiLTQwNGUtYTAwZS1mMDk4NGM2MWEyMTAiLCJhbGciOiJIUzI1NiJ9.eyJ1cmwiOiJjZG4vNTcxOTI1OTMtM2ExZi00YjhjLWE3ZTEtODYyZDFmNDg4MTc4L2xhc3RmbXJhZGlvZGVtby5wbmciLCJzY29wZSI6ImRvd25sb2FkIiwiaWF0IjoxNzgyNDgzODMwLCJleHAiOjE3ODI0ODc0MzB9.tb-IXmiGCr4_4syw-qPHdcnBnIaskEWUp7a1erX9kL0)

## How it works

1. Pulls your top tracks from the Last.fm API
2. Downloads them via yt-dlp (YouTube search)
3. Streams them continuously to Icecast via ffmpeg (no gaps between tracks)
4. Refreshes every 30 minutes — new tracks get downloaded and added to the rotation
5. Serves a web dashboard at `http://localhost:5100`

## Requirements

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/download.html) installed and in your PATH
- [Icecast](https://icecast.org/download/) running locally (or remotely)
- A [Last.fm API key](https://www.last.fm/api/account/create) (free)

## Setup

**1. Clone the repo**
```bash
git clone https://github.com/weareleon/lastfm-radio
cd lastfm-radio
```

**2. Install Python dependencies**
```bash
pip install -r requirements.txt
```

**3. Configure**
```bash
cp config.example.py config.py
```

Open `config.py` and fill in:
- `LASTFM_API_KEY` — from https://www.last.fm/api/account/create
- `LASTFM_USER` — your Last.fm username
- `ICECAST_PASSWORD` — your Icecast source password
- Adjust `LASTFM_PERIOD`, `LASTFM_LIMIT`, mount, bitrate etc. as needed

**4. Run**
```bash
python lastfm_radio.py
```

The script will:
- Fetch your top tracks and start downloading them
- Begin streaming to Icecast once tracks are ready
- Start the dashboard at `http://localhost:5100`

## Dashboard

Open `http://localhost:5100` in your browser.

Features:
- Now playing with album art
- Inline stream player with volume control
- Searchable library of downloaded tracks
- Recent scrobbles from your Last.fm profile
- Your Last.fm user info and scrobble count

## Blocking tracks

Create a `blocked-words.txt` file in the project folder — one word per line. Any track whose title contains a blocked word will be skipped at download time.

```
# blocked-words.txt
karaoke
live
instrumental
remix
# lines starting with # are comments
```

The list reloads every refresh cycle so you can edit it without restarting.

## Configuration reference

| Option | Default | Description |
|---|---|---|
| `LASTFM_API_KEY` | — | Your Last.fm API key |
| `LASTFM_USER` | — | Last.fm username to pull tracks from |
| `LASTFM_PERIOD` | `1month` | Timeframe: `7day` `1month` `3month` `6month` `12month` `overall` |
| `LASTFM_LIMIT` | `50` | Number of top tracks (max 1000) |
| `ICECAST_HOST` | `localhost` | Icecast server host |
| `ICECAST_PORT` | `8000` | Icecast port |
| `ICECAST_PASSWORD` | `hackme` | Icecast source password |
| `ICECAST_MOUNT` | `/lastfmradio` | Stream mount point |
| `REFRESH_INTERVAL` | `1800` | Seconds between Last.fm polls |
| `BITRATE` | `192k` | MP3 stream bitrate |
| `DASHBOARD_PORT` | `5100` | Port for the web dashboard |

## API endpoints

The Flask server exposes a small REST API:

| Endpoint | Description |
|---|---|
| `GET /api/now-playing` | Current track (artist, title, file) |
| `GET /api/library` | Full downloaded track list |
| `GET /api/scrobbles` | Last 10 Last.fm scrobbles |
| `GET /api/user` | Last.fm user info |
| `GET /api/status` | Stream status + track count |

## Notes

- Track downloads use yt-dlp searching YouTube. Not every track will be found, and occasionally the wrong version gets grabbed — those get skipped silently.
- The stream uses ffmpeg's concat demuxer so there are no gaps or reconnects between tracks.
- The playlist loops indefinitely (999 repetitions) and reshuffles when new tracks are added.
- `config.py` and `lastfm_music/` are in `.gitignore` — your API key and downloaded music stay local.

## License

MIT
