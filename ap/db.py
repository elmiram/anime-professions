"""SQLite schema (the source of truth) + resumable-collection checkpoints.

Design notes:
  * `candidate` holds Stage-1 lexicon hits; each is real (isco_code) XOR fantasy (fantasy_key).
  * `adjudication` holds Stage-2 verdicts; unambiguous candidates get a synthetic trusted
    verdict without an LLM call.
  * NOTHING here stores subtitle text. `candidate.locator` is a pointer (episode/timestamp
    or "synopsis"/"character:<name>"); `candidate.term` is the matched surface form only.
  * `checkpoint` makes every long collection resumable — re-running never re-fetches.
"""
from __future__ import annotations
import sqlite3
from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS anime (
    anilist_id     INTEGER PRIMARY KEY,
    mal_id         INTEGER,
    title          TEXT,
    title_native   TEXT,
    format         TEXT,       -- TV, MOVIE, OVA, ONA, SPECIAL, MUSIC, TV_SHORT
    year           INTEGER,
    episodes       INTEGER,
    popularity     INTEGER,
    favourites     INTEGER,
    avg_score      INTEGER,
    country        TEXT,
    source_material TEXT,
    genres         TEXT,       -- json array
    synopsis       TEXT,       -- AniList description (public blurb; scanned, not redistributed as corpus)
    franchise_id   INTEGER,    -- assigned by the franchise-clustering step
    in_denominator INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS relation (
    source_id      INTEGER,
    target_id      INTEGER,
    relation_type  TEXT,
    PRIMARY KEY (source_id, target_id, relation_type)
);

CREATE TABLE IF NOT EXISTS character (
    char_id        INTEGER PRIMARY KEY,
    name           TEXT,
    description    TEXT        -- scanned for occupation mentions; not part of any export
);

CREATE TABLE IF NOT EXISTS appearance (
    anime_id       INTEGER,
    char_id        INTEGER,
    role           TEXT,       -- MAIN / SUPPORTING / BACKGROUND
    PRIMARY KEY (anime_id, char_id)
);

CREATE TABLE IF NOT EXISTS tag (   -- ground truth for scoring the text pipeline
    anime_id       INTEGER,
    name           TEXT,
    rank           INTEGER,
    category       TEXT,
    is_spoiler     INTEGER,
    PRIMARY KEY (anime_id, name)
);

CREATE TABLE IF NOT EXISTS candidate (   -- Stage 1: lexicon hits
    candidate_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    anime_id       INTEGER NOT NULL,
    char_id        INTEGER,             -- set when source='character'
    isco_code      TEXT,                -- real occupation (XOR fantasy_key)
    fantasy_key    TEXT,                -- fantasy stratum (XOR isco_code)
    term           TEXT NOT NULL,       -- matched surface form (NOT the surrounding line)
    source         TEXT NOT NULL,       -- synopsis / character / subtitle / tag
    locator        TEXT NOT NULL,       -- 'synopsis' | 'character:<name>' | 'epNN@HH:MM:SS'
    ambiguous      INTEGER NOT NULL     -- 1 -> needs Stage-2 adjudication
);

CREATE TABLE IF NOT EXISTS adjudication (   -- Stage 2: verdicts (text never stored)
    candidate_id   INTEGER PRIMARY KEY,
    verdict        TEXT,      -- yes / no
    real_or_fantasy TEXT,     -- real / fantasy / na
    prominence     TEXT,      -- protagonist / recurring / incidental / unknown
    confidence     REAL,
    model          TEXT,      -- e.g. claude-haiku-4-5, or 'trusted' for unambiguous
    FOREIGN KEY (candidate_id) REFERENCES candidate(candidate_id)
);

CREATE TABLE IF NOT EXISTS gold_label (   -- for precision/recall measurement
    candidate_id   INTEGER PRIMARY KEY,
    gold_holds     TEXT,      -- yes / no
    source         TEXT       -- 'manual' or 'model-assisted:<model>'
);

CREATE TABLE IF NOT EXISTS precision_recall (
    isco_code      TEXT PRIMARY KEY,
    precision      REAL,
    recall         REAL,
    n_labeled      INTEGER,
    reliable       INTEGER    -- 1 if precision >= floor
);

CREATE TABLE IF NOT EXISTS subtitle_title (   -- Layer C: subtitle folder -> AniList id
    rel_dir        TEXT PRIMARY KEY,   -- 'anime_tv/<Title>'
    anime_id       INTEGER
);

CREATE TABLE IF NOT EXISTS checkpoint (
    key            TEXT PRIMARY KEY,
    value          TEXT
);

CREATE INDEX IF NOT EXISTS idx_candidate_anime ON candidate(anime_id);
CREATE INDEX IF NOT EXISTS idx_candidate_isco  ON candidate(isco_code);
CREATE INDEX IF NOT EXISTS idx_candidate_amb   ON candidate(ambiguous);
CREATE INDEX IF NOT EXISTS idx_appearance_anime ON appearance(anime_id);
CREATE INDEX IF NOT EXISTS idx_relation_source ON relation(source_id);
"""


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(config.DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    return con


def get_ckpt(con: sqlite3.Connection, key: str, default=None):
    row = con.execute("SELECT value FROM checkpoint WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_ckpt(con: sqlite3.Connection, key: str, value) -> None:
    con.execute(
        "INSERT INTO checkpoint(key, value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
    con.commit()
