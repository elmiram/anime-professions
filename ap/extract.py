"""Stage 1 — high-recall lexicon candidate generation.

Scans synopsis text and character bios for lexicon surface forms. Casts wide and accepts
false positives; the Stage-2 adjudicator (extract -> adjudicate) resolves ambiguous ones.
One combined word-boundary regex (longest-match-first) keeps a full-corpus scan fast.

Only the matched TERM and a locator are recorded — never the surrounding line.
"""
from __future__ import annotations
import html
import re

from . import db
from .lexicon import LEXICON, FANTASY

# term(lowercased) -> list of (kind, key, ambiguous)
_TERMS: dict[str, list[tuple[str, str, bool]]] = {}
for _code, (_forms, _amb) in LEXICON.items():
    for _t in _forms:
        _TERMS.setdefault(_t.lower(), []).append(("isco", _code, _amb))
for _key, (_forms, _amb) in FANTASY.items():
    for _t in _forms:
        _TERMS.setdefault(_t.lower(), []).append(("fantasy", _key, _amb))

# Longest surface forms first so "software engineer" wins over any shorter overlap.
_ALT = sorted((re.escape(t) for t in _TERMS), key=len, reverse=True)
_PATTERN = re.compile(r"\b(" + "|".join(_ALT) + r")\b", re.IGNORECASE)

_TAG_RE = re.compile(r"<[^>]+>")          # AniList markup: <br>, <i> ...
_SPOILER_RE = re.compile(r"~!.*?!~", re.S)  # AniList spoiler blocks


def clean(text: str | None) -> str:
    if not text:
        return ""
    text = _SPOILER_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    return html.unescape(text)


def scan(text: str | None) -> list[tuple[str, str, str, bool]]:
    """Return distinct (kind, key, matched_term, ambiguous) tuples found in text."""
    seen = set()
    out = []
    for m in _PATTERN.finditer(clean(text)):
        term = m.group(1).lower()
        for kind, key, amb in _TERMS.get(term, ()):
            sig = (kind, key, term)
            if sig in seen:
                continue
            seen.add(sig)
            out.append((kind, key, term, amb))
    return out


def _add(rows, anime_id, char_id, kind, key, term, amb, source, locator):
    isco = key if kind == "isco" else None
    fant = key if kind == "fantasy" else None
    rows.append((anime_id, char_id, isco, fant, term, source, locator, int(amb)))


def generate_candidates(only_anime: list[int] | None = None) -> None:
    """(Re)build Stage-1 candidates for the given anime (or all). Deterministic + cheap,
    so it fully regenerates rather than trying to be incremental."""
    con = db.connect()
    where = ""
    params: tuple = ()
    if only_anime:
        qs = ",".join("?" * len(only_anime))
        where = f" WHERE anilist_id IN ({qs})"
        params = tuple(only_anime)

    # clear prior candidates (+ their adjudications) for the target scope
    if only_anime:
        con.execute(f"DELETE FROM adjudication WHERE candidate_id IN "
                    f"(SELECT candidate_id FROM candidate WHERE anime_id IN ({qs}))", params)
        con.execute(f"DELETE FROM candidate WHERE anime_id IN ({qs})", params)
    else:
        con.execute("DELETE FROM adjudication")
        con.execute("DELETE FROM candidate")
    con.commit()

    rows: list[tuple] = []
    # --- synopsis ---
    for aid, syn in con.execute(f"SELECT anilist_id, synopsis FROM anime{where}", params):
        for kind, key, term, amb in scan(syn):
            _add(rows, aid, None, kind, key, term, amb, "synopsis", "synopsis")

    # --- character bios (attribute to every anime the character appears in, in scope) ---
    ap_where = ""
    if only_anime:
        ap_where = f" WHERE ap.anime_id IN ({qs})"
    q = (f"SELECT ap.anime_id, c.char_id, c.name, c.description "
         f"FROM appearance ap JOIN character c ON c.char_id = ap.char_id{ap_where}")
    for aid, cid, name, desc in con.execute(q, params):
        hits = scan(desc)
        if not hits:
            continue
        loc = f"character:{name}" if name else f"character:{cid}"
        for kind, key, term, amb in hits:
            _add(rows, aid, cid, kind, key, term, amb, "character", loc)

    con.executemany(
        "INSERT INTO candidate(anime_id,char_id,isco_code,fantasy_key,term,source,locator,ambiguous) "
        "VALUES(?,?,?,?,?,?,?,?)", rows)
    con.commit()
    n_amb = sum(1 for r in rows if r[7])
    print(f"[extract] {len(rows)} candidates "
          f"({n_amb} ambiguous -> Stage 2, {len(rows)-n_amb} trusted)")
    con.close()
