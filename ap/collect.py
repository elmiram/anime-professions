"""Collection: AniList media (corpus) + tags (ground truth) + relations (franchise)
+ characters/appearances (Layer 2). One media page carries all of it.

Resumable: the checkpoint 'anilist_page' records the last fully-committed page. Re-running
resumes there; upserts are idempotent, so a re-fetch never duplicates.
"""
from __future__ import annotations
import json

from . import anilist, config, db

FRANCHISE_RELATIONS = {
    "PREQUEL", "SEQUEL", "PARENT", "SIDE_STORY", "SUMMARY",
    "ALTERNATIVE", "SPIN_OFF", "COMPILATION", "CONTAINS",
}


def _title(t: dict) -> str:
    return t.get("english") or t.get("romaji") or t.get("native") or "?"


def _upsert_media(con, m: dict) -> None:
    fmt = m.get("format")
    in_denom = 0 if fmt in config.DENOMINATOR_EXCLUDE_FORMATS else 1
    con.execute(
        """INSERT OR REPLACE INTO anime
           (anilist_id, mal_id, title, title_native, format, year, episodes,
            popularity, favourites, avg_score, country, source_material, genres,
            synopsis, franchise_id, in_denominator)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                   (SELECT franchise_id FROM anime WHERE anilist_id=?), ?)""",
        (m["id"], m.get("idMal"), _title(m["title"]), m["title"].get("native"), fmt,
         (m.get("startDate") or {}).get("year"), m.get("episodes"), m.get("popularity"),
         m.get("favourites"), m.get("averageScore"), m.get("countryOfOrigin"),
         m.get("source"), json.dumps(m.get("genres") or []), m.get("description"),
         m["id"], in_denom),
    )
    # tags (ground truth)
    con.execute("DELETE FROM tag WHERE anime_id=?", (m["id"],))
    con.executemany(
        "INSERT OR IGNORE INTO tag(anime_id,name,rank,category,is_spoiler) VALUES(?,?,?,?,?)",
        [(m["id"], t["name"], t.get("rank"), t.get("category"), int(bool(t.get("isMediaSpoiler"))))
         for t in (m.get("tags") or [])],
    )
    # relations (for franchise clustering) — anime nodes only
    con.executemany(
        "INSERT OR IGNORE INTO relation(source_id,target_id,relation_type) VALUES(?,?,?)",
        [(m["id"], e["node"]["id"], e["relationType"])
         for e in (m.get("relations") or {}).get("edges", [])
         if e.get("node") and e["node"].get("type") == "ANIME"],
    )
    # characters + appearances (Layer 2)
    for e in (m.get("characters") or {}).get("edges", []):
        node = e["node"]
        con.execute("INSERT OR REPLACE INTO character(char_id,name,description) VALUES(?,?,?)",
                    (node["id"], (node.get("name") or {}).get("full"), node.get("description")))
        con.execute("INSERT OR REPLACE INTO appearance(anime_id,char_id,role) VALUES(?,?,?)",
                    (m["id"], node["id"], e.get("role")))


def collect_corpus(sample: int | None = None, per_page: int = 50, char_per_page: int = 25,
                   restart: bool = False, year_from: int = 1900, year_to: int = 2027) -> None:
    con = db.connect()

    # --- sample mode: first page(s), no year filter (for the end-to-end test) ---
    if sample:
        if restart:
            db.set_ckpt(con, "anilist_page", 0)
        page = int(db.get_ckpt(con, "anilist_page", 0)) + 1
        while True:
            p = anilist.media_page(page, per_page=per_page, char_per_page=char_per_page)
            for m in p["media"]:
                _upsert_media(con, m)
            con.commit(); db.set_ckpt(con, "anilist_page", page)
            total = con.execute("SELECT COUNT(*) FROM anime").fetchone()[0]
            print(f"  page {page}: +{len(p['media'])} (corpus={total})")
            if total >= sample:
                print(f"[collect] sample cap {sample} reached."); break
            if not p["pageInfo"]["hasNextPage"] or not p["media"]:
                break
            page += 1
        con.close(); return

    # --- full mode: chunk by start-year window (AniList caps offset at 5000/window) ---
    if restart:
        db.set_ckpt(con, "collect_year", 0); db.set_ckpt(con, "collect_page", 0)
    cy = int(db.get_ckpt(con, "collect_year", 0))
    cp = int(db.get_ckpt(con, "collect_page", 0))
    start_year = cy if cy else year_from
    got = con.execute("SELECT COUNT(*) FROM anime").fetchone()[0]
    print(f"[collect] full: resuming at year {start_year} page {cp+1 if cy else 1} (have {got})")

    for year in range(start_year, year_to + 1):
        page = (cp + 1) if (year == cy and cp) else 1
        while True:
            p = anilist.media_page(page, per_page=per_page, char_per_page=char_per_page, year=year)
            media = p["media"]
            for m in media:
                _upsert_media(con, m)
            con.commit()
            db.set_ckpt(con, "collect_year", year); db.set_ckpt(con, "collect_page", page)
            if media:
                total = con.execute("SELECT COUNT(*) FROM anime").fetchone()[0]
                print(f"  {year} p{page}: +{len(media)} (corpus={total})", flush=True)
            if not p["pageInfo"]["hasNextPage"] or not media:
                break
            page += 1
    total = con.execute("SELECT COUNT(*) FROM anime").fetchone()[0]
    print(f"[collect] full done: {total} anime across {year_from}-{year_to}")
    con.close()


def assign_franchises() -> None:
    """Union-find over franchise-type relations among collected anime -> franchise_id.
    Fuzzy by nature (see PROJECT_PLAN.md §6); every entry still keeps its own row."""
    con = db.connect()
    ids = [r[0] for r in con.execute("SELECT anilist_id FROM anime")]
    idset = set(ids)
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)   # deterministic: smallest id is the root

    for s, t, rt in con.execute("SELECT source_id,target_id,relation_type FROM relation"):
        if rt in FRANCHISE_RELATIONS and s in idset and t in idset:
            union(s, t)
    for i in ids:
        con.execute("UPDATE anime SET franchise_id=? WHERE anilist_id=?", (find(i), i))
    con.commit()
    n_fr = len({find(i) for i in ids})
    print(f"[franchise] {len(ids)} entries -> {n_fr} franchises")
    con.close()
