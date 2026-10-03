"""SonicWave music catalog — in-memory database."""

ARTISTS = [
    {"id": 1, "name": "Eclipse Hollow", "genre": "Electronic", "emoji": "🌌", "followers": 284_512},
    {"id": 2, "name": "Zara Voss", "genre": "Synthwave", "emoji": "🌸", "followers": 198_340},
    {"id": 3, "name": "Kai Nakamura", "genre": "Ambient", "emoji": "🌊", "followers": 356_780},
    {"id": 4, "name": "The Void Keys", "genre": "Bass", "emoji": "👻", "followers": 142_905},
    {"id": 5, "name": "Nova Meridian", "genre": "Electronic", "emoji": "💎", "followers": 121_450},
    {"id": 6, "name": "Mira Osei", "genre": "R&B", "emoji": "🌙", "followers": 167_233},
    {"id": 7, "name": "Rex Thunder", "genre": "Rock", "emoji": "🎸", "followers": 209_871},
    {"id": 8, "name": "Sage & Fleur", "genre": "Indie", "emoji": "🌿", "followers": 98_654},
    {"id": 9, "name": "Lyra Systems", "genre": "Electronic", "emoji": "✨", "followers": 133_902},
]

ALBUMS = [
    {"id": 1, "title": "Neon Dreams Vol. 3", "artist_id": 1, "genre": "Electronic", "tracks": 14, "year": 2026, "tag": "Featured"},
    {"id": 2, "title": "Midnight Frequencies", "artist_id": 2, "genre": "Synthwave", "tracks": 10, "year": 2026, "tag": "New Release"},
    {"id": 3, "title": "Solar Wind Sessions", "artist_id": 3, "genre": "Ambient", "tracks": 8, "year": 2026, "tag": "Trending"},
    {"id": 4, "title": "Underground Signal", "artist_id": 4, "genre": "Bass", "tracks": 9, "year": 2025, "tag": None},
    {"id": 5, "title": "Spectral Lines", "artist_id": 5, "genre": "Electronic", "tracks": 11, "year": 2025, "tag": None},
    {"id": 6, "title": "Depths of Zero", "artist_id": 6, "genre": "R&B", "tracks": 8, "year": 2026, "tag": "New Release"},
    {"id": 7, "title": "High Voltage", "artist_id": 7, "genre": "Rock", "tracks": 12, "year": 2026, "tag": "New Release"},
    {"id": 8, "title": "Golden Hour", "artist_id": 8, "genre": "Indie", "tracks": 9, "year": 2026, "tag": "New Release"},
    {"id": 9, "title": "Orbital Array", "artist_id": 9, "genre": "Electronic", "tracks": 10, "year": 2026, "tag": "New Release"},
]

