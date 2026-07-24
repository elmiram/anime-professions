"""Precompute the whole explorer into a static `site/` folder for GitHub Pages.

The dataset is frozen, so every API response is deterministic. We generate them by
calling the webapp's own API functions (so shapes match exactly), then inject a small
client-side shim into index.html that answers the same /api/* calls from these files —
the frontend code is otherwise untouched. No server, no DB shipped (only derived stats +
titles + AniList ids; never subtitle text).
"""
from __future__ import annotations
import json
import shutil

from . import config, webapp

SHIM = """<script>
window.STATIC=true;
window.STATIC_FETCH=(function(){
  var cache={};
  function load(f){ if(!cache[f]) cache[f]=fetch(f).then(function(r){return r.json();}); return cache[f]; }
  return async function(url){
    var parts=url.split('?'), p=parts[0], q=new URLSearchParams(parts[1]||'');
    if(p==='/api/summary') return load('data/summary.json');
    if(p==='/api/decade_top') return load('data/decade_top_'+(q.get('stratum')||'real')+'.json');
    if(p==='/api/occupation') return load('data/occ/'+q.get('kind')+'_'+q.get('key')+'.json');
    if(p==='/api/occupations'){ var all=await load('data/occupations.json'); var occ=all.occupations.slice();
      var st=q.get('stratum'), qq=(q.get('q')||'').toLowerCase();
      if(st==='real'||st==='fantasy') occ=occ.filter(function(o){return o.stratum===st;});
      if(qq) occ=occ.filter(function(o){return o.title.toLowerCase().indexOf(qq)>=0||o.key.toLowerCase().indexOf(qq)>=0;});
      return {denominator:all.denominator, occupations:occ}; }
    if(p==='/api/anime/search'){ var t=await load('data/titles.json'); var qq=(q.get('q')||'').toLowerCase();
      if(qq.length<2) return {results:[]};
      return {results:t.filter(function(a){return a.title.toLowerCase().indexOf(qq)>=0;})
        .sort(function(a,b){return (b.popularity||0)-(a.popularity||0);}).slice(0,40)}; }
    if(p==='/api/anime'){ var b=await load('data/anime.json'); var e=b[q.get('id')]||{};
      return {anime:e.anime||{anilist_id:+q.get('id')}, occupations:e.occupations||[]}; }
    if(p==='/api/trends'){ var kind=q.get('kind'), keys=(q.get('keys')||'').split(',').filter(Boolean);
      var decs=await load('data/decades.json'), series=[];
      for(var i=0;i<keys.length;i++){ var d=await load('data/occ/'+kind+'_'+keys[i]+'.json');
        series.push({key:keys[i], title:(kind==='isco'?d.info.title:keys[i].replace(/_/g,' ')), points:d.decades}); }
      return {decades:decs, series:series}; }
    throw new Error('static: unmapped '+url);
  };
})();
</script>
"""


def _w(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def export(out_dir: str = "site") -> None:
    webapp.CACHE = webapp.Cache()
    out = config.ROOT / out_dir
    data = out / "data"
    occ_dir = data / "occ"
    if out.exists():
        shutil.rmtree(out)
    occ_dir.mkdir(parents=True)

    print("[static] summary / occupations / decades / leaderboards")
    _w(data / "summary.json", webapp.api_summary())
    _w(data / "occupations.json", webapp.api_occupations({"stratum": ["all"]}))
    _w(data / "decades.json", sorted(webapp.CACHE.corpus_decade))
    _w(data / "decade_top_real.json", webapp.api_decade_top({"stratum": ["real"], "n": ["6"]}))
    _w(data / "decade_top_fantasy.json", webapp.api_decade_top({"stratum": ["fantasy"], "n": ["6"]}))

    print("[static] per-occupation detail files")
    occs = webapp.CACHE.occ_list()
    for o in occs:
        _w(occ_dir / f"{o['kind']}_{o['key']}.json",
           webapp.api_occupation({"kind": [o["kind"]], "key": [o["key"]]}))

    print("[static] title search index")
    con = webapp._con()
    titles = [{"anilist_id": r["anilist_id"], "title": r["title"], "year": r["year"],
               "format": r["format"], "popularity": r["popularity"]}
              for r in con.execute("SELECT anilist_id,title,year,format,popularity FROM anime")]
    _w(data / "titles.json", titles)

    print("[static] anime detail blob (only titles with confirmed hits)")
    ids = [r[0] for r in con.execute(
        "SELECT DISTINCT c.anime_id FROM candidate c "
        "JOIN adjudication a ON a.candidate_id=c.candidate_id AND a.verdict='yes'")]
    con.close()
    blob = {}
    for aid in ids:
        d = webapp.api_anime({"id": [str(aid)]})
        if d.get("occupations"):
            blob[str(aid)] = {"anime": d["anime"], "occupations": d["occupations"]}
    _w(data / "anime.json", blob)

    print("[static] index.html (+ shim) + .nojekyll")
    html = (config.ROOT / "web" / "index.html").read_text(encoding="utf-8")
    anchor = "<script>\nconst $ ="
    if anchor not in html:
        raise RuntimeError("could not find main <script> anchor in index.html")
    html = html.replace(anchor, SHIM + anchor, 1)
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")

    nfiles = sum(1 for _ in out.rglob("*") if _.is_file())
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"[static] wrote {out}/ — {nfiles} files, {size/1e6:.1f} MB "
          f"({len(occs)} occupation files, {len(blob)} anime, {len(titles)} titles)")
    print(f"[static] preview:  cd {out} && python3 -m http.server 8090   ->  http://127.0.0.1:8090")
