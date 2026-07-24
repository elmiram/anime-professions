"""Paths, constants, and credential loading. No secrets are ever logged."""
from __future__ import annotations
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = ROOT / "anime_professions.db"
ISCO_JSON = DATA_DIR / "isco08.json"
EXPORT_DIR = ROOT / "exports"

# Polite, honest User-Agent. We derive statistics only; we never redistribute text.
USER_AGENT = "anime-occupation-research/1.0 (non-redistributive research; contact: project owner)"

ANILIST_URL = "https://graphql.anilist.co"
ANILIST_MIN_INTERVAL = 0.7          # seconds between requests (~85/min, under the 90/min cap)
JIKAN_URL = "https://api.jikan.moe/v4"
JIKAN_MIN_INTERVAL = 1.1            # Jikan is fragile; be gentle. Best-effort only.

# Subtitle mirror (Layer C). Cloned locally; only counts + locators are ever persisted.
SUBTITLE_MIRROR_REPO = "https://github.com/Ajatt-Tools/kitsunekko-mirror.git"
SUBTITLE_MIRROR_DIR = ROOT / "subtitle_mirror"   # git-ignored; never committed

# Adjudication model. Haiku 4.5 via the Batch API (-50%).
ADJUDICATION_MODEL = "claude-haiku-4-5"

# Corpus rules (see PROJECT_PLAN.md §6). Formats excluded from the denominator.
DENOMINATOR_EXCLUDE_FORMATS = {"MUSIC"}   # AniList has no CM format; MUSIC == music video


def get_api_key() -> str | None:
    """ANTHROPIC_API_KEY env var, else api_key.txt in the project root. Never logged."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key.strip()
    f = ROOT / "api_key.txt"
    if f.exists():
        k = f.read_text(encoding="utf-8").strip()
        return k or None
    return None
