"""Local web explorer for the anime-professions dataset.

Stdlib HTTP server + SQLite JSON API; a self-contained vanilla-JS SPA (web/index.html)
renders the charts with inline SVG (no external dependencies, works offline). Read-only.

    python ap.py web        # -> http://127.0.0.1:8000
"""
from __future__ import annotations
import json
import sqlite3
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from . import config, agg, taxonomy
from .lexicon import FANTASY

PROM_LABEL = {3: "protagonist", 2: "recurring", 1: "incidental", 0: "unknown"}

# confirmed-hit base (candidate that the adjudicator said 'yes')
_CONF = ("candidate c JOIN adjudication a ON a.candidate_id=c.candidate_id AND a.verdict='yes' "
         "JOIN anime an ON an.anilist_id=c.anime_id")
_PROM = ("CASE WHEN c.source='synopsis' THEN 3 WHEN ap.role='MAIN' THEN 3 "
         "WHEN ap.role='SUPPORTING' THEN 2 WHEN ap.role='BACKGROUND' THEN 1 ELSE 0 END")


def _con():
    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row
    return con


class Cache:
    """Computed once at startup (the DB is static after analysis)."""
    def __init__(self):
        con = _con()
        self.dens = agg.denominators(con)
        self.counts = agg.occupation_counts(con, "franchise")
        self.pr = {r["isco_code"]: r for r in con.execute("SELECT * FROM precision_recall")}
        self.confirmed = con.execute(
            "SELECT COUNT(*) FROM adjudication WHERE verdict='yes'").fetchone()[0]
        self.total_anime = con.execute("SELECT COUNT(*) FROM anime").fetchone()[0]
        self.characters = con.execute("SELECT COUNT(*) FROM character").fetchone()[0]
        self.franchises = con.execute(
            "SELECT COUNT(DISTINCT franchise_id) FROM anime").fetchone()[0]
        # corpus per decade (denominator)
        self.corpus_decade = {int(d): n for d, n in con.execute(
            "SELECT (year/10)*10 d, COUNT(DISTINCT franchise_id) FROM anime "
            "WHERE in_denominator=1 AND year IS NOT NULL GROUP BY d")}
        con.close()

    def occ_list(self):
        N = self.dens["with_scannable_text"] or 1
        out = []
        for u in taxonomy.all_units():
            code = u["code"]
            v = self.counts.get(("isco", code), {"count": 0, "prominence": {}})
            pr = self.pr.get(code)
            out.append({
                "kind": "isco", "key": code, "title": u["title"],
                "major": taxonomy.rollup(code)["major_title"],
                "count": v["count"], "pct": round(100 * v["count"] / N, 3),
                "renderable": taxonomy.is_renderable(code),
                "reliable": (None if not pr else bool(pr["reliable"])),
                "precision": (pr["precision"] if pr else None),
                "recall": (pr["recall"] if pr else None),
                "prominence": v["prominence"], "stratum": "real",
            })
        for key in FANTASY:
            v = self.counts.get(("fantasy", key), {"count": 0, "prominence": {}})
            out.append({
                "kind": "fantasy", "key": key, "title": key.replace("_", " "),
                "major": "Fantasy stratum", "count": v["count"],
                "pct": round(100 * v["count"] / N, 3), "renderable": True,
                "reliable": None, "precision": None, "recall": None,
                "prominence": v["prominence"], "stratum": "fantasy",
            })
        out.sort(key=lambda r: -r["count"])
        return out


CACHE: Cache | None = None


# ---------------------------------------------------------------- API handlers
def api_summary():
    N = CACHE.dens["with_scannable_text"]
    occ = CACHE.occ_list()
    real = [o for o in occ if o["stratum"] == "real"]
    fan = [o for o in occ if o["stratum"] == "fantasy"]
    renderable = [o for o in real if o["renderable"]]
    return {
        "anime": CACHE.total_anime,
        "denominator": CACHE.dens["all_in_denominator"],
        "scannable": N, "confirmed_hits": CACHE.confirmed,
        "characters": CACHE.characters, "franchises": CACHE.franchises,
        "renderable": len(renderable),
        "zero_renderable": sum(1 for o in renderable if o["count"] == 0),
        "top_real": real[:12], "top_fantasy": fan[:12],
        "zero_list": [o for o in renderable if o["count"] == 0],
    }