SONGS = [
    {"id": 1,  "title": "Neon Pulse",        "artist_id": 1, "album_id": 1, "genre": "Electronic", "duration": "3:34", "emoji": "🌌", "plays": 1_204_331, "chart_rank": 1},
    {"id": 2,  "title": "Midnight Circuit",  "artist_id": 1, "album_id": 1, "genre": "Electronic", "duration": "3:07", "emoji": "⚡", "plays": 1_015_887, "chart_rank": 2},
    {"id": 3,  "title": "Cyber Bloom",       "artist_id": 2, "album_id": 2, "genre": "Synthwave",  "duration": "4:13", "emoji": "🌸", "plays": 986_402,  "chart_rank": 3},
    {"id": 4,  "title": "Velvet Static",     "artist_id": 2, "album_id": 2, "genre": "Synthwave",  "duration": "3:18", "emoji": "🎭", "plays": 874_119,  "chart_rank": 4},
    {"id": 5,  "title": "Aurora Waves",      "artist_id": 3, "album_id": 3, "genre": "Ambient",    "duration": "5:32", "emoji": "🌊", "plays": 812_650,  "chart_rank": 5},
    {"id": 6,  "title": "Solar Drift",       "artist_id": 3, "album_id": 3, "genre": "Ambient",    "duration": "4:35", "emoji": "☀️", "plays": 745_208,  "chart_rank": 6},
    {"id": 7,  "title": "Phantom Bass",      "artist_id": 4, "album_id": 4, "genre": "Bass",       "duration": "3:43", "emoji": "👻", "plays": 698_771,  "chart_rank": 7},
    {"id": 8,  "title": "Lost In Spectrum",  "artist_id": 4, "album_id": 4, "genre": "Bass",       "duration": "4:51", "emoji": "🌀", "plays": 655_340,  "chart_rank": 8},
    {"id": 9,  "title": "Crystal Echoes",    "artist_id": 5, "album_id": 5, "genre": "Electronic", "duration": "4:04", "emoji": "💎", "plays": 601_558,  "chart_rank": 9},
    {"id": 10, "title": "Fractured Light",   "artist_id": 5, "album_id": 5, "genre": "Electronic", "duration": "4:27", "emoji": "🔮", "plays": 587_902,  "chart_rank": 10},
    {"id": 11, "title": "Gravity Pull",      "artist_id": 6, "album_id": 6, "genre": "R&B",        "duration": "3:15", "emoji": "🌙", "plays": 402_337,  "chart_rank": None},
    {"id": 12, "title": "Velvet Sky",        "artist_id": 6, "album_id": 6, "genre": "R&B",        "duration": "3:48", "emoji": "🌙", "plays": 388_120,  "chart_rank": None},
    {"id": 13, "title": "Electric Soul",     "artist_id": 7, "album_id": 7, "genre": "Rock",       "duration": "3:29", "emoji": "⚡", "plays": 356_884,  "chart_rank": None},
    {"id": 14, "title": "Iron Cascade",      "artist_id": 7, "album_id": 7, "genre": "Rock",       "duration": "3:54", "emoji": "🎸", "plays": 344_501,  "chart_rank": None},
    {"id": 15, "title": "Lucid Morning",     "artist_id": 8, "album_id": 8, "genre": "Indie",      "duration": "4:02", "emoji": "🌿", "plays": 298_664,  "chart_rank": None},
    {"id": 16, "title": "Cafe au Lait",      "artist_id": 8, "album_id": 8, "genre": "Indie",      "duration": "3:36", "emoji": "☕", "plays": 287_310,  "chart_rank": None},
    {"id": 17, "title": "Stardust Protocol", "artist_id": 9, "album_id": 9, "genre": "Electronic", "duration": "4:21", "emoji": "✨", "plays": 265_990,  "chart_rank": None},
    {"id": 18, "title": "Binary Sunset",     "artist_id": 9, "album_id": 9, "genre": "Electronic", "duration": "3:58", "emoji": "🌅", "plays": 251_476,  "chart_rank": None},
    {"id": 19, "title": "Deep Frequencies",  "artist_id": 3, "album_id": 3, "genre": "Ambient",    "duration": "5:05", "emoji": "🌊", "plays": 244_803,  "chart_rank": None},
]

PLAYLISTS = [
    {"id": 1, "name": "Neon Afterglow",     "emoji": "🌃", "description": "Electric vibes for late nights",        "creator": "SonicWave", "song_ids": [1, 2, 3, 4, 9, 10], "mood": "energetic"},
    {"id": 2, "name": "Sunrise Sessions",   "emoji": "🌅", "description": "Wake up and feel alive",                "creator": "SonicWave", "song_ids": [6, 15, 16, 18, 5],  "mood": "happy"},
    {"id": 3, "name": "Deep Space Chill",   "emoji": "🚀", "description": "Float through the cosmos",              "creator": "You",       "song_ids": [5, 6, 19, 17, 9],   "mood": "calm"},
    {"id": 4, "name": "Underground Pulse",  "emoji": "🔊", "description": "Raw energy from the depths",            "creator": "You",       "song_ids": [7, 8, 2, 13, 14],   "mood": "energetic"},
    {"id": 5, "name": "Velvet Nights",      "emoji": "💜", "description": "Smooth R&B for slow moments",           "creator": "You",       "song_ids": [11, 12, 4, 16, 3],  "mood": "romantic"},
    {"id": 6, "name": "Focus Matrix",       "emoji": "🎯", "description": "Sharpen your mind, block out the noise","creator": "You",       "song_ids": [17, 18, 19, 5, 9],  "mood": "focus"},
]

# Mutable user state
LIKED_SONG_IDS = {3, 5, 8, 11, 14, 17}
QUEUE: list[int] = []

USER_STATS = {
    "songs_played": 1247,
    "hours_listened": 86,
    "top_genre": "Electronic",
    "favorite_artist": "Kai Nakamura",
}
