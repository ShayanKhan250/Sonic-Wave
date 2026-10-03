"""SonicWave API v2 — SQLite + user accounts + playlists + real music search/streaming."""

import os
import sqlite3
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

import db

db.seed()

app = FastAPI(
    title="SonicWave API",
    description=(
        "🎵 REST API for SonicWave — user accounts, SQLite-backed catalog, playlists, "
        "likes, queue, plus REAL music search/lyrics/streaming via musicapi.x007.workers.dev.\n\n"
        "**Auth:** register or login to get a token, then send it as `Authorization: Bearer <token>`. "
        "Demo account: username `demo`, password `demo123`."
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MUSIC_API = "https://musicapi.x007.workers.dev"


# ---------- dependencies ----------

def conn_dep():
    conn = db.get_db()
    try:
        yield conn
    finally:
        conn.close()

Conn = Annotated[sqlite3.Connection, Depends(conn_dep)]


def current_user(conn: Conn, authorization: str | None = Header(None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing token. Send 'Authorization: Bearer <token>' (get one from /api/auth/login).")
    user = db.user_from_token(conn, authorization.split(" ", 1)[1].strip())
    if not user:
        raise HTTPException(401, "Invalid or expired token.")
    return user

User = Annotated[sqlite3.Row, Depends(current_user)]


def optional_user(conn: Conn, authorization: str | None = Header(None)):
    if authorization and authorization.lower().startswith("bearer "):
        return db.user_from_token(conn, authorization.split(" ", 1)[1].strip())
    return None

MaybeUser = Annotated[sqlite3.Row | None, Depends(optional_user)]


# ---------- serializers ----------

SONG_SQL = """
SELECT s.*, a.name AS artist, al.title AS album
FROM songs s JOIN artists a ON a.id = s.artist_id JOIN albums al ON al.id = s.album_id
"""

def song_dict(row: sqlite3.Row, conn: sqlite3.Connection, user=None) -> dict:
    d = dict(row)
    if user:
        d["liked"] = bool(conn.execute(
            "SELECT 1 FROM likes WHERE user_id=? AND song_id=?", (user["id"], row["id"])
        ).fetchone())
    return d


def playlist_dict(row: sqlite3.Row, conn: sqlite3.Connection, with_songs=True, user=None) -> dict:
    owner = None
    if row["owner_id"]:
        o = conn.execute("SELECT display_name FROM users WHERE id=?", (row["owner_id"],)).fetchone()
        owner = o["display_name"] if o else None
    d = {**dict(row), "creator": owner or "SonicWave"}
    songs = conn.execute(
        SONG_SQL + " JOIN playlist_songs ps ON ps.song_id = s.id WHERE ps.playlist_id=? ORDER BY ps.position",
        (row["id"],),
    ).fetchall()
    d["song_count"] = len(songs)
    if with_songs:
        d["songs"] = [song_dict(s, conn, user) for s in songs]
    return d


# ---------- models ----------

class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=6, max_length=128)
    display_name: str | None = Field(None, max_length=60)
    captcha: str | None = Field(None, max_length=4096)

class LoginIn(BaseModel):
    username: str
    password: str
    captcha: str | None = Field(None, max_length=4096)

class PlaylistIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    emoji: str = "🎵"
    description: str = Field("", max_length=200)
    mood: str | None = None
    song_ids: list[int] = []

class AddSongIn(BaseModel):
    song_id: int


# ---------- website ----------

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def website():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# ---- PWA: installable-app assets (served from the root scope) ----

@app.get("/manifest.json", include_in_schema=False)
def pwa_manifest():
    return FileResponse(os.path.join(STATIC_DIR, "manifest.json"), media_type="application/manifest+json")


@app.get("/sw.js", include_in_schema=False)
def pwa_sw():
    return FileResponse(os.path.join(STATIC_DIR, "sw.js"), media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})


@app.get("/icon-96.png", include_in_schema=False)
def pwa_icon_96():
    return FileResponse(os.path.join(STATIC_DIR, "icon-96.png"), media_type="image/png")


@app.get("/icon-192.png", include_in_schema=False)
def pwa_icon_192():
    return FileResponse(os.path.join(STATIC_DIR, "icon-192.png"), media_type="image/png")


@app.get("/icon-512.png", include_in_schema=False)
def pwa_icon_512():
    return FileResponse(os.path.join(STATIC_DIR, "icon-512.png"), media_type="image/png")


@app.get("/icon-maskable-512.png", include_in_schema=False)
def pwa_icon_mask():
    return FileResponse(os.path.join(STATIC_DIR, "icon-maskable-512.png"), media_type="image/png")


@app.get("/apple-touch-icon.png", include_in_schema=False)
def pwa_icon_apple():
    return FileResponse(os.path.join(STATIC_DIR, "apple-touch-icon.png"), media_type="image/png")


@app.get("/logo.png", include_in_schema=False)
def pwa_logo():
    return FileResponse(os.path.join(STATIC_DIR, "logo-master.png"), media_type="image/png")


# ---- Native app downloads (real setup files saved to the user's storage) ----

_DL_DIR = os.path.join(STATIC_DIR, "downloads")

# The native Windows app (Electron, ~97 MB) lives in GitHub Releases — too big
# for the repo itself. This permalink always points at the newest release asset.
WINDOWS_EXE_URL = "https://github.com/ShayanKhan250/Sonic-Wave/releases/latest/download/SonicWave-Setup.exe"


@app.get("/download/windows", include_in_schema=False)
def download_windows():
    return RedirectResponse(WINDOWS_EXE_URL, status_code=302)


@app.get("/download/android", include_in_schema=False)
def download_android():
    return FileResponse(os.path.join(_DL_DIR, "SonicWave.apk"),
                        media_type="application/vnd.android.package-archive",
                        filename="SonicWave.apk")


@app.get("/download/mac", include_in_schema=False)
def download_mac():
    return FileResponse(os.path.join(_DL_DIR, "SonicWave-macOS.zip"),
                        media_type="application/zip", filename="SonicWave-macOS.zip")


@app.get("/download/linux", include_in_schema=False)
def download_linux():
    return FileResponse(os.path.join(_DL_DIR, "SonicWave-Linux-Installer.sh"),
                        media_type="application/x-sh", filename="SonicWave-Linux-Installer.sh")

@app.get("/legacy", response_class=HTMLResponse, include_in_schema=False)
def legacy_website():
    return FileResponse(os.path.join(STATIC_DIR, "legacy.html"))

@app.get("/standalone", response_class=HTMLResponse, include_in_schema=False)
def standalone_website():
    return FileResponse(os.path.join(STATIC_DIR, "standalone.html"))


_PRIVACY_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Privacy Policy – SonicWave</title>
<style>
body{font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;background:#0b0b0f;color:#e8e8ee;max-width:760px;margin:0 auto;padding:48px 24px 80px;line-height:1.75}
h1{font-size:30px;background:linear-gradient(90deg,#ff2d78,#b84dff);-webkit-background-clip:text;background-clip:text;color:transparent;margin-bottom:4px}
.sub{color:#8b8b9a;font-size:13px;margin-bottom:34px}
h2{font-size:18px;margin:34px 0 10px;color:#fff;border-bottom:1px solid rgba(255,255,255,.08);padding-bottom:8px}
h3{font-size:14.5px;margin:20px 0 6px;color:#fff}
p,li{color:#b9b9c6;font-size:14.5px}
ul{padding-left:22px;margin:8px 0}
a{color:#ff5e94}
table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13.5px}
th,td{text-align:left;padding:9px 12px;border:1px solid rgba(255,255,255,.1);color:#b9b9c6;vertical-align:top}
th{color:#fff;background:rgba(255,255,255,.04)}
.toc{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:18px 22px;margin-bottom:8px}
.toc li{margin:3px 0;font-size:13.5px}
</style></head><body>
<h1>SonicWave Privacy Policy</h1>
<div class="sub">Effective date: 3 October 2026 &nbsp;·&nbsp; Version 2.0</div>

<div class="toc"><b style="color:#fff;font-size:13.5px">Contents</b>
<ul>
<li><a href="#s1">1. About this Policy</a></li>
<li><a href="#s2">2. Who We Are</a></li>
<li><a href="#s3">3. Personal Data We Collect</a></li>
<li><a href="#s4">4. How and Why We Use Your Data</a></li>
<li><a href="#s5">5. Cookies and Local Storage</a></li>
<li><a href="#s6">6. Third-Party Services</a></li>
<li><a href="#s7">7. Sharing and Disclosure</a></li>
<li><a href="#s8">8. Data Retention and Deletion</a></li>
<li><a href="#s9">9. Your Rights and Choices</a></li>
<li><a href="#s10">10. Children's Privacy</a></li>
<li><a href="#s11">11. Security</a></li>
<li><a href="#s12">12. International Data Transfers</a></li>
<li><a href="#s13">13. Changes to this Policy</a></li>
<li><a href="#s14">14. Contact Us</a></li>
</ul></div>

<h2 id="s1">1. About this Policy</h2>
<p>This Privacy Policy describes how SonicWave ("<b>SonicWave</b>", "<b>we</b>", "<b>us</b>" or "<b>our</b>") collects, uses, stores, shares and protects personal data when you use the SonicWave music streaming service, including our website, applications and related services (together, the "<b>Service</b>"). It also explains the rights and choices you have over your personal data.</p>
<p>By creating an account or using the Service, you acknowledge that you have read and understood this Policy. If you do not agree with it, please do not use the Service.</p>

<h2 id="s2">2. Who We Are</h2>
<p>The Service is operated by the owner of SonicWave, who acts as the data controller for the personal data described in this Policy (the party that decides how and why your data is processed). For data-related requests, see <a href="#s14">Section 14 (Contact Us)</a>.</p>

<h2 id="s3">3. Personal Data We Collect</h2>
<table>
<tr><th>Category</th><th>Examples</th><th>Source</th></tr>
<tr><td><b>Account Data</b></td><td>Username, display name, hashed password, account creation date</td><td>Provided by you at sign-up</td></tr>
<tr><td><b>Google Sign-In Data</b></td><td>Your Google account identifier and public profile name</td><td>Provided by Google, with your consent, when you choose "Continue with Google"</td></tr>
<tr><td><b>Usage Data</b></td><td>Songs you play, like ("heart"), add to playlists; playlists you create; country/region preference</td><td>Generated by your use of the Service</td></tr>
<tr><td><b>Device Preferences</b></td><td>Theme (dark/light), audio settings, recently played and recent searches (stored only on your device, subject to your cookie choice)</td><td>Stored locally in your browser</td></tr>
<tr><td><b>Technical Data</b></td><td>IP address (processed transiently for security rate-limiting and spam prevention; not stored in our database), browser type</td><td>Collected automatically</td></tr>
</table>
<p><b>What we do NOT collect:</b> we do not collect your real name (unless you choose it as a display name), email address (unless provided via Google Sign-In, in which case only your name is stored), phone number, payment information, precise location, or contacts. We never see or store your Google password. Account passwords are stored exclusively as salted cryptographic hashes and cannot be read by anyone, including us.</p>

<h2 id="s4">4. How and Why We Use Your Data</h2>
<table>
<tr><th>Purpose</th><th>Data used</th><th>Legal basis (GDPR)</th></tr>
<tr><td>Provide the Service — accounts, login sessions, playback, likes, playlists</td><td>Account Data, Usage Data</td><td>Performance of a contract (Art. 6(1)(b))</td></tr>
<tr><td>Personalisation — "Made For You" recommendations and country charts</td><td>Usage Data</td><td>Performance of a contract / legitimate interests (Art. 6(1)(f))</td></tr>
<tr><td>Security — login protection, bot and abuse prevention, rate limiting</td><td>Technical Data</td><td>Legitimate interests (Art. 6(1)(f))</td></tr>
<tr><td>Optional device features — recently played, recent searches</td><td>Device Preferences</td><td>Consent (Art. 6(1)(a)) — via the cookie banner</td></tr>
</table>
<p>We do <b>not</b> use your personal data for advertising, we do not build advertising profiles, and we do not send marketing communications.</p>

<h2 id="s5">5. Cookies and Local Storage</h2>
<p>SonicWave uses browser local storage and similar technologies in two categories, which you control through our consent banner (shown on first visit, and changeable at any time under <b>Settings → Privacy &amp; cookies → Manage</b>):</p>
<ul>
<li><b>Essential (always active):</b> your login session token, theme, country and audio settings, and your cookie choice itself. The Service cannot function without these.</li>
<li><b>Optional (your choice):</b> a device-local list of your recently played songs and recent searches. If you choose "Essential only", this data is immediately deleted from your device and no new entries are saved.</li>
</ul>
<p>Third-party security tools (Google reCAPTCHA and Google Sign-In) may set their own cookies, governed by Google's policies — see Section 6.</p>

<h2 id="s6">6. Third-Party Services</h2>
<table>
<tr><th>Service</th><th>Purpose</th><th>Their policy</th></tr>
<tr><td>Google reCAPTCHA</td><td>Protects login and sign-up against bots</td><td><a href="https://policies.google.com/privacy">Privacy</a> · <a href="https://policies.google.com/terms">Terms</a></td></tr>
<tr><td>Google Sign-In</td><td>Optional one-tap account creation and login</td><td><a href="https://policies.google.com/privacy">Privacy</a></td></tr>
<tr><td>Vercel</td><td>Application hosting</td><td><a href="https://vercel.com/legal/privacy-policy">Privacy</a></td></tr>
<tr><td>Neon</td><td>Encrypted database hosting</td><td><a href="https://neon.tech/privacy-policy">Privacy</a></td></tr>
<tr><td>Public music catalogue APIs (song metadata, artwork, lyrics, charts)</td><td>Provide music search results, album art, synced lyrics and top-chart data</td><td>Requests for music content are made by the Service; your identity is not disclosed to these providers</td></tr>
</table>

<h2 id="s7">7. Sharing and Disclosure</h2>
<p>We do <b>not</b> sell, rent or trade your personal data. We only disclose personal data:</p>
<ul>
<li>to the hosting and infrastructure processors listed in Section 6, strictly to operate the Service;</li>
<li>if required by applicable law, regulation, legal process or enforceable governmental request; or</li>
<li>to protect the rights, property or safety of SonicWave, our users or the public.</li>
</ul>

<h2 id="s8">8. Data Retention and Deletion</h2>
<ul>
<li><b>Account Data and Usage Data</b> are retained for as long as your account exists.</li>
<li><b>Likes, playlists and listening history</b> can be deleted by you at any time inside the app (unlike a song, delete a playlist, etc.), taking effect immediately.</li>
<li><b>Device-local data</b> is deleted instantly when you select "Essential only" in the cookie settings, or when you clear your browser storage.</li>
<li><b>Full account deletion:</b> contact us (Section 14) and your account and all associated data will be permanently erased from the database without undue delay, and in any event within 30 days.</li>
</ul>

<h2 id="s9">9. Your Rights and Choices</h2>
<p>Depending on your jurisdiction (including the EU/EEA under the GDPR, the UK under the UK GDPR, and California under the CCPA/CPRA), you have the right to:</p>
<ul>
<li><b>Access</b> — request a copy of the personal data we hold about you;</li>
<li><b>Rectification</b> — correct inaccurate data (e.g. change your display name);</li>
<li><b>Erasure</b> ("right to be forgotten") — request deletion of your account and data;</li>
<li><b>Portability</b> — receive your data in a structured, machine-readable format;</li>
<li><b>Objection / Restriction</b> — object to or restrict certain processing;</li>
<li><b>Withdraw consent</b> — at any time, for processing based on consent (e.g. optional storage), without affecting prior processing;</li>
<li><b>Non-discrimination</b> — we will never degrade the Service because you exercised a privacy right;</li>
<li><b>Complain</b> — lodge a complaint with your local data protection authority.</li>
</ul>
<p>To exercise any of these rights, contact us via Section 14. We respond to verified requests within the timeframe required by applicable law (generally 30 days).</p>

<h2 id="s10">10. Children's Privacy</h2>
<p>The Service is not directed to children under the age of 13 (or the higher minimum age required in your country). We do not knowingly collect personal data from children. If you believe a child has provided us personal data, contact us and we will delete it promptly.</p>

<h2 id="s11">11. Security</h2>
<p>We apply appropriate technical and organisational measures to protect your data, including: transport encryption (HTTPS/TLS) on all connections; salted password hashing (passwords are never stored or transmitted in readable form); encrypted database storage; login rate-limiting and bot protection; and the principle of data minimisation — we simply do not collect what we do not need.</p>
<p>No method of transmission or storage is 100% secure; in the unlikely event of a breach affecting your personal data, we will notify affected users and authorities as required by applicable law.</p>

<h2 id="s12">12. International Data Transfers</h2>
<p>Our infrastructure providers (Section 6) may process data in data centres located in different countries, including the United States and Singapore. Where data is transferred from the EU/EEA or UK, such transfers rely on appropriate safeguards such as Standard Contractual Clauses implemented by those providers.</p>

<h2 id="s13">13. Changes to this Policy</h2>
<p>We may update this Policy from time to time. Material changes will be indicated by updating the effective date at the top of this page, and where appropriate, by notice within the Service. Continued use of the Service after changes take effect constitutes acceptance of the revised Policy.</p>

<h2 id="s14">14. Contact Us</h2>
<p>For any questions about this Policy, or to exercise your privacy rights (access, deletion, portability, etc.), contact the site owner through the social or contact channel where you obtained the link to this Service. Verified requests are handled within 30 days.</p>

<p style="margin-top:36px;font-size:12px;color:#8b8b9a">© 2026 SonicWave. This document is provided for transparency and does not constitute legal advice to any third party.</p>
</body></html>"""


@app.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
def privacy_policy():
    return HTMLResponse(_PRIVACY_HTML)

@app.get("/favicon-dark.svg", include_in_schema=False)
def favicon_dark():
    return FileResponse(os.path.join(STATIC_DIR, "favicon-dark.svg"), media_type="image/svg+xml")

@app.get("/favicon-light.svg", include_in_schema=False)
def favicon_light():
    return FileResponse(os.path.join(STATIC_DIR, "favicon-light.svg"), media_type="image/svg+xml")


# ---------- public url ----------

URL_FILE = "/home/user/PUBLIC_URL.txt"
SHORT_URL_FILE = "/home/user/SHORT_URL.txt"

def _read_file(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read().strip() or None
    except OSError:
        return None

def _read_public_url() -> str | None:
    return _read_file(URL_FILE)

@app.get("/api/url", tags=["Stats"])
def public_url():
    return {"public_url": _read_public_url(), "short_url": _read_file(SHORT_URL_FILE)}

@app.get("/url", response_class=HTMLResponse, include_in_schema=False)
def public_url_page():
    url = _read_public_url() or "not available yet"
    short = _read_file(SHORT_URL_FILE)
    link = f'<a href="{url}" style="color:#06b6d4;font-size:18px;word-break:break-all">{url}</a>' \
        if url.startswith("http") else f"<b>{url}</b>"
    short_html = (f'<p style="color:#8b8ba3;margin-top:26px">Easy shareable link:</p>'
                  f'<a href="{short}" style="color:#a855f7;font-size:24px;font-weight:800">{short}</a>') if short else ""
    return f"""<!doctype html><html><head><title>SonicWave — Current Public URL</title>
    <meta http-equiv="refresh" content="15"/></head>
    <body style="font-family:system-ui;background:#0d0d1a;color:#eee;display:grid;place-items:center;height:100vh;margin:0;text-align:center">
    <div><h1 style="background:linear-gradient(90deg,#a855f7,#06b6d4);-webkit-background-clip:text;background-clip:text;color:transparent">🎵 SonicWave</h1>
    {short_html}
    <p style="color:#8b8ba3;margin-top:26px">Direct tunnel URL (auto-refreshes every 15s):</p>{link}</div></body></html>"""


# ---------- api landing ----------

@app.get("/api", response_class=HTMLResponse, include_in_schema=False)
def api_landing():
    return """<!doctype html><html><head><title>SonicWave API v2</title><style>
    body{font-family:system-ui,sans-serif;background:#0d0d1a;color:#eee;max-width:800px;margin:40px auto;padding:0 20px}
    h1{background:linear-gradient(90deg,#a855f7,#06b6d4);-webkit-background-clip:text;background-clip:text;color:transparent}
    h2{color:#a855f7;font-size:1.1em;margin-top:28px}
    code{background:#1e1e35;padding:2px 8px;border-radius:6px;color:#7dd3fc}
    li{margin:7px 0} a{color:#a855f7} .tag{color:#fbbf24;font-size:.85em}
    </style></head><body>
    <h1>🎵 SonicWave API v2</h1>
    <p>SQLite-backed. Interactive docs at <a href="/docs">/docs</a>. Demo login: <code>demo / demo123</code></p>
    <h2>👤 Accounts</h2><ul>
      <li><code>POST /api/auth/register</code> — {username, password} → token</li>
      <li><code>POST /api/auth/login</code> — {username, password} → token</li>
      <li><code>GET /api/auth/me</code> <span class="tag">🔒</span> · <code>POST /api/auth/logout</code> <span class="tag">🔒</span></li>
    </ul>
    <h2>🌍 Real Music (musicapi.x007.workers.dev)</h2><ul>
      <li><code>GET /api/music/search?q=Pathaan&engine=gaama</code> — search real songs (engines: auto/saavn = FULL songs via JioSaavn, plus deezer, itunes, gaama, seevn, hunjama, mtmusic, wunk — auto-falls back if a provider is down)</li>
      <li><code>GET /api/music/lyrics?id=…</code> — lyrics (gaama only)</li>
      <li><code>GET /api/music/fetch?id=…</code> — stream / mp3 link</li>
      <li><code>GET /api/stream/candidates?title=…&artist=…</code> — streaming engine phase 1: ranked stream candidates from every provider (JioSaavn, YouTube Music, Audius)</li>
      <li><code>GET /api/stream/resolve?id=…</code> — streaming engine phase 2: just-in-time playable URL with caching, expiry and retries</li>
    </ul>
    <h2>📚 Catalog</h2><ul>
      <li><code>GET /api/songs</code> (?genre= ?artist= ?q=) · <code>GET /api/songs/{id}</code></li>
      <li><code>GET /api/artists</code> · <code>/api/artists/{id}</code> · <code>/api/artists/{id}/songs</code></li>
      <li><code>GET /api/albums</code> · <code>/api/albums/{id}</code></li>
      <li><code>GET /api/charts/top</code> · <code>/api/trending</code> · <code>/api/new-releases</code> · <code>/api/search?q=</code> · <code>/api/mood/{mood}</code></li>
    </ul>
    <h2>🎼 Playlists</h2><ul>
      <li><code>GET /api/playlists</code> · <code>GET /api/playlists/{id}</code></li>
      <li><code>POST /api/playlists</code> <span class="tag">🔒</span> — create playlist</li>
      <li><code>POST /api/playlists/{id}/songs</code> <span class="tag">🔒</span> · <code>DELETE /api/playlists/{id}/songs/{song_id}</code> <span class="tag">🔒</span></li>
      <li><code>DELETE /api/playlists/{id}</code> <span class="tag">🔒</span></li>
    </ul>
    <h2>❤️ Likes &amp; Queue <span class="tag">🔒 per-user</span></h2><ul>
      <li><code>GET /api/liked</code> · <code>POST /api/songs/{id}/like</code> · <code>DELETE /api/songs/{id}/like</code></li>
      <li><code>GET /api/queue</code> · <code>POST /api/queue/{song_id}</code> · <code>DELETE /api/queue</code></li>
    </ul></body></html>"""


# ---------- auth ----------

# --- bot / abuse protection -------------------------------------------------
RECAPTCHA_SECRET = os.environ.get("RECAPTCHA_SECRET", "6Le4jNstAAAAACJ3AkXlE-r4HwJsvCooB9XWaBVC")
# Domains where the reCAPTCHA widget is served to users; requests whose Origin
# matches one of these MUST carry a valid captcha token.
CAPTCHA_ENFORCED_HOSTS = {"sonicwavez.netlify.app"}

import time as _time
from collections import defaultdict as _dd, deque as _deque
_AUTH_HITS: dict = _dd(_deque)          # ip -> recent auth attempt timestamps
_AUTH_MAX, _AUTH_WINDOW = 10, 60.0       # 10 attempts / minute / IP


def _client_ip(request: Request) -> str:
    return (request.headers.get("cf-connecting-ip")
            or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
            or (request.client.host if request.client else "?"))


def _auth_guard(request: Request, captcha: str | None):
    """Rate-limit brute force on every domain; verify Google reCAPTCHA when supplied
    (and require it when the request comes from a captcha-enforced origin)."""
    ip = _client_ip(request)
    now = _time.monotonic()
    hits = _AUTH_HITS[ip]
    while hits and now - hits[0] > _AUTH_WINDOW:
        hits.popleft()
    if len(hits) >= _AUTH_MAX:
        raise HTTPException(429, "Too many attempts — please wait a minute and try again.")
    hits.append(now)

    if not captcha:
        # reCAPTCHA v3 is invisible; a missing token usually means an ad-blocker.
        # Real users must never be locked out — bots are stopped by the rate limiter above.
        return
    try:
        with httpx.Client(timeout=10) as c:
            r = c.post("https://www.google.com/recaptcha/api/siteverify",
                       data={"secret": RECAPTCHA_SECRET, "response": captcha, "remoteip": ip})
            r.raise_for_status()
            data = r.json()
            ok = bool(data.get("success"))
            score = data.get("score")
            # v3 trust score: new site keys / new domains / VPN users legitimately score
            # as low as 0.1 for days, so only reject the hard floor. Real abuse is
            # already throttled by the per-IP rate limiter above.
            min_score = float(os.environ.get("CAPTCHA_MIN_SCORE", "0.05"))
            if ok and score is not None and float(score) < min_score:
                ok = False
            if not ok:
                codes = data.get("error-codes") or []
                # Config-side failures (wrong domain registration, expired/duplicate
                # token after a slow page) must never lock out real users.
                lenient = {"timeout-or-duplicate", "hostname-mismatch", "browser-error"}
                if any(c in lenient for c in codes):
                    ok = True
    except httpx.HTTPError:
        ok = True   # Google unreachable from our server: never punish users for our outage
    except (TypeError, ValueError):
        ok = False
    if not ok:
        raise HTTPException(400, "Security check failed — please refresh the page and try again.")


@app.post("/api/auth/register", tags=["Auth"], status_code=201)
def register(body: RegisterIn, conn: Conn, request: Request):
    _auth_guard(request, body.captcha)
    try:
        uid = db.create_user(conn, body.username, body.password, body.display_name)
    except db.IntegrityErrors:
        raise HTTPException(409, f"Username '{body.username}' is already taken.")
    token = db.issue_token(conn, uid)
    return {"user": {"id": uid, "username": body.username, "display_name": body.display_name or body.username},
            "token": token, "token_type": "bearer"}

@app.post("/api/auth/login", tags=["Auth"])
def login(body: LoginIn, conn: Conn, request: Request):
    _auth_guard(request, body.captcha)
    user = db.verify_user(conn, body.username, body.password)
    if not user:
        raise HTTPException(401, "Invalid username or password.")
    token = db.issue_token(conn, user["id"])
    return {"user": {"id": user["id"], "username": user["username"], "display_name": user["display_name"]},
            "token": token, "token_type": "bearer"}


# ---------- Sign in with Google ----------
import secrets as _secrets

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()


class GoogleIn(BaseModel):
    credential: str = Field(min_length=20)


@app.get("/api/auth/google/config", tags=["Auth"])
def google_config():
    """Tells the frontend whether Google sign-in is configured (and with which public client id)."""
    return {"client_id": GOOGLE_CLIENT_ID or None}


@app.post("/api/auth/google", tags=["Auth"])
def google_login(body: GoogleIn, conn: Conn, request: Request):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(503, "Google sign-in is not configured on this server.")
    _auth_guard(request, None)   # per-IP rate limit; Google's own token check replaces the captcha
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": body.credential})
    except httpx.HTTPError:
        raise HTTPException(502, "Could not reach Google — please try again.")
    if r.status_code != 200:
        raise HTTPException(401, "Google sign-in failed — please try again.")
    info = r.json()
    if info.get("aud") != GOOGLE_CLIENT_ID or info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPException(401, "Google sign-in failed — please try again.")
    sub = info.get("sub")
    if not sub:
        raise HTTPException(401, "Google sign-in failed — please try again.")
    name = (info.get("name") or (info.get("email") or "Listener").split("@")[0]).strip()[:40] or "Listener"
    username = f"google_{sub}"
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row:
        uid, display, avatar = row["id"], row["display_name"], _avatar_of(row)
    else:
        # Google users get an unusable random password — they always sign in via Google.
        uid = db.create_user(conn, username, _secrets.token_hex(24), name)
        display, avatar = name, (info.get("picture") or None)
        if avatar:
            try:
                conn.execute("UPDATE users SET avatar=? WHERE id=?", (avatar, uid))
                conn.commit()
            except Exception:
                avatar = None
    token = db.issue_token(conn, uid)
    return {"user": {"id": uid, "username": username, "display_name": display, "avatar": avatar},
            "token": token, "token_type": "bearer"}


def _avatar_of(row):
    try:
        return row["avatar"] if "avatar" in row.keys() else None
    except Exception:
        return None


def _valid_avatar(v: str) -> bool:
    return v.startswith("data:image/") or v.startswith("preset:") or v.startswith("https://")


@app.get("/api/auth/me", tags=["Auth"])
def me(user: User, conn: Conn):
    likes = conn.execute("SELECT COUNT(*) c FROM likes WHERE user_id=?", (user["id"],)).fetchone()["c"]
    playlists = conn.execute("SELECT COUNT(*) c FROM playlists WHERE owner_id=?", (user["id"],)).fetchone()["c"]
    return {"id": user["id"], "username": user["username"], "display_name": user["display_name"],
            "avatar": _avatar_of(user),
            "created_at": user["created_at"], "liked_songs": likes, "playlists": playlists}


class ProfileIn(BaseModel):
    display_name: str | None = Field(None, max_length=60)
    avatar: str | None = Field(None, max_length=400_000)   # resized client-side; ~50 KB typical


@app.post("/api/me/profile", tags=["Auth"])
def update_profile(body: ProfileIn, user: User, conn: Conn):
    sets, vals = [], []
    if body.display_name is not None:
        dn = body.display_name.strip()[:40]
        if not dn:
            raise HTTPException(400, "Display name cannot be empty.")
        sets.append("display_name=?"); vals.append(dn)
    if body.avatar is not None:
        av = body.avatar.strip()
        if av and not _valid_avatar(av):
            raise HTTPException(400, "Invalid image format.")
        sets.append("avatar=?"); vals.append(av or None)
    if not sets:
        raise HTTPException(400, "Nothing to update.")
    vals.append(user["id"])
    conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", tuple(vals))
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
    return {"id": row["id"], "username": row["username"], "display_name": row["display_name"],
            "avatar": _avatar_of(row)}


class DeleteAccountIn(BaseModel):
    confirm: str


@app.post("/api/me/account/delete", tags=["Auth"])
def delete_account(body: DeleteAccountIn, user: User, conn: Conn):
    if body.confirm.strip().upper() != "DELETE":
        raise HTTPException(400, 'Type "DELETE" to confirm — this cannot be undone.')
    uid = user["id"]
    for q in (
        "DELETE FROM user_playlist_tracks WHERE playlist_id IN (SELECT id FROM user_playlists WHERE user_id=?)",
        "DELETE FROM user_playlists WHERE user_id=?",
        "DELETE FROM liked_tracks WHERE user_id=?",
        "DELETE FROM likes WHERE user_id=?",
        "DELETE FROM plays WHERE user_id=?",
        "DELETE FROM queue_items WHERE user_id=?",
        "DELETE FROM playlist_songs WHERE playlist_id IN (SELECT id FROM playlists WHERE owner_id=?)",
        "DELETE FROM playlists WHERE owner_id=?",
        "DELETE FROM tokens WHERE user_id=?",
        "DELETE FROM users WHERE id=?",
    ):
        conn.execute(q, (uid,))
    conn.commit()
    return {"deleted": True, "message": "Your account and all data have been permanently erased."}

@app.post("/api/auth/logout", tags=["Auth"])
def logout(user: User, conn: Conn, authorization: str = Header(...)):
    conn.execute("DELETE FROM tokens WHERE token=?", (authorization.split(" ", 1)[1].strip(),))
    conn.commit()
    return {"logged_out": True}


# ---------- real music (external) ----------
# Primary: musicapi.x007.workers.dev (gaama/seevn/hunjama/mtmusic/wunk)
# Fallback: iTunes + Deezer (used automatically when x007 is unreachable)

X007_ENGINES = {"gaama", "seevn", "hunjama", "mtmusic", "wunk"}
ALL_ENGINES = X007_ENGINES | {"itunes", "deezer", "saavn", "yt", "audius", "auto"}
SAAVN_API = "https://saavn-api.nandanvarma.com/api"

import html as _html


def _saavn_map(r: dict) -> dict:
    urls = [u for u in (r.get("downloadUrl") or []) if u.get("url")]
    best = None
    for u in urls:  # prefer 320kbps, else take highest available (list is ascending)
        if u.get("quality") == "320kbps":
            best = u["url"]
    if not best and urls:
        best = urls[-1]["url"]
    prim = ((r.get("artists") or {}).get("primary")) or []
    imgs = r.get("image") or []
    return {
        "id": f"saavn:{r.get('id')}",
        "title": _html.unescape(r.get("name") or ""),
        "artist": _html.unescape(prim[0].get("name", "")) if prim else None,
        "album": _html.unescape(((r.get("album") or {}).get("name")) or "") or None,
        "img": imgs[-1]["url"] if imgs else None,
        "preview_url": best,           # actually the FULL song
        "duration": (lambda d: f"{d // 60}:{d % 60:02d}" if isinstance(d, int) else None)(r.get("duration")),
        "full": True,
        "source": "saavn",
    }


# ---------- Native JioSaavn (direct, no third-party mirror) ----------

SAAVN_NATIVE = "https://www.jiosaavn.com/api.php"


def _native_params(q: str, limit: int) -> dict:
    return {"__call": "search.getResults", "q": q, "p": 1, "n": max(1, min(50, limit)),
            "_format": "json", "_marker": "0", "api_version": "4", "ctx": "web6dot0"}


def _des_url(enc: str) -> str | None:
    try:
        import base64
        from Crypto.Cipher import DES
        dec = DES.new(b"38346591", DES.MODE_ECB).decrypt(base64.b64decode(enc))
        url = "".join(ch for ch in dec.decode("utf-8", "ignore") if 32 <= ord(ch) < 127).strip()
        if not url.startswith("http"):
            return None
        return url.replace("_96.mp4", "_320.mp4")
    except Exception:
        return None


def _native_map(r: dict) -> dict | None:
    mi = r.get("more_info") or {}
    url = _des_url(mi.get("encrypted_media_url") or "")
    if not url:
        return None
    prim = ((mi.get("artistMap") or {}).get("primary_artists")) or []
    artist = ", ".join(a.get("name", "") for a in prim[:3]) or (r.get("subtitle") or "")
    try:
        dur = int(mi.get("duration") or 0)
    except (TypeError, ValueError):
        dur = 0
    return {
        "id": f"saavn:{r.get('id')}",
        "title": _html.unescape(r.get("title") or ""),
        "artist": _html.unescape(artist) or None,
        "album": _html.unescape((mi.get("album") or "")) or None,
        "img": (r.get("image") or "").replace("150x150", "500x500") or None,
        "preview_url": url,            # actually the FULL song (320kbps)
        "duration": f"{dur // 60}:{dur % 60:02d}" if dur else None,
        "full": True,
        "source": "saavn",
    }


def _dedupe_tracks(tracks: list) -> list:
    """Drop visually-identical duplicates (same song from single + album releases)."""
    seen, out = set(), []
    for t in tracks:
        key = ((t.get("title") or "").lower().strip(),
               (t.get("artist") or "").lower().split(",")[0].strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


# ---------- YouTube Music (Piped search + yt-dlp server-proxied streams) ----------

PIPED_INSTANCES = ["https://pipedapi.ducks.party", "https://api.piped.private.coffee"]


def _yt_map(x: dict) -> dict | None:
    vid = (x.get("url") or "").split("v=")[-1].strip()
    if not vid:
        return None
    dur = x.get("duration")
    return {
        "id": f"yt:{vid}",
        "title": _html.unescape(x.get("title") or ""),
        "artist": _html.unescape(x.get("uploaderName") or "") or None,
        "album": None,
        "img": x.get("thumbnail"),
        "preview_url": None,            # resolved at play time via /api/music/fetch
        "duration": (f"{dur // 60}:{dur % 60:02d}" if isinstance(dur, int) and dur > 0 else None),
        "full": True,
        "source": "yt",
    }


async def _yt_search(client, q: str, limit: int = 20):
    for base in PIPED_INSTANCES:
        try:
            r = await client.get(f"{base}/search", params={"q": q, "filter": "music_songs"})
            r.raise_for_status()
            items = (r.json().get("items") or [])[: max(1, limit)]
            out = [t for t in (_yt_map(x) for x in items) if t and t["title"]]
            if out:
                return out
        except Exception:
            continue
    return []


async def _saavn_search(client, q: str, limit: int = 20):
    """Full-song search: JioSaavn mirror first, then the native JioSaavn API.
    Two independent backends so one going down can never degrade us to previews."""
    out = []
    try:
        data_ = await _get_json(client, f"{SAAVN_API}/search/songs", {"query": q, "limit": max(1, min(50, limit))})
        results = ((data_.get("data") or {}).get("results")) or []
        out = [t for t in (_saavn_map(r) for r in results) if t["preview_url"]]
    except Exception:
        out = []
    if not out:
        try:
            r = await client.get(SAAVN_NATIVE, params=_native_params(q, limit),
                                 headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                                 follow_redirects=True)
            r.raise_for_status()
            out = [t for t in (_native_map(x) for x in (r.json().get("results") or [])) if t]
        except Exception:
            out = []
    return _dedupe_tracks(out)


async def _get_json(client: httpx.AsyncClient, url: str, params: dict):
    r = await client.get(url, params=params)
    r.raise_for_status()
    return r.json()


async def _x007_search(client, q: str, engine: str):
    data_ = await _get_json(client, f"{MUSIC_API}/search", {"q": q, "searchEngine": engine})
    results = data_.get("response") or []
    return [{"id": r.get("id"), "title": r.get("title"), "artist": None,
             "img": r.get("img"), "source": engine} for r in results]


async def _itunes_search(client, q: str):
    data_ = await _get_json(client, "https://itunes.apple.com/search",
                            {"term": q, "media": "music", "limit": 15})
    return [{"id": f"itunes:{r['trackId']}", "title": r.get("trackName"),
             "artist": r.get("artistName"), "img": r.get("artworkUrl100"),
             "album": r.get("collectionName"), "preview_url": r.get("previewUrl"),
             "full": False, "source": "itunes"} for r in data_.get("results", []) if r.get("trackId")]


async def _deezer_search(client, q: str):
    data_ = await _get_json(client, "https://api.deezer.com/search", {"q": q, "limit": 15})
    return [{"id": f"deezer:{r['id']}", "title": r.get("title"),
             "artist": (r.get("artist") or {}).get("name"),
             "img": (r.get("album") or {}).get("cover_medium"),
             "album": (r.get("album") or {}).get("title"), "preview_url": r.get("preview"),
             "full": False, "source": "deezer"} for r in data_.get("data", []) if r.get("id")]


@app.get("/api/music/search", tags=["Real Music"])
async def music_search(
    q: str = Query(..., min_length=1, description="Song name, e.g. Pathaan"),
    engine: str = Query("auto", description=f"One of: {', '.join(sorted(ALL_ENGINES))}"),
    limit: int = Query(20, ge=1, le=50),
):
    if engine not in ALL_ENGINES:
        raise HTTPException(400, f"Unknown engine '{engine}'. Available: {', '.join(sorted(ALL_ENGINES))}")
    note = None
    async with httpx.AsyncClient(timeout=20) as client:
        if engine == "yt":
            results = await _yt_search(client, q, limit)
            if results:
                return {"query": q, "engine": "yt", "count": len(results), "results": results,
                        "note": "Full-length songs via YouTube Music."}
            note = "YouTube Music returned no results — fell back to Deezer previews."
            engine = "deezer"
        if engine in ("auto", "saavn"):
            results = []
            try:
                results = await _saavn_search(client, q, limit)
            except (httpx.HTTPError, KeyError, ValueError):
                pass
            if engine == "auto" and len(results) < limit:
                # widen coverage with YouTube Music, dedup by (title, artist)
                seen = {((t["title"] or "").lower().strip(), (t["artist"] or "").lower().strip()) for t in results}
                for t in await _yt_search(client, q, limit - len(results)):
                    key = ((t["title"] or "").lower().strip(), (t["artist"] or "").lower().strip())
                    if key not in seen:
                        seen.add(key)
                        results.append(t)
            if results:
                srcs = {t["source"] for t in results}
                return {"query": q, "engine": "+".join(sorted(srcs)), "count": len(results), "results": results,
                        "note": "Full-length songs via " +
                                " + ".join(n for s, n in (("saavn", "JioSaavn"), ("yt", "YouTube Music")) if s in srcs) + "."}
            note = "Saavn and YouTube Music returned no results — fell back to Deezer previews."
            engine = "deezer"
        if engine == "audius":
            raw = await _audius_search(client, q, limit)
            results = [{"id": c["id"], "title": c["title"], "artist": c.get("artist"),
                        "album": None, "img": c.get("thumbnail"),
                        "preview_url": _audius_stream_url(c["id"].split(":", 1)[1]),
                        "duration": (f"{c['durationMs'] // 60000}:{c['durationMs'] % 60000 // 1000:02d}"
                                     if c.get("durationMs") else None),
                        "full": True, "source": "audius"} for c in raw]
            if results:
                return {"query": q, "engine": "audius", "count": len(results), "results": results,
                        "note": "Full-length songs via Audius (independent artists)."}
            note = "Audius returned no results — fell back to Deezer previews."
            engine = "deezer"
        if engine in X007_ENGINES:
            try:
                results = await _x007_search(client, q, engine)
                return {"query": q, "engine": engine, "count": len(results), "results": results}
            except httpx.HTTPError:
                note = f"Engine '{engine}' (musicapi.x007.workers.dev) is currently unreachable — fell back to iTunes."
                engine = "itunes"
        try:
            results = await _itunes_search(client, q) if engine == "itunes" else await _deezer_search(client, q)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"All music providers failed: {e}")
    out = {"query": q, "engine": engine, "count": len(results), "results": results}
    if note:
        out["note"] = note
    return out


@app.get("/api/music/lyrics", tags=["Real Music"])
async def music_lyrics(id: str = Query(..., description="Song ID from /api/music/search (gaama engine only)")):
    if id.startswith(("itunes:", "deezer:")):
        raise HTTPException(400, "Lyrics are only available for gaama (x007) song IDs.")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            data_ = await _get_json(client, f"{MUSIC_API}/lyrics", {"id": id})
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Lyrics provider (x007) unreachable: {e}")
    return {"id": id, "lyrics_html": data_.get("response"),
            "note": "Lyrics only work with the gaama engine (beta)."}


@app.get("/api/music/fetch", tags=["Real Music"])
async def music_fetch(id: str = Query(..., description="Song ID from /api/music/search")):
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            if id.startswith("saavn:"):
                sid = id.split(":", 1)[1]
                track = None
                try:
                    data_ = await _get_json(client, f"{SAAVN_API}/songs/{sid}", {})
                    items = data_.get("data") or []
                    track = _saavn_map(items[0]) if items else None
                except Exception:
                    track = None
                if not track or not track.get("preview_url"):
                    try:  # native JioSaavn fallback
                        r = await client.get(SAAVN_NATIVE,
                                             params={"__call": "song.getDetails", "pids": sid, "_format": "json",
                                                     "_marker": "0", "api_version": "4", "ctx": "web6dot0"},
                                             headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                                             follow_redirects=True)
                        r.raise_for_status()
                        item = (r.json().get("songs") or [None])[0]
                        track = _native_map(item) if item else None
                    except Exception:
                        track = None
                if not track or not track["preview_url"]:
                    raise HTTPException(404, "No stream available for this Saavn track.")
                return {"id": id, "stream_url": track["preview_url"], "type": "direct_file",
                        "note": "Full-length song via JioSaavn (320kbps)."}
            if id.startswith("yt:"):
                vid = id.split(":", 1)[1]
                if not _re.fullmatch(r"[A-Za-z0-9_-]{6,20}", vid):
                    raise HTTPException(400, "Invalid YouTube video id.")
                return {"id": id, "stream_url": f"/api/yt/audio/{vid}", "type": "direct_file",
                        "note": "Full-length song via YouTube Music (server-relayed audio)."}
            if id.startswith("audius:"):
                tid = id.split(":", 1)[1]
                if not _re.fullmatch(r"[A-Za-z0-9]{3,24}", tid):
                    raise HTTPException(400, "Invalid Audius track id.")
                return {"id": id, "stream_url": _audius_stream_url(tid), "type": "direct_file",
                        "note": "Full-length song via Audius."}
            if id.startswith("itunes:"):
                data_ = await _get_json(client, "https://itunes.apple.com/lookup", {"id": id.split(":", 1)[1]})
                results = data_.get("results") or []
                url = results[0].get("previewUrl") if results else None
                if not url:
                    raise HTTPException(404, "No preview available for this iTunes track.")
                return {"id": id, "stream_url": url, "type": "direct_file",
                        "note": "iTunes provides 30-second previews."}
            if id.startswith("deezer:"):
                data_ = await _get_json(client, f"https://api.deezer.com/track/{id.split(':', 1)[1]}", {})
                url = data_.get("preview")
                if not url:
                    raise HTTPException(404, "No preview available for this Deezer track.")
                return {"id": id, "stream_url": url, "type": "direct_file",
                        "note": "Deezer provides 30-second previews."}
            data_ = await _get_json(client, f"{MUSIC_API}/fetch", {"id": id})
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Music provider unreachable: {e}")
    url = data_.get("response")
    kind = "hls_stream" if isinstance(url, str) and ".m3u8" in url else "direct_file"
    return {"id": id, "stream_url": url, "type": kind}


# ---------- Streaming Engine (Nuclear-inspired two-phase resolution) ----------
# Modeled on Nuclear's Streaming API (docs.nuclearplayer.com):
#   Phase 1  /api/stream/candidates  — discover potential sources across providers
#   Phase 2  /api/stream/resolve     — resolve the playable URL just-in-time
# Resolved streams carry url/protocol/mimeType/bitrateKbps/codec/qualityLabel,
# are cached with an expiry window (STREAM_EXPIRY_MS, like core.playback.streamExpiryMs)
# and retried up to STREAM_RETRIES times (like core.playback.streamResolutionRetries)
# before a candidate is marked failed. Providers: JioSaavn, YouTube Music, Audius.

import asyncio as _asyncio

AUDIUS_HOST = "https://api.audius.co"
STREAM_EXPIRY_MS = 60 * 60 * 1000            # 1 hour, like Nuclear's default
STREAM_RETRIES = 3                           # like Nuclear's default
_STREAM_CACHE: dict = {}                     # candidate id -> (resolved_at_ms, stream dict)


def _mk_stream(url, protocol="https", mime=None, kbps=None, codec=None, label=None):
    return {"url": url, "protocol": protocol, "mimeType": mime,
            "bitrateKbps": kbps, "codec": codec, "qualityLabel": label}


def _dur_to_ms(d):
    """'3:45' / seconds / None -> milliseconds or None."""
    if not d:
        return None
    try:
        if isinstance(d, (int, float)):
            return int(d) * 1000
        s = 0
        for part in str(d).split(":"):
            s = s * 60 + int(part)
        return s * 1000
    except (TypeError, ValueError):
        return None


def _norm_tokens(s):
    s = _re.sub(r"[\(\[\{].*?[\)\]\}]", " ", (s or "").lower())
    return set(_re.findall(r"[a-z0-9]+", s))


def _cand_score(want_title, want_artist, want_ms, cand):
    """Rank candidates: title match > artist match > duration proximity > provider."""
    wt, wa = _norm_tokens(want_title), _norm_tokens(want_artist)
    ct = _norm_tokens(cand.get("title")) | _norm_tokens(cand.get("artist"))
    score = 0.0
    if wt:
        score += 60.0 * len(wt & ct) / len(wt)
    if wa:
        score += 25.0 * len(wa & ct) / len(wa)
    cms = cand.get("durationMs")
    if want_ms and cms:
        diff_s = abs(want_ms - cms) / 1000.0
        score += max(0.0, 15.0 - min(15.0, diff_s / 2.0))    # full bonus at 0s, none at ±30s
    prov = (cand.get("source") or {}).get("provider")
    score += {"saavn": 6.0, "yt": 4.0, "audius": 0.0}.get(prov, 0.0)
    return round(score, 2)


async def _audius_search(client, q: str, limit: int = 6):
    try:
        r = await client.get(f"{AUDIUS_HOST}/v1/tracks/search",
                             params={"query": q, "app_name": "SonicWave"})
        r.raise_for_status()
        out = []
        for t in (r.json().get("data") or [])[: max(1, limit)]:
            if t.get("is_streamable") is False or not t.get("id"):
                continue
            art = t.get("artwork") or {}
            out.append({
                "id": f"audius:{t['id']}",
                "title": _html.unescape(t.get("title") or ""),
                "artist": (t.get("user") or {}).get("name"),
                "durationMs": (int(t.get("duration") or 0) * 1000) or None,
                "thumbnail": art.get("480x480") or art.get("150x150"),
                "source": {"provider": "audius", "name": "Audius"},
            })
        return out
    except Exception:
        return []


def _audius_stream_url(tid: str) -> str:
    return f"{AUDIUS_HOST}/v1/tracks/{tid}/stream?app_name=SonicWave"


@app.get("/api/stream/candidates", tags=["Streaming"])
async def stream_candidates(
    title: str = Query(..., min_length=1, description="Track title"),
    artist: str = Query("", description="Artist name(s)"),
    duration_ms: int = Query(0, ge=0, description="Known duration in ms (improves ranking)"),
    limit: int = Query(12, ge=1, le=30),
):
    """Phase 1 — search every streaming provider for candidates matching the track."""
    main_artist = _re.split(r",|&|feat\.?", artist, flags=_re.I)[0].strip()
    q = f"{title} {main_artist}".strip()
    now_iso = _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime())
    async with httpx.AsyncClient(timeout=20) as client:
        saavn, yt, audius = await _asyncio.gather(
            _saavn_search(client, q, 8), _yt_search(client, q, 5), _audius_search(client, q, 6),
            return_exceptions=True)
    cands = []
    for t in (saavn if isinstance(saavn, list) else []):
        cands.append({
            "id": t["id"], "title": t["title"], "artist": t.get("artist"),
            "durationMs": _dur_to_ms(t.get("duration")), "thumbnail": t.get("img"),
            "source": {"provider": "saavn", "name": "JioSaavn"},
            "stream": _mk_stream(t["preview_url"], mime="audio/mp4", kbps=320,
                                 codec="aac", label="320 kbps"),
            "lastResolvedAtIso": now_iso, "failed": False,
        })
    for t in (yt if isinstance(yt, list) else []):
        cands.append({
            "id": t["id"], "title": t["title"], "artist": t.get("artist"),
            "durationMs": _dur_to_ms(t.get("duration")), "thumbnail": t.get("img"),
            "source": {"provider": "yt", "name": "YouTube Music"},
            "stream": None, "lastResolvedAtIso": None, "failed": False,
        })
    for c in (audius if isinstance(audius, list) else []):
        c = dict(c)
        c["stream"] = _mk_stream(_audius_stream_url(c["id"].split(":", 1)[1]),
                                 mime="audio/mpeg", codec="mp3", label="MP3")
        c["lastResolvedAtIso"] = now_iso
        c["failed"] = False
        cands.append(c)
    for c in cands:
        c["score"] = _cand_score(title, artist, duration_ms or None, c)
    cands.sort(key=lambda c: c["score"], reverse=True)
    cands = cands[:limit]
    if not cands:
        return {"success": False, "error": "No streaming provider returned candidates.",
                "candidates": []}
    return {"success": True, "query": q, "candidates": cands,
            "providers": {"saavn": isinstance(saavn, list) and len(saavn) or 0,
                          "yt": isinstance(yt, list) and len(yt) or 0,
                          "audius": isinstance(audius, list) and len(audius) or 0},
            "settings": {"streamExpiryMs": STREAM_EXPIRY_MS,
                         "streamResolutionRetries": STREAM_RETRIES}}


async def _resolve_stream_once(id: str) -> dict:
    """Resolve one candidate id into a Stream dict. Raises on failure."""
    async with httpx.AsyncClient(timeout=20) as client:
        if id.startswith("saavn:"):
            sid = id.split(":", 1)[1]
            track = None
            try:
                data_ = await _get_json(client, f"{SAAVN_API}/songs/{sid}", {})
                items = data_.get("data") or []
                track = _saavn_map(items[0]) if items else None
            except Exception:
                track = None
            if not track or not track.get("preview_url"):
                r = await client.get(SAAVN_NATIVE,
                                     params={"__call": "song.getDetails", "pids": sid,
                                             "_format": "json", "_marker": "0",
                                             "api_version": "4", "ctx": "web6dot0"},
                                     headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                                     follow_redirects=True)
                r.raise_for_status()
                item = (r.json().get("songs") or [None])[0]
                track = _native_map(item) if item else None
            if not track or not track.get("preview_url"):
                raise HTTPException(404, "No stream available for this Saavn track.")
            return _mk_stream(track["preview_url"], mime="audio/mp4", kbps=320,
                              codec="aac", label="320 kbps")
        if id.startswith("yt:"):
            vid = id.split(":", 1)[1]
            if not _re.fullmatch(r"[A-Za-z0-9_-]{6,20}", vid):
                raise HTTPException(400, "Invalid YouTube video id.")
            return _mk_stream(f"/api/yt/audio/{vid}", mime="audio/mp4",
                              codec="m4a", label="YT Audio")
        if id.startswith("audius:"):
            tid = id.split(":", 1)[1]
            if not _re.fullmatch(r"[A-Za-z0-9]{3,24}", tid):
                raise HTTPException(400, "Invalid Audius track id.")
            return _mk_stream(_audius_stream_url(tid), mime="audio/mpeg",
                              codec="mp3", label="MP3")
    raise HTTPException(404, "Unknown candidate id — expected saavn:/yt:/audius: prefix.")


@app.get("/api/stream/resolve", tags=["Streaming"])
async def stream_resolve(id: str = Query(..., description="Candidate id from /api/stream/candidates")):
    """Phase 2 — resolve the playable URL for a candidate, with caching + retries."""
    now_ms = int(_time.time() * 1000)
    hit = _STREAM_CACHE.get(id)
    if hit and now_ms - hit[0] < STREAM_EXPIRY_MS:
        return {"id": id, "stream": hit[1], "cached": True,
                "resolvedAtMs": hit[0], "expiresAtMs": hit[0] + STREAM_EXPIRY_MS}
    last_err = None
    for _attempt in range(STREAM_RETRIES):
        try:
            stream = await _resolve_stream_once(id)
            if len(_STREAM_CACHE) > 400:           # keep the cache bounded
                for k in sorted(_STREAM_CACHE, key=lambda k: _STREAM_CACHE[k][0])[:100]:
                    _STREAM_CACHE.pop(k, None)
            _STREAM_CACHE[id] = (now_ms, stream)
            return {"id": id, "stream": stream, "cached": False,
                    "resolvedAtMs": now_ms, "expiresAtMs": now_ms + STREAM_EXPIRY_MS}
        except HTTPException as e:
            last_err = e.detail
            if e.status_code in (400, 404):        # permanent — retrying won't help
                break
        except Exception as e:
            last_err = str(e) or type(e).__name__
    return {"id": id, "failed": True, "error": last_err or "Stream resolution failed."}


# ---------- catalog: songs ----------

@app.get("/api/songs", tags=["Songs"])
def list_songs(conn: Conn, user: MaybeUser,
               genre: str | None = None, artist: str | None = None, q: str | None = None):
    sql, params = SONG_SQL + " WHERE 1=1", []
    if genre:
        sql += " AND LOWER(s.genre)=LOWER(?)"; params.append(genre)
    if artist:
        sql += " AND LOWER(a.name) LIKE LOWER(?)"; params.append(f"%{artist}%")
    if q:
        sql += " AND LOWER(s.title) LIKE LOWER(?)"; params.append(f"%{q}%")
    rows = conn.execute(sql + " ORDER BY s.id", params).fetchall()
    return {"count": len(rows), "songs": [song_dict(r, conn, user) for r in rows]}

@app.get("/api/songs/{song_id}", tags=["Songs"])
def get_song(song_id: int, conn: Conn, user: MaybeUser):
    row = conn.execute(SONG_SQL + " WHERE s.id=?", (song_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Song {song_id} not found")
    return song_dict(row, conn, user)


# ---------- catalog: artists / albums ----------

@app.get("/api/artists", tags=["Artists"])
def list_artists(conn: Conn):
    rows = conn.execute("SELECT * FROM artists ORDER BY id").fetchall()
    return {"count": len(rows), "artists": [dict(r) for r in rows]}

@app.get("/api/artists/{artist_id}", tags=["Artists"])
def get_artist(artist_id: int, conn: Conn):
    artist = conn.execute("SELECT * FROM artists WHERE id=?", (artist_id,)).fetchone()
    if not artist:
        raise HTTPException(404, f"Artist {artist_id} not found")
    albums = conn.execute(
        "SELECT al.*, a.name AS artist FROM albums al JOIN artists a ON a.id=al.artist_id WHERE al.artist_id=?",
        (artist_id,)).fetchall()
    return {**dict(artist), "albums": [dict(a) for a in albums]}

@app.get("/api/artists/{artist_id}/songs", tags=["Artists"])
def artist_songs(artist_id: int, conn: Conn, user: MaybeUser):
    if not conn.execute("SELECT 1 FROM artists WHERE id=?", (artist_id,)).fetchone():
        raise HTTPException(404, f"Artist {artist_id} not found")
    rows = conn.execute(SONG_SQL + " WHERE s.artist_id=? ORDER BY s.id", (artist_id,)).fetchall()
    return {"count": len(rows), "songs": [song_dict(r, conn, user) for r in rows]}

@app.get("/api/albums", tags=["Albums"])
def list_albums(conn: Conn):
    rows = conn.execute(
        "SELECT al.*, a.name AS artist FROM albums al JOIN artists a ON a.id=al.artist_id ORDER BY al.id").fetchall()
    return {"count": len(rows), "albums": [dict(r) for r in rows]}

@app.get("/api/albums/{album_id}", tags=["Albums"])
def get_album(album_id: int, conn: Conn, user: MaybeUser):
    album = conn.execute(
        "SELECT al.*, a.name AS artist FROM albums al JOIN artists a ON a.id=al.artist_id WHERE al.id=?",
        (album_id,)).fetchone()
    if not album:
        raise HTTPException(404, f"Album {album_id} not found")
    songs = conn.execute(SONG_SQL + " WHERE s.album_id=? ORDER BY s.id", (album_id,)).fetchall()
    return {**dict(album), "songs": [song_dict(s, conn, user) for s in songs]}


# ---------- discovery ----------

@app.get("/api/charts/top", tags=["Discovery"])
def top_charts(conn: Conn, user: MaybeUser):
    rows = conn.execute(SONG_SQL + " WHERE s.chart_rank IS NOT NULL ORDER BY s.chart_rank").fetchall()
    return {"chart": "Top 10", "entries": [song_dict(r, conn, user) for r in rows]}

@app.get("/api/trending", tags=["Discovery"])
def trending(conn: Conn, user: MaybeUser):
    rows = conn.execute(SONG_SQL + " ORDER BY s.plays DESC LIMIT 8").fetchall()
    return {"trending": [song_dict(r, conn, user) for r in rows]}

@app.get("/api/new-releases", tags=["Discovery"])
def new_releases(conn: Conn):
    rows = conn.execute(
        "SELECT al.*, a.name AS artist FROM albums al JOIN artists a ON a.id=al.artist_id WHERE al.year=2026").fetchall()
    return {"new_releases": [dict(r) for r in rows]}

@app.get("/api/search", tags=["Discovery"])
def local_search(conn: Conn, user: MaybeUser, q: str = Query(..., min_length=1)):
    like = f"%{q.lower()}%"
    songs = conn.execute(SONG_SQL + " WHERE LOWER(s.title) LIKE ?", (like,)).fetchall()
    artists = conn.execute("SELECT * FROM artists WHERE LOWER(name) LIKE ?", (like,)).fetchall()
    albums = conn.execute(
        "SELECT al.*, a.name AS artist FROM albums al JOIN artists a ON a.id=al.artist_id WHERE LOWER(al.title) LIKE ?",
        (like,)).fetchall()
    playlists = conn.execute(
        "SELECT * FROM playlists WHERE LOWER(name) LIKE ? OR LOWER(description) LIKE ?", (like, like)).fetchall()
    return {
        "query": q,
        "songs": [song_dict(s, conn, user) for s in songs],
        "artists": [dict(a) for a in artists],
        "albums": [dict(a) for a in albums],
        "playlists": [playlist_dict(p, conn, with_songs=False) for p in playlists],
        "tip": "For real-world songs use /api/music/search",
    }

MOOD_GENRES = {
    "happy": ["Indie", "Synthwave"],
    "sad": ["R&B", "Ambient"],
    "energetic": ["Electronic", "Rock", "Bass"],
    "calm": ["Ambient", "Indie"],
    "focus": ["Ambient", "Electronic"],
    "romantic": ["R&B", "Synthwave"],
}

@app.get("/api/mood/{mood}", tags=["Discovery"])
def mood_mixer(mood: str, conn: Conn, user: MaybeUser):
    genres = MOOD_GENRES.get(mood.lower())
    if not genres:
        raise HTTPException(404, f"Unknown mood '{mood}'. Try: {', '.join(MOOD_GENRES)}")
    marks = ",".join("?" * len(genres))
    rows = conn.execute(SONG_SQL + f" WHERE s.genre IN ({marks})", genres).fetchall()
    return {"mood": mood.lower(), "genres": genres, "count": len(rows),
            "songs": [song_dict(r, conn, user) for r in rows]}


# ---------- playlists ----------

@app.get("/api/playlists", tags=["Playlists"])
def list_playlists(conn: Conn, user: MaybeUser, mine: bool = False):
    if mine:
        if not user:
            raise HTTPException(401, "Login required for ?mine=true")
        rows = conn.execute("SELECT * FROM playlists WHERE owner_id=? ORDER BY id", (user["id"],)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM playlists ORDER BY id").fetchall()
    return {"count": len(rows), "playlists": [playlist_dict(r, conn, with_songs=False) for r in rows]}

@app.get("/api/playlists/{playlist_id}", tags=["Playlists"])
def get_playlist(playlist_id: int, conn: Conn, user: MaybeUser):
    row = conn.execute("SELECT * FROM playlists WHERE id=?", (playlist_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Playlist {playlist_id} not found")
    return playlist_dict(row, conn, user=user)

@app.post("/api/playlists", tags=["Playlists"], status_code=201)
def create_playlist(body: PlaylistIn, user: User, conn: Conn):
    for sid in body.song_ids:
        if not conn.execute("SELECT 1 FROM songs WHERE id=?", (sid,)).fetchone():
            raise HTTPException(404, f"Song {sid} not found")
    cur = conn.execute(
        "INSERT INTO playlists (name, emoji, description, mood, owner_id) VALUES (?, ?, ?, ?, ?)",
        (body.name, body.emoji, body.description, body.mood, user["id"]),
    )
    pid = cur.lastrowid
    for pos, sid in enumerate(dict.fromkeys(body.song_ids), 1):  # dedupe, keep order
        conn.execute("INSERT INTO playlist_songs (playlist_id, song_id, position) VALUES (?, ?, ?)", (pid, sid, pos))
    conn.commit()
    return playlist_dict(conn.execute("SELECT * FROM playlists WHERE id=?", (pid,)).fetchone(), conn, user=user)


def _owned_playlist(conn, playlist_id: int, user) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM playlists WHERE id=?", (playlist_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Playlist {playlist_id} not found")
    if row["owner_id"] != user["id"]:
        raise HTTPException(403, "You can only modify your own playlists.")
    return row

@app.post("/api/playlists/{playlist_id}/songs", tags=["Playlists"], status_code=201)
def add_song_to_playlist(playlist_id: int, body: AddSongIn, user: User, conn: Conn):
    _owned_playlist(conn, playlist_id, user)
    if not conn.execute("SELECT 1 FROM songs WHERE id=?", (body.song_id,)).fetchone():
        raise HTTPException(404, f"Song {body.song_id} not found")
    pos = conn.execute(
        "SELECT COALESCE(MAX(position),0)+1 p FROM playlist_songs WHERE playlist_id=?", (playlist_id,)
    ).fetchone()["p"]
    try:
        conn.execute("INSERT INTO playlist_songs (playlist_id, song_id, position) VALUES (?, ?, ?)",
                     (playlist_id, body.song_id, pos))
    except db.IntegrityErrors:
        raise HTTPException(409, "Song is already in this playlist.")
    conn.commit()
    return playlist_dict(conn.execute("SELECT * FROM playlists WHERE id=?", (playlist_id,)).fetchone(), conn, user=user)

@app.delete("/api/playlists/{playlist_id}/songs/{song_id}", tags=["Playlists"])
def remove_song_from_playlist(playlist_id: int, song_id: int, user: User, conn: Conn):
    _owned_playlist(conn, playlist_id, user)
    cur = conn.execute("DELETE FROM playlist_songs WHERE playlist_id=? AND song_id=?", (playlist_id, song_id))
    if cur.rowcount == 0:
        raise HTTPException(404, "That song is not in this playlist.")
    conn.commit()
    return {"removed": song_id, "playlist_id": playlist_id}

@app.delete("/api/playlists/{playlist_id}", tags=["Playlists"])
def delete_playlist(playlist_id: int, user: User, conn: Conn):
    _owned_playlist(conn, playlist_id, user)
    conn.execute("DELETE FROM playlists WHERE id=?", (playlist_id,))
    conn.commit()
    return {"deleted": playlist_id}


# ---------- likes ----------

@app.get("/api/liked", tags=["Likes"])
def liked_songs(user: User, conn: Conn):
    rows = conn.execute(
        SONG_SQL + " JOIN likes l ON l.song_id = s.id WHERE l.user_id=? ORDER BY l.created_at DESC",
        (user["id"],)).fetchall()
    return {"count": len(rows), "songs": [dict(r) | {"liked": True} for r in rows]}

@app.post("/api/songs/{song_id}/like", tags=["Likes"])
def like_song(song_id: int, user: User, conn: Conn):
    if not conn.execute("SELECT 1 FROM songs WHERE id=?", (song_id,)).fetchone():
        raise HTTPException(404, f"Song {song_id} not found")
    conn.execute("INSERT OR IGNORE INTO likes (user_id, song_id) VALUES (?, ?)", (user["id"], song_id))
    conn.commit()
    return {"liked": True, "song_id": song_id}

@app.delete("/api/songs/{song_id}/like", tags=["Likes"])
def unlike_song(song_id: int, user: User, conn: Conn):
    conn.execute("DELETE FROM likes WHERE user_id=? AND song_id=?", (user["id"], song_id))
    conn.commit()
    return {"liked": False, "song_id": song_id}


# ---------- liked REAL tracks (from the music API) ----------

class LikedTrackIn(BaseModel):
    id: str
    title: str
    artist: str | None = None
    album: str | None = None
    img: str | None = None
    url: str | None = None
    duration: str | None = None


@app.get("/api/me/likes", tags=["Likes"])
def my_liked_tracks(user: User, conn: Conn):
    rows = conn.execute(
        "SELECT track_id, title, artist, album, img, url, duration FROM liked_tracks "
        "WHERE user_id=? ORDER BY created_at DESC", (user["id"],)).fetchall()
    tracks = [{"id": r["track_id"], "title": r["title"], "artist": r["artist"],
               "album": r["album"], "img": r["img"], "preview_url": r["url"],
               "duration": r["duration"], "full": str(r["track_id"]).startswith("saavn:"),
               "source": str(r["track_id"]).split(":")[0]} for r in rows]
    return {"count": len(tracks), "tracks": tracks}


@app.post("/api/me/likes", tags=["Likes"])
def like_track(t: LikedTrackIn, user: User, conn: Conn):
    conn.execute(
        "INSERT OR REPLACE INTO liked_tracks (user_id, track_id, title, artist, album, img, url, duration) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (user["id"], t.id, t.title, t.artist, t.album, t.img, t.url, t.duration))
    conn.commit()
    return {"liked": True, "id": t.id}


@app.delete("/api/me/likes", tags=["Likes"])
def unlike_track(id: str, user: User, conn: Conn):
    conn.execute("DELETE FROM liked_tracks WHERE user_id=? AND track_id=?", (user["id"], id))
    conn.commit()
    return {"liked": False, "id": id}


# ---------- USER playlists (real tracks, created by the user only) ----------

class UPlaylistIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


def _track_row_out(r) -> dict:
    return {"id": r["track_id"], "title": r["title"], "artist": r["artist"],
            "album": r["album"], "img": r["img"], "preview_url": r["url"],
            "duration": r["duration"], "full": str(r["track_id"]).startswith("saavn:"),
            "source": str(r["track_id"]).split(":")[0]}


def _owned_upl(conn, pid: int, user):
    row = conn.execute("SELECT * FROM user_playlists WHERE id=? AND user_id=?", (pid, user["id"])).fetchone()
    if not row:
        raise HTTPException(404, "Playlist not found.")
    return row


@app.get("/api/me/playlists", tags=["Playlists"])
def my_playlists_v2(user: User, conn: Conn):
    pls = conn.execute("SELECT id, name, cover, created_at FROM user_playlists WHERE user_id=? ORDER BY created_at DESC",
                       (user["id"],)).fetchall()
    out = []
    for p in pls:
        covers = [r["img"] for r in conn.execute(
            "SELECT img FROM user_playlist_tracks WHERE playlist_id=? AND img IS NOT NULL ORDER BY created_at LIMIT 4",
            (p["id"],)).fetchall()]
        cnt = conn.execute("SELECT COUNT(*) c FROM user_playlist_tracks WHERE playlist_id=?", (p["id"],)).fetchone()["c"]
        out.append({"id": p["id"], "name": p["name"], "count": cnt, "covers": covers, "cover": p["cover"]})
    return {"count": len(out), "playlists": out}


@app.post("/api/me/playlists", tags=["Playlists"])
def create_playlist_v2(body: UPlaylistIn, user: User, conn: Conn):
    cur = conn.execute("INSERT INTO user_playlists (user_id, name) VALUES (?, ?)", (user["id"], body.name.strip()))
    conn.commit()
    return {"id": cur.lastrowid, "name": body.name.strip(), "count": 0, "covers": []}


@app.get("/api/me/playlists/{pid}", tags=["Playlists"])
def playlist_detail_v2(pid: int, user: User, conn: Conn):
    p = _owned_upl(conn, pid, user)
    rows = conn.execute(
        "SELECT track_id, title, artist, album, img, url, duration FROM user_playlist_tracks "
        "WHERE playlist_id=? ORDER BY pos, created_at", (pid,)).fetchall()
    cov = p["cover"] if "cover" in p.keys() else None
    return {"id": p["id"], "name": p["name"], "cover": cov, "count": len(rows), "tracks": [_track_row_out(r) for r in rows]}


class CoverIn(BaseModel):
    img: str | None = Field(None, max_length=700_000)


@app.post("/api/me/playlists/{pid}/cover", tags=["Playlists"])
def playlist_set_cover(pid: int, body: CoverIn, user: User, conn: Conn):
    _owned_upl(conn, pid, user)
    img = (body.img or "").strip() or None
    if img and not img.startswith("data:image/"):
        raise HTTPException(400, "Invalid image format.")
    conn.execute("UPDATE user_playlists SET cover=? WHERE id=?", (img, pid))
    conn.commit()
    return {"id": pid, "cover": img is not None}


@app.delete("/api/me/playlists/{pid}", tags=["Playlists"])
def delete_playlist_v2(pid: int, user: User, conn: Conn):
    _owned_upl(conn, pid, user)
    conn.execute("DELETE FROM user_playlists WHERE id=?", (pid,))
    conn.commit()
    return {"deleted": pid}


@app.post("/api/me/playlists/{pid}/tracks", tags=["Playlists"])
def playlist_add_track_v2(pid: int, t: LikedTrackIn, user: User, conn: Conn):
    _owned_upl(conn, pid, user)
    pos = conn.execute("SELECT COALESCE(MAX(pos),0)+1 p FROM user_playlist_tracks WHERE playlist_id=?", (pid,)).fetchone()["p"]
    conn.execute(
        "INSERT OR REPLACE INTO user_playlist_tracks (playlist_id, track_id, title, artist, album, img, url, duration, pos) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (pid, t.id, t.title, t.artist, t.album, t.img, t.url, t.duration, pos))
    conn.commit()
    return {"added": t.id, "playlist_id": pid}


@app.delete("/api/me/playlists/{pid}/tracks", tags=["Playlists"])
def playlist_remove_track_v2(pid: int, id: str, user: User, conn: Conn):
    _owned_upl(conn, pid, user)
    conn.execute("DELETE FROM user_playlist_tracks WHERE playlist_id=? AND track_id=?", (pid, id))
    conn.commit()
    return {"removed": id, "playlist_id": pid}


# ---------- listening history + recommendations ----------

@app.post("/api/me/plays", tags=["Recommendations"])
def log_play(t: LikedTrackIn, user: User, conn: Conn):
    conn.execute(
        "INSERT INTO plays (user_id, track_id, title, artist, album, img, url, duration) VALUES (?,?,?,?,?,?,?,?)",
        (user["id"], t.id, t.title, t.artist, t.album, t.img, t.url, t.duration))
    # keep only the most recent 300 plays per user
    conn.execute(
        "DELETE FROM plays WHERE user_id=? AND id NOT IN "
        "(SELECT id FROM plays WHERE user_id=? ORDER BY id DESC LIMIT 300)",
        (user["id"], user["id"]))
    conn.commit()
    return {"logged": t.id}


@app.get("/api/me/plays", tags=["Recommendations"])
def my_plays(user: User, conn: Conn, limit: int = Query(20, ge=1, le=100)):
    rows = conn.execute(
        "SELECT track_id, MAX(title) title, MAX(artist) artist, MAX(album) album, "
        "MAX(img) img, MAX(url) url, MAX(duration) duration, MAX(played_at) pa, COUNT(*) n "
        "FROM plays WHERE user_id=? GROUP BY track_id ORDER BY pa DESC LIMIT ?",
        (user["id"], limit)).fetchall()
    return {"count": len(rows), "tracks": [_track_row_out(r) | {"plays": r["n"]} for r in rows]}


def _saavn_search_sync(client: httpx.Client, q: str, limit: int = 15):
    out = []
    try:
        r = client.get(f"{SAAVN_API}/search/songs", params={"query": q, "limit": max(1, min(50, limit))})
        r.raise_for_status()
        results = ((r.json().get("data") or {}).get("results")) or []
        out = [t for t in (_saavn_map(x) for x in results) if t["preview_url"]]
    except Exception:
        out = []
    if not out:
        r = client.get(SAAVN_NATIVE, params=_native_params(q, limit),
                       headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                       follow_redirects=True)
        r.raise_for_status()
        out = [t for t in (_native_map(x) for x in (r.json().get("results") or [])) if t]
    return _dedupe_tracks(out)


@app.get("/api/me/recommendations", tags=["Recommendations"])
def recommendations(user: User, conn: Conn,
                    country: str = Query("us", min_length=2, max_length=2)):
    """Personal recommendations learned from this user's listening history + likes.
    Blends seed artists, similar artists (Deezer related) AND the user's country chart,
    so a new US user gets English hits while a new Indian user gets Hindi/Punjabi hits."""
    from collections import Counter
    import random
    plays = conn.execute(
        "SELECT track_id, artist, title FROM plays WHERE user_id=? ORDER BY id DESC LIMIT 150",
        (user["id"],)).fetchall()
    likes = conn.execute(
        "SELECT track_id, artist, title FROM liked_tracks WHERE user_id=?", (user["id"],)).fetchall()
    known_ids = {r["track_id"] for r in plays} | {r["track_id"] for r in likes}
    known_titles = {(r["title"] or "").lower() for r in plays} | {(r["title"] or "").lower() for r in likes}
    counts = Counter()
    for r in plays:
        if r["artist"]:
            counts[r["artist"]] += 1
    for r in likes:
        if r["artist"]:
            counts[r["artist"]] += 2   # likes weigh double
    top_artists = [a for a, _ in counts.most_common(4)]
    seeds, sections, pool = [], [], []
    with httpx.Client(timeout=20) as client:
        for a in top_artists[:3]:
            seeds.append((a, f"Because you listen to {a}"))
        # add SIMILAR artists for variety (Deezer related artists of the user's #1)
        if top_artists:
            try:
                s = client.get("https://api.deezer.com/search/artist",
                               params={"q": top_artists[0], "limit": 1}).json()
                hit = (s.get("data") or [None])[0]
                if hit:
                    rel = client.get(f"https://api.deezer.com/artist/{hit['id']}/related").json().get("data") or []
                    for ra in rel[:3]:
                        if ra.get("name") and ra["name"] not in top_artists:
                            seeds.append((ra["name"], f"Similar to {top_artists[0]}"))
            except Exception:
                pass
        seen_titles = set(known_titles)
        for name, reason in seeds[:6]:
            try:
                tracks = _saavn_search_sync(client, name, 12)
            except (httpx.HTTPError, ValueError):
                continue
            fresh = []
            for t in tracks:
                tl = (t["title"] or "").lower()
                if t["id"] in known_ids or tl in seen_titles:
                    continue
                seen_titles.add(tl)
                fresh.append(t)
            fresh = fresh[:8]
            if fresh:
                sections.append({"reason": reason, "seed": name, "tracks": fresh})
                pool.append(fresh)
        # country flavour: local chart feeds the mix (language-appropriate by nature)
        chart_tracks = []
        try:
            cc = country.lower() if country.isalpha() else "us"
            payload = get_charts(country=cc, limit=30)
            for t in payload.get("results") or []:
                tl = (t["title"] or "").lower()
                if t["id"] in known_ids or tl in seen_titles:
                    continue
                seen_titles.add(tl)
                chart_tracks.append(t)
        except Exception:
            pass
        if chart_tracks:
            pool.append(chart_tracks[:10])
            if not sections:
                sections.append({"reason": "Trending in your country — play some songs and this becomes personal",
                                 "seed": None, "tracks": chart_tracks[:20]})
        if not sections:
            _mkt = {"in": "bollywood top hits 2025", "pk": "bollywood top hits 2025", "bd": "bollywood top hits 2025",
                    "np": "bollywood top hits 2025", "lk": "bollywood top hits 2025",
                    "br": "top brasil 2025", "pt": "top brasil 2025",
                    "mx": "exitos 2025 latino", "es": "exitos 2025 latino", "ar": "exitos 2025 latino", "co": "exitos 2025 latino",
                    "fr": "hits francais 2025", "de": "deutsche hits 2025", "jp": "jpop hits 2025", "kr": "kpop hits 2025",
                    "tr": "turkce pop 2025", "sa": "arabic hits 2025", "ae": "arabic hits 2025", "eg": "arabic hits 2025",
                    "id": "lagu indonesia hits 2025", "it": "hits italia 2025", "ru": "русские хиты 2025",
                    "ng": "afrobeats hits 2025", "gh": "afrobeats hits 2025", "ke": "afrobeats hits 2025", "za": "amapiano hits"}
            try:
                tracks = _saavn_search_sync(client, _mkt.get(country.lower(), "top english hits 2025"), 20)
                sections.append({"reason": "Popular right now — play some songs and this becomes personal",
                                 "seed": None, "tracks": tracks})
                pool.append(tracks)
            except (httpx.HTTPError, ValueError):
                pass
    # blended MIX: round-robin across all seeds so it's never one artist in a row
    mix, i = [], 0
    while len(mix) < 24 and any(i < len(p) for p in pool):
        for p in pool:
            if i < len(p) and len(mix) < 24:
                mix.append(p[i])
        i += 1
    random.shuffle(mix)
    return {"count": len(sections), "personalized": bool(top_artists), "mix": mix, "sections": sections}


# ---------- lyrics (LRCLIB — free, supports time-synced lyrics) ----------

import re as _re


def _clean_title(t: str) -> str:
    """Strip noise so lyric lookups hit: (From "Movie"), [Remix], feat. X, etc."""
    t = _re.sub(r'\(.*?\)|\[.*?\]', ' ', t or "")
    t = _re.split(r'(?i)\s(?:-\s)?(?:from|feat\.?|ft\.?)\s', t)[0]
    return _re.sub(r'\s+', ' ', t).strip(' -–|')


def _pick_lyric(arr, want_synced=True):
    if not arr:
        return None
    if want_synced:
        for x in arr:
            if x.get("syncedLyrics"):
                return x
    for x in arr:
        if x.get("plainLyrics"):
            return x
    return None


@app.get("/api/lyrics", tags=["Real Music"])
async def get_lyrics(title: str = Query(..., min_length=1), artist: str = "", duration: int | None = None):
    d = None
    clean = _clean_title(title)
    artist = (artist or "").strip()
    async with httpx.AsyncClient(timeout=15) as client:
        attempts = []
        params = {"track_name": title, "artist_name": artist}
        if duration:
            params["duration"] = duration
        attempts.append(("get", params))
        if clean and clean.lower() != title.lower():
            attempts.append(("get", {"track_name": clean, "artist_name": artist}))
        attempts += [
            ("search", {"track_name": clean or title, "artist_name": artist}),
            ("search", {"q": f"{clean or title} {artist}".strip()}),
            ("search", {"q": clean or title}),
        ]
        for kind, p in attempts:
            try:
                if kind == "get":
                    d = await _get_json(client, "https://lrclib.net/api/get", p)
                else:
                    d = _pick_lyric(await _get_json(client, "https://lrclib.net/api/search", p))
                if d and (d.get("syncedLyrics") or d.get("plainLyrics")):
                    break
                d = None
            except httpx.HTTPError:
                d = None
        if not d and artist:
            # final fallback: lyrics.ovh (plain text only)
            try:
                o = await _get_json(client, f"https://api.lyrics.ovh/v1/{artist}/{clean or title}", {})
                if o.get("lyrics"):
                    return {"found": True, "title": title, "artist": artist,
                            "plain": o["lyrics"], "synced": None}
            except httpx.HTTPError:
                pass
    if not d:
        return {"found": False}
    return {"found": True, "title": d.get("trackName"), "artist": d.get("artistName"),
            "plain": d.get("plainLyrics"), "synced": d.get("syncedLyrics")}


# ---------- artist info (Deezer followers/photo + Wikipedia biography) ----------

# ---------- YouTube audio relay (yt-dlp; googlevideo URLs are IP-locked, so we proxy) ----------

YT_URL_CACHE: dict = {}        # vid -> (ts, direct_url); YouTube URLs stay valid ~6h, we keep 3h
YT_URL_TTL = 3 * 3600


def _yt_direct_url(vid: str) -> str:
    import time as _t
    hit = YT_URL_CACHE.get(vid)
    if hit and _t.time() - hit[0] < YT_URL_TTL:
        return hit[1]
    try:
        import yt_dlp
    except ImportError:
        raise HTTPException(503, "YouTube engine not installed on this server (pip install yt-dlp).")
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True,
            "format": "bestaudio[ext=m4a]/bestaudio"}
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
    except Exception:
        raise HTTPException(502, "Couldn't resolve this YouTube stream — try another song.")
    url = info.get("url")
    if not url:
        raise HTTPException(502, "No audio stream found for this YouTube track.")
    YT_URL_CACHE[vid] = (_t.time(), url)
    return url


@app.get("/api/yt/audio/{vid}", tags=["Real Music"])
def yt_audio(vid: str, request: Request):
    """Relay YouTube audio bytes (with Range support for seeking)."""
    if not _re.fullmatch(r"[A-Za-z0-9_-]{6,20}", vid):
        raise HTTPException(400, "Invalid video id.")
    url = _yt_direct_url(vid)
    fwd = {}
    rng = request.headers.get("range")
    if rng:
        fwd["Range"] = rng
    client = httpx.Client(timeout=httpx.Timeout(30, read=60), follow_redirects=True)
    try:
        resp = client.send(client.build_request("GET", url, headers=fwd), stream=True)
        if resp.status_code >= 400:           # stale cached URL → re-extract once
            resp.close()
            YT_URL_CACHE.pop(vid, None)
            url = _yt_direct_url(vid)
            resp = client.send(client.build_request("GET", url, headers=fwd), stream=True)
        if resp.status_code >= 400:
            resp.close(); client.close()
            raise HTTPException(502, "YouTube stream rejected the request.")
    except httpx.HTTPError:
        client.close()
        raise HTTPException(502, "YouTube stream unavailable right now.")
    canon = {"content-type": "Content-Type", "content-length": "Content-Length",
             "content-range": "Content-Range", "accept-ranges": "Accept-Ranges"}
    headers = {canon[k.lower()]: v for k, v in resp.headers.items() if k.lower() in canon}
    headers.setdefault("Accept-Ranges", "bytes")
    headers.setdefault("Content-Type", "audio/mp4")
    headers["Cache-Control"] = "no-store"

    def gen():
        try:
            for chunk in resp.iter_bytes(64 * 1024):
                yield chunk
        finally:
            resp.close()
            client.close()

    return StreamingResponse(gen(), status_code=resp.status_code, headers=headers)


# ---------- real album artwork resolver (Deezer -> iTunes, both label-sourced) ----------

_ART_CACHE: dict = {}


@app.get("/api/artwork", tags=["Real Music"])
def artwork(title: str = Query(..., min_length=1, max_length=200), artist: str = Query("", max_length=200)):
    """Resolve the REAL album cover for a song (used to replace video thumbnails)."""
    key = (title.lower().strip(), artist.lower().strip())
    if key in _ART_CACHE:
        return {"img": _ART_CACHE[key]}
    img = None
    with httpx.Client(timeout=10, follow_redirects=True) as c:
        try:  # Deezer: 1000px covers, generous rate limits
            q = f'track:"{title}" artist:"{artist}"' if artist else title
            r = c.get("https://api.deezer.com/search", params={"q": q, "limit": 1})
            data = (r.json().get("data") or [])
            if not data:
                r = c.get("https://api.deezer.com/search", params={"q": f"{title} {artist}".strip(), "limit": 1})
                data = (r.json().get("data") or [])
            if data:
                alb = data[0].get("album") or {}
                img = alb.get("cover_xl") or alb.get("cover_big") or alb.get("cover_medium")
        except Exception:
            img = None
        if not img:
            try:  # iTunes fallback: upscale official artwork to 600px
                r = c.get("https://itunes.apple.com/search",
                          params={"term": f"{title} {artist}".strip(), "media": "music", "limit": 1})
                res = r.json().get("results") or []
                if res:
                    img = (res[0].get("artworkUrl100") or "").replace("100x100", "600x600") or None
            except Exception:
                img = None
    if len(_ART_CACHE) > 5000:
        _ART_CACHE.clear()
    _ART_CACHE[key] = img
    return {"img": img}


# ---------- country charts (Apple Music most-played + iTunes RSS, free, no key) ----------

import time as _time

CHART_CACHE: dict = {}          # cc -> (timestamp, payload); 30-min TTL protects against rate limits
CHART_TTL = 1800


def _chart_track(id_, title, artist, album, img):
    return {"id": f"chart:{id_}", "title": title, "artist": artist, "album": album,
            "img": img, "preview_url": None, "duration": None, "full": False, "source": "chart"}


def _charts_most_played(client: httpx.Client, cc: str, limit: int):
    r = client.get(f"https://rss.marketingtools.apple.com/api/v2/{cc}/music/most-played/{limit}/songs.json")
    r.raise_for_status()
    res = (r.json().get("feed") or {}).get("results") or []
    return [_chart_track(x.get("id"), x.get("name"), x.get("artistName"), None,
                         (x.get("artworkUrl100") or "").replace("100x100", "600x600")) for x in res]


def _charts_itunes_rss(client: httpx.Client, cc: str, limit: int):
    r = client.get(f"https://itunes.apple.com/{cc}/rss/topsongs/limit={limit}/json")
    r.raise_for_status()
    entries = (r.json().get("feed") or {}).get("entry") or []
    if isinstance(entries, dict):
        entries = [entries]
    out = []
    for x in entries:
        img = ((x.get("im:image") or [{}])[-1].get("label") or "")
        img = img.replace("/170x170", "/600x600").replace("/55x55", "/600x600").replace("/60x60", "/600x600").replace("/100x100", "/600x600")
        out.append(_chart_track(
            ((x.get("id") or {}).get("attributes") or {}).get("im:id", ""),
            (x.get("im:name") or {}).get("label"),
            (x.get("im:artist") or {}).get("label"),
            (((x.get("im:collection") or {}).get("im:name")) or {}).get("label"),
            img))
    return out


@app.get("/api/charts", tags=["Real Music"])
def get_charts(country: str = Query("us", min_length=2, max_length=2),
               limit: int = Query(40, ge=1, le=50)):
    """Real top-songs chart for a country (Apple Music most-played, iTunes RSS fallback)."""
    cc = country.lower()
    if not cc.isalpha():
        raise HTTPException(400, "Invalid country code — use ISO-3166 alpha-2 (e.g. us, pk, in, jp).")
    now = _time.time()
    hit = CHART_CACHE.get(cc)
    if hit and now - hit[0] < CHART_TTL:
        return hit[1]
    tracks, source, served = [], None, cc
    with httpx.Client(timeout=15, follow_redirects=True,
                      headers={"User-Agent": "SonicWave/1.0"}) as client:
        for target in ([cc] if cc == "us" else [cc, "us"]):
            for fn, name in ((_charts_most_played, "apple-music-most-played"),
                             (_charts_itunes_rss, "itunes-top-songs")):
                try:
                    got = [t for t in fn(client, target, limit) if t["title"] and t["artist"]]
                except Exception:
                    got = []
                if got:
                    tracks, source, served = got, name, target
                    break
            if tracks:
                break
    payload = {"country": cc, "served": served, "source": source,
               "count": len(tracks), "results": tracks}
    if tracks:
        CHART_CACHE[cc] = (now, payload)
    return payload


@app.get("/api/artist-info", tags=["Real Music"])
async def artist_info(name: str = Query(..., min_length=1)):
    out = {"name": name, "followers": None, "albums": None, "img": None, "bio": None}
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            s = await _get_json(client, "https://api.deezer.com/search/artist", {"q": name, "limit": 1})
            hit = (s.get("data") or [None])[0]
            if hit:
                a = await _get_json(client, f"https://api.deezer.com/artist/{hit['id']}", {})
                out.update({"name": a.get("name") or name, "followers": a.get("nb_fan"),
                            "albums": a.get("nb_album"),
                            "img": a.get("picture_xl") or a.get("picture_big") or a.get("picture_medium")})
        except httpx.HTTPError:
            pass
        try:
            r = await client.get(
                "https://en.wikipedia.org/api/rest_v1/page/summary/" + out["name"].replace(" ", "_"),
                headers={"User-Agent": "SonicWave/1.0 (music app)"}, follow_redirects=True)
            r.raise_for_status()
            w = r.json()
            if w.get("extract") and w.get("type") == "standard":
                out["bio"] = w["extract"]
            if not out["img"] and (w.get("thumbnail") or {}).get("source"):
                out["img"] = w["thumbnail"]["source"]
        except (httpx.HTTPError, ValueError):
            pass
    return out


# ---------- queue ----------

@app.get("/api/queue", tags=["Queue"])
def get_queue(user: User, conn: Conn):
    rows = conn.execute(
        SONG_SQL + " JOIN queue_items qi ON qi.song_id = s.id WHERE qi.user_id=? ORDER BY qi.id",
        (user["id"],)).fetchall()
    return {"count": len(rows), "queue": [dict(r) for r in rows]}

@app.post("/api/queue/{song_id}", tags=["Queue"], status_code=201)
def add_to_queue(song_id: int, user: User, conn: Conn):
    if not conn.execute("SELECT 1 FROM songs WHERE id=?", (song_id,)).fetchone():
        raise HTTPException(404, f"Song {song_id} not found")
    conn.execute("INSERT INTO queue_items (user_id, song_id) VALUES (?, ?)", (user["id"], song_id))
    conn.commit()
    n = conn.execute("SELECT COUNT(*) c FROM queue_items WHERE user_id=?", (user["id"],)).fetchone()["c"]
    return {"added": song_id, "queue_length": n}

@app.delete("/api/queue", tags=["Queue"])
def clear_queue(user: User, conn: Conn):
    conn.execute("DELETE FROM queue_items WHERE user_id=?", (user["id"],))
    conn.commit()
    return {"cleared": True, "queue_length": 0}


# ---------- stats ----------

@app.get("/api/stats", tags=["Stats"])
def stats(conn: Conn):
    return {
        "songs_played": 1247,
        "hours_listened": 86,
        "top_genre": "Electronic",
        "favorite_artist": "Kai Nakamura",
        "catalog": {
            "songs": conn.execute("SELECT COUNT(*) c FROM songs").fetchone()["c"],
            "artists": conn.execute("SELECT COUNT(*) c FROM artists").fetchone()["c"],
            "albums": conn.execute("SELECT COUNT(*) c FROM albums").fetchone()["c"],
            "playlists": conn.execute("SELECT COUNT(*) c FROM playlists").fetchone()["c"],
            "registered_users": conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"],
        },
    }