def api_occupations(qs):
    q = (qs.get("q", [""])[0] or "").lower().strip()
    stratum = qs.get("stratum", ["all"])[0]
    occ = CACHE.occ_list()
    if stratum in ("real", "fantasy"):
        occ = [o for o in occ if o["stratum"] == stratum]
    if q:
        occ = [o for o in occ if q in o["title"].lower() or q in o["key"].lower()]
    return {"denominator": CACHE.dens["with_scannable_text"], "occupations": occ}


def _decades(con, kind, key):
    col = "isco_code" if kind == "isco" else "fantasy_key"
    rows = con.execute(
        f"SELECT (an.year/10)*10 d, COUNT(DISTINCT an.franchise_id) n FROM {_CONF} "
        f"WHERE c.{col}=? AND an.year IS NOT NULL GROUP BY d ORDER BY d", (key,)).fetchall()
    out = []
    for r in rows:
        dec = int(r["d"]); corp = CACHE.corpus_decade.get(dec, 0)
        out.append({"decade": dec, "count": r["n"],
                    "pct": round(100 * r["n"] / corp, 2) if corp else 0})
    return out


def api_occupation(qs):
    kind = qs.get("kind", ["isco"])[0]
    key = qs.get("key", [""])[0]
    con = _con()
    col = "isco_code" if kind == "isco" else "fantasy_key"
    # source breakdown
    src = {r["source"]: r["n"] for r in con.execute(
        f"SELECT c.source, COUNT(*) n FROM {_CONF} WHERE c.{col}=? GROUP BY c.source", (key,))}
    # title list (per anime, best prominence, merged sources, max confidence)
    rows = con.execute(f"""
        SELECT an.title, an.anilist_id, an.mal_id, an.year, an.format, an.popularity,
               MAX(a.confidence) conf, GROUP_CONCAT(DISTINCT c.source) sources,
               MAX({_PROM}) prom
        FROM {_CONF} LEFT JOIN appearance ap ON ap.anime_id=c.anime_id AND ap.char_id=c.char_id
        WHERE c.{col}=? GROUP BY an.anilist_id ORDER BY an.popularity DESC LIMIT 500
    """, (key,)).fetchall()
    titles = [{"title": r["title"], "anilist_id": r["anilist_id"], "mal_id": r["mal_id"],
               "year": r["year"], "format": r["format"],
               "prominence": PROM_LABEL[r["prom"]], "sources": r["sources"],
               "confidence": round(r["conf"] or 0, 2)} for r in rows]
    info = next((o for o in CACHE.occ_list() if o["kind"] == kind and o["key"] == key), {})
    dec = _decades(con, kind, key)
    con.close()
    return {"info": info, "sources": src, "decades": dec, "titles": titles,
            "rollup": (taxonomy.rollup(key) if kind == "isco" else None)}


def api_anime_search(qs):
    q = (qs.get("q", [""])[0] or "").strip()
    if len(q) < 2:
        return {"results": []}
    con = _con()
    rows = con.execute(
        "SELECT anilist_id, title, year, format, popularity FROM anime "
        "WHERE title LIKE ? ORDER BY popularity DESC LIMIT 40", (f"%{q}%",)).fetchall()
    con.close()
    return {"results": [dict(r) for r in rows]}


