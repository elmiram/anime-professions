"""Export the three CSVs from SQLite (the source of truth).

  occupation_counts.csv  one row per ISCO unit group (incl. zeros) + fantasy rows,
                         stratum-tagged so fantasy is never summed into ISCO.
  title_occupation.csv   one row per (title x occupation) — the main lookup artifact.
  evidence.csv           one row per confirmed match: matched term + locator only,
                         NEVER the surrounding line (no redistributable text).
"""
from __future__ import annotations
import csv

from . import agg, config, db, taxonomy
from .lexicon import LEXICON, FANTASY


def _pr(con):
    return {code: (p, r, n, rel) for code, p, r, n, rel in
            con.execute("SELECT isco_code,precision,recall,n_labeled,reliable FROM precision_recall")}


def export_all(count_mode: str = "franchise") -> None:
    config.EXPORT_DIR.mkdir(exist_ok=True)
    con = db.connect()
    dens = agg.denominators(con)
    N = dens["with_scannable_text"] or 1
    counts = agg.occupation_counts(con, count_mode)
    pr = _pr(con)

    # ---- occupation_counts.csv ----
    path = config.EXPORT_DIR / "occupation_counts.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["stratum", "isco_code", "occupation", "renderable", "title_count",
                    "pct_of_scannable_corpus", "denominator_scannable", "denominator_all",
                    "protagonist", "recurring", "incidental", "unknown_prominence",
                    "precision", "recall", "n_labeled", "reliable", "note"])
        # every ISCO unit group, including zeros
        for u in taxonomy.all_units():
            code = u["code"]
            v = counts.get(("isco", code), {"count": 0, "prominence": {}})
            prom = v["prominence"]
            p, r, n, rel = pr.get(code, ("", "", "", ""))
            w.writerow(["real", code, u["title"], int(taxonomy.is_renderable(code)), v["count"],
                        round(100 * v["count"] / N, 4), N, dens["all_in_denominator"],
                        prom.get("protagonist", 0), prom.get("recurring", 0),
                        prom.get("incidental", 0), prom.get("unknown", 0),
                        p, r, n, rel, taxonomy.note(code) or ""])
        # fantasy stratum rows (kept separate)
        for key in FANTASY:
            v = counts.get(("fantasy", key), {"count": 0, "prominence": {}})
            prom = v["prominence"]
            w.writerow(["fantasy", "", key.replace("_", " "), 1, v["count"],
                        round(100 * v["count"] / N, 4), N, dens["all_in_denominator"],
                        prom.get("protagonist", 0), prom.get("recurring", 0),
                        prom.get("incidental", 0), prom.get("unknown", 0),
                        "", "", "", "", "ambiguous real/fantasy" if FANTASY[key][1] else ""])

    # ---- title_occupation.csv (main artifact) ----
    path2 = config.EXPORT_DIR / "title_occupation.csv"
    with open(path2, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["title", "anilist_id", "mal_id", "year", "format", "episodes",
                    "stratum", "occupation", "isco_code", "prominence", "sources",
                    "confidence", "franchise_id"])
        for row in agg.title_occupation_rows(con):
            if row["occ_kind"] == "isco":
                occ, isco, stratum = taxonomy.title(row["occ_key"]), row["occ_key"], "real"
            else:
                occ, isco, stratum = row["occ_key"].replace("_", " "), "", "fantasy"
            w.writerow([row["title"], row["anime_id"], row["mal_id"], row["year"], row["format"],
                        row["episodes"], stratum, occ, isco, row["best_prom"],
                        "|".join(sorted(row["sources"])), round(row["max_conf"], 3),
                        row["franchise_id"]])

    # ---- evidence.csv (term + locator only) ----
    path3 = config.EXPORT_DIR / "evidence.csv"
    with open(path3, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["title", "anilist_id", "stratum", "occupation", "isco_code",
                    "matched_term", "source", "locator", "confidence"])
        for h in agg.confirmed_hits(con):
            if h["isco_code"]:
                occ, isco, stratum = taxonomy.title(h["isco_code"]), h["isco_code"], "real"
            else:
                occ, isco, stratum = h["fantasy_key"].replace("_", " "), "", "fantasy"
            w.writerow([h["title"], h["anime_id"], stratum, occ, isco, h["term"],
                        h["source"], h["locator"], round(h["confidence"] or 0.0, 3)])

    con.close()
    print(f"[export] wrote:\n  {path}\n  {path2}\n  {path3}")
