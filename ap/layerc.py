"""Layer C — subtitle dialogue (Japanese), smart middle.

  build_title_map()  subtitle folder (romaji) -> AniList id
  scan()             write subtitle candidates: title-deduped for ALL occupations (counts),
                     plus per-episode for RARE occupations (evidence). Stores locator only
                     (relpath@timestamp) + matched term — NEVER the dialogue text.
  subtitle_sentence()  re-open ONE file at a locator and return the matched line in memory,
                     used only at adjudication time (text is never persisted).

Matching is JP substring (no tokenizer); the Stage-2 LLM adjudicator supplies precision.
"""
from __future__ import annotations
import re
import unicodedata
import json

from . import config, db, agg
from .jp_lexicon import JP_LEXICON, JP_FANTASY

RARE_THRESHOLD = 25          # occupations with <= this many L1-2 titles get per-episode evidence
_ASS_TS = None
_SRT_TS = re.compile(r"(\d\d):(\d\d):(\d\d)[,.]\d+\s*-->")

# term -> list of (kind, isco_or_fantasy_key, ambiguous)
_JP_TERMS: dict[str, list[tuple[str, str, bool]]] = {}
for _c, (_forms, _a) in JP_LEXICON.items():
    for _t in _forms:
        _JP_TERMS.setdefault(_t, []).append(("isco", _c, _a))
for _k, (_forms, _a) in JP_FANTASY.items():
    for _t in _forms:
        _JP_TERMS.setdefault(_t, []).append(("fantasy", _k, _a))
_JP_TERM_LIST = list(_JP_TERMS)