def api_anime(qs):
    aid = qs.get("id", ["0"])[0]
    con = _con()
    a = con.execute("SELECT * FROM anime WHERE anilist_id=?", (aid,)).fetchone()
    if not a:
        con.close(); return {"error": "not found"}
    rows = con.execute(f"""
        SELECT c.isco_code, c.fantasy_key,
               GROUP_CONCAT(DISTINCT c.source) sources, MAX(a.confidence) conf,
               MAX({_PROM}) prom
        FROM {_CONF} LEFT JOIN appearance ap ON ap.anime_id=c.anime_id AND ap.char_id=c.char_id
        WHERE c.anime_id=? GROUP BY c.isco_code, c.fantasy_key
    """, (aid,)).fetchall()
    occs = []
    for r in rows:
        if r["isco_code"]:
            occs.append({"stratum": "real", "code": r["isco_code"],
                         "title": taxonomy.title(r["isco_code"]),
                         "sources": r["sources"], "prominence": PROM_LABEL[r["prom"]],
                         "confidence": round(r["conf"] or 0, 2)})
        else:
            occs.append({"stratum": "fantasy", "code": r["fantasy_key"],
                         "title": r["fantasy_key"].replace("_", " "),
                         "sources": r["sources"], "prominence": PROM_LABEL[r["prom"]],
                         "confidence": round(r["conf"] or 0, 2)})
    occs.sort(key=lambda o: (o["stratum"], -o["confidence"]))
    con.close()
    return {"anime": {k: a[k] for k in ("anilist_id", "mal_id", "title", "year", "format",
                                        "episodes", "popularity")}, "occupations": occs}


def api_trends(qs):
    kind = qs.get("kind", ["isco"])[0]
    keys = [k for k in qs.get("keys", [""])[0].split(",") if k]
    con = _con()
    series = []
    for key in keys[:6]:
        title = taxonomy.title(key) if kind == "isco" else key.replace("_", " ")
        series.append({"key": key, "title": title, "points": _decades(con, kind, key)})
    con.close()
    decades = sorted(CACHE.corpus_decade)
    return {"decades": decades, "series": series}


def api_decade_top(qs):
    n = int(qs.get("n", ["6"])[0])
    stratum = qs.get("stratum", ["real"])[0]      # real | fantasy
    col = "isco_code" if stratum == "real" else "fantasy_key"
    con = _con()
    rows = con.execute(
        f"SELECT (an.year/10)*10 dec, c.{col} k, COUNT(DISTINCT an.franchise_id) n "
        f"FROM {_CONF} WHERE c.{col} IS NOT NULL AND an.year IS NOT NULL "
        f"GROUP BY dec, c.{col}").fetchall()
    con.close()
    by = {}
    for r in rows:
        dec = int(r["dec"])
        if CACHE.corpus_decade.get(dec, 0) < 10:   # skip tiny early decades
            continue
        corp = CACHE.corpus_decade.get(dec, 0)
        title = taxonomy.title(r["k"]) if stratum == "real" else r["k"].replace("_", " ")
        by.setdefault(dec, []).append({
            "kind": "isco" if stratum == "real" else "fantasy", "key": r["k"], "title": title,
            "count": r["n"], "pct": round(100 * r["n"] / corp, 2) if corp else 0})
    out = {str(d): sorted(v, key=lambda x: -x["count"])[:n] for d, v in by.items()}
    return {"stratum": stratum, "decades": sorted(int(d) for d in out), "by_decade": out}


ROUTES = {
    "/api/summary": lambda qs: api_summary(),
    "/api/decade_top": api_decade_top,
    "/api/occupations": api_occupations,
    "/api/occupation": api_occupation,
    "/api/anime/search": api_anime_search,
    "/api/anime": api_anime,
    "/api/trends": api_trends,
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")   # always serve fresh
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ROUTES:
            try:
                data = ROUTES[u.path](parse_qs(u.query))
                self._send(200, json.dumps(data).encode(), "application/json")
            except Exception as e:
                self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")
            return
        if u.path in ("/", "/index.html"):
            html = (config.ROOT / "web" / "index.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
            return
        self._send(404, b"not found", "text/plain")


def serve(port: int = 8000):
    global CACHE
    print("[web] building cache ...")
    CACHE = Cache()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"[web] anime-professions explorer -> http://127.0.0.1:{port}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[web] stopped")
