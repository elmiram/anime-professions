"""Shared aggregation over confirmed hits, used by analyse and export.

A confirmed hit = a candidate whose adjudication verdict is 'yes' (ambiguous candidates
that the LLM confirmed, plus unambiguous 'trusted' candidates). Prominence is derived
here from source + character role (data-driven, not an LLM guess):
  synopsis            -> protagonist (premise/lead)
  character MAIN      -> protagonist
  character SUPPORTING-> recurring
  character BACKGROUND-> incidental
"""
from __future__ import annotations
from . import db, taxonomy
from .lexicon import LEXICON, FANTASY

PROMINENCE_RANK = {"protagonist": 3, "recurring": 2, "incidental": 1, "unknown": 0}

_PROMINENCE_SQL = """
    CASE
      WHEN c.source='synopsis' THEN 'protagonist'
      WHEN ap.role='MAIN' THEN 'protagonist'
      WHEN ap.role='SUPPORTING' THEN 'recurring'
      WHEN ap.role='BACKGROUND' THEN 'incidental'
      ELSE 'unknown'
    END"""

_CONFIRMED = f"""
    SELECT c.anime_id, an.franchise_id, an.title, an.mal_id, an.year, an.format,
           an.episodes, c.isco_code, c.fantasy_key, c.source, c.term, c.locator,
           adj.confidence, {_PROMINENCE_SQL} AS prominence
    FROM candidate c
    JOIN adjudication adj ON adj.candidate_id = c.candidate_id AND adj.verdict='yes'
    JOIN anime an ON an.anilist_id = c.anime_id
    LEFT JOIN appearance ap ON ap.anime_id = c.anime_id AND ap.char_id = c.char_id
"""


def confirmed_hits(con):
    """Yield dict rows for every confirmed candidate (the evidence grain)."""
    cols = ["anime_id", "franchise_id", "title", "mal_id", "year", "format", "episodes",
            "isco_code", "fantasy_key", "source", "term", "locator", "confidence", "prominence"]
    for r in con.execute(_CONFIRMED):
        yield dict(zip(cols, r))


def denominators(con) -> dict:
    total = con.execute("SELECT COUNT(*) FROM anime WHERE in_denominator=1").fetchone()[0]
    with_text = con.execute("""
        SELECT COUNT(*) FROM anime an WHERE in_denominator=1 AND (
            (synopsis IS NOT NULL AND synopsis!='') OR EXISTS(
                SELECT 1 FROM appearance ap JOIN character c ON c.char_id=ap.char_id
                WHERE ap.anime_id=an.anilist_id AND c.description IS NOT NULL AND c.description!=''))
    """).fetchone()[0]
    return {"all_in_denominator": total, "with_scannable_text": with_text}


def title_occupation_rows(con):
    """One row per (anime x occupation): best prominence, max confidence, merged sources."""
    agg: dict = {}
    for h in confirmed_hits(con):
        occ = ("isco", h["isco_code"]) if h["isco_code"] else ("fantasy", h["fantasy_key"])
        key = (h["anime_id"], occ)
        cur = agg.get(key)
        if cur is None:
            cur = {**h, "occ_kind": occ[0], "occ_key": occ[1], "sources": set(), "terms": set(),
                   "best_prom": "unknown", "max_conf": 0.0}
            agg[key] = cur
        cur["sources"].add(h["source"])
        cur["terms"].add(h["term"])
        if PROMINENCE_RANK[h["prominence"]] > PROMINENCE_RANK[cur["best_prom"]]:
            cur["best_prom"] = h["prominence"]
        cur["max_conf"] = max(cur["max_conf"], h["confidence"] or 0.0)
    return list(agg.values())


def occupation_counts(con, count_mode: str = "franchise"):
    """Per occupation: title count under the chosen count mode, prominence breakdown.
    Returns {(kind,key): {count, prominence_counts}}. count_mode: 'franchise' | 'entry'."""
    unit_field = "franchise_id" if count_mode == "franchise" else "anime_id"
    counts: dict = {}
    for row in title_occupation_rows(con):
        k = (row["occ_kind"], row["occ_key"])
        c = counts.setdefault(k, {"units": set(), "prominence": {}})
        c["units"].add(row[unit_field])
        c["prominence"][row["best_prom"]] = c["prominence"].get(row["best_prom"], 0) + 1
    return {k: {"count": len(v["units"]), "prominence": v["prominence"]} for k, v in counts.items()}