def _norm(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKC", s).lower())


def _strip_season(k: str) -> str:
    return re.sub(r"(2nd|3rd|\d+th|season|part|finalseason|\d+)+$", "", k)


def build_title_map() -> int:
    """Match subtitle folders to AniList ids via titles.json; store in subtitle_title."""
    titles = json.loads((config.DATA_DIR / "titles.json").read_text(encoding="utf-8"))
    idx = {}
    for aid, t in titles.items():
        for v in (t.get("romaji"), t.get("english"), t.get("native")):
            k = _norm(v)
            if k:
                idx.setdefault(k, int(aid))
                ks = _strip_season(k)
                if len(ks) > 4:
                    idx.setdefault(ks, int(aid))
    con = db.connect()
    con.execute("DELETE FROM subtitle_title")
    base = config.SUBTITLE_MIRROR_DIR / "subtitles"
    n = 0
    for cat in ("anime_tv", "anime_movie"):
        d = base / cat
        if not d.exists():
            continue
        for p in d.iterdir():
            if not p.is_dir():
                continue
            k = _norm(p.name)
            aid = idx.get(k) or idx.get(_strip_season(k))
            if aid:
                con.execute("INSERT OR REPLACE INTO subtitle_title(rel_dir,anime_id) VALUES(?,?)",
                            (f"{cat}/{p.name}", aid))
                n += 1
    con.commit(); con.close()
    print(f"[layerc] matched {n} subtitle titles to AniList ids")
    return n


def _parse_ts(path):
    """Yield (timestamp 'HH:MM:SS', text) pairs from an .srt/.ass file."""
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return
    if path.suffix.lower() in (".ass", ".ssa"):
        for line in raw.splitlines():
            if line.startswith("Dialogue:"):
                parts = line.split(",", 9)
                if len(parts) == 10:
                    ts = parts[1].strip().split(".")[0]           # H:MM:SS
                    txt = re.sub(r"\{[^}]*\}", "", parts[9]).replace("\\N", " ").strip()
                    if txt:
                        yield ts, txt
    else:
        cur = "00:00:00"
        for line in raw.splitlines():
            m = _SRT_TS.search(line)
            if m:
                cur = f"{m.group(1)}:{m.group(2)}:{m.group(3)}"; continue
            s = line.strip()
            if s and not s.isdigit():
                yield cur, s


def subtitle_sentence(locator: str, term: str) -> str:
    """Re-open the file at `locator` (relpath@ts) and return the matched line. In-memory only."""
    try:
        rel, ts = locator.rsplit("@", 1)
    except ValueError:
        return ""
    path = config.SUBTITLE_MIRROR_DIR / rel
    for t, txt in _parse_ts(path):
        if t == ts and term in txt:
            return txt[:400]
    # fallback: first line containing the term
    for _, txt in _parse_ts(path):
        if term in txt:
            return txt[:400]
    return ""


def scan(limit: int | None = None) -> None:
    """Write subtitle candidates: title-deduped for all occupations + per-episode for rare ones."""
    con = db.connect()
    con.execute("DELETE FROM adjudication WHERE candidate_id IN "
                "(SELECT candidate_id FROM candidate WHERE source='subtitle')")
    con.execute("DELETE FROM candidate WHERE source='subtitle'")
    con.commit()

    # rare occupations = few titles in Layers 1-2
    l12 = agg.occupation_counts(con, "franchise")
    rare = {code for (kind, code), v in l12.items()
            if kind == "isco" and v["count"] <= RARE_THRESHOLD}

    rows = con.execute("SELECT rel_dir, anime_id FROM subtitle_title"
                       + (f" LIMIT {int(limit)}" if limit else "")).fetchall()
    print(f"[layerc] scanning {len(rows)} matched titles ...", flush=True)
    base = config.SUBTITLE_MIRROR_DIR / "subtitles"
    inserts = []
    done = 0
    for rel_dir, aid in rows:
        tdir = base / rel_dir
        if not tdir.exists():
            continue
        # per (kind,key): representative (locator, term); and for rare, all episode occurrences
        seen_title: dict = {}
        rare_eps: list = []
        for f in tdir.rglob("*"):
            if f.suffix.lower() not in (".srt", ".ass", ".ssa"):
                continue
            relf = f.relative_to(config.SUBTITLE_MIRROR_DIR).as_posix()
            ep_seen = set()
            for ts, txt in _parse_ts(f):
                for term in _JP_TERM_LIST:
                    if term in txt:
                        for kind, key, amb in _JP_TERMS[term]:
                            loc = f"{relf}@{ts}"
                            if (kind, key) not in seen_title:
                                seen_title[(kind, key)] = (term, loc, amb)
                            if kind == "isco" and key in rare and (kind, key, relf) not in ep_seen:
                                ep_seen.add((kind, key, relf))
                                rare_eps.append((kind, key, term, loc, amb))
        # title-dedup candidates (all occupations)
        for (kind, key), (term, loc, amb) in seen_title.items():
            isco = key if kind == "isco" else None
            fant = key if kind == "fantasy" else None
            inserts.append((aid, None, isco, fant, term, "subtitle", loc, int(amb)))
        # per-episode candidates for rare occupations (skip the one already added as representative)
        for kind, key, term, loc, amb in rare_eps:
            if seen_title.get((kind, key), (None, None, None))[1] == loc:
                continue
            isco = key if kind == "isco" else None
            fant = key if kind == "fantasy" else None
            inserts.append((aid, None, isco, fant, term, "subtitle", loc, int(amb)))
        done += 1
        if done % 500 == 0:
            con.executemany("INSERT INTO candidate(anime_id,char_id,isco_code,fantasy_key,term,"
                            "source,locator,ambiguous) VALUES(?,?,?,?,?,?,?,?)", inserts)
            con.commit(); inserts = []
            sofar = con.execute("SELECT COUNT(*) FROM candidate WHERE source='subtitle'").fetchone()[0]
            print(f"  ...{done}/{len(rows)} titles, {sofar} subtitle candidates", flush=True)
    if inserts:
        con.executemany("INSERT INTO candidate(anime_id,char_id,isco_code,fantasy_key,term,"
                        "source,locator,ambiguous) VALUES(?,?,?,?,?,?,?,?)", inserts)
        con.commit()
    tot = con.execute("SELECT COUNT(*) FROM candidate WHERE source='subtitle'").fetchone()[0]
    amb = con.execute("SELECT COUNT(*) FROM candidate WHERE source='subtitle' AND ambiguous=1").fetchone()[0]
    print(f"[layerc] scan done: {tot} subtitle candidates ({amb} ambiguous, {tot-amb} trusted)")
    con.close()
