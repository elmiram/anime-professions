#!/usr/bin/env python3
"""anime_professions CLI — occupational representation in anime.

Free (no spend):   collect, franchise, extract, analyse, export, estimate
Paid (Haiku/Opus): adjudicate, measure

Typical flow:
    python ap.py collect --sample 50      # or full: python ap.py collect
    python ap.py franchise
    python ap.py extract
    python ap.py estimate                 # exact candidate count + projected batched cost
    python ap.py adjudicate               # Stage-2 Batch API (spends)
    python ap.py measure                  # precision/recall (spends a little)
    python ap.py analyse
    python ap.py export

Credentials: ANTHROPIC_API_KEY env var, or api_key.txt in this directory (never logged).
"""
import argparse
import json


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="AniList corpus + tags + relations + characters")
    c.add_argument("--sample", type=int, default=None, help="stop after ~N titles (test mode)")
    c.add_argument("--restart", action="store_true", help="restart from page 1")
    c.add_argument("--per-page", type=int, default=50)
    c.add_argument("--char-per-page", type=int, default=25)

    sub.add_parser("franchise", help="assign franchise_id by relation clustering")
    sub.add_parser("extract", help="Stage-1 lexicon candidate generation")
    sub.add_parser("estimate", help="free: exact candidate count + projected batched cost")

    a = sub.add_parser("adjudicate", help="Stage-2 Haiku Batch API (spends)")
    a.add_argument("--poll", type=int, default=20, help="batch poll interval (s)")

    m = sub.add_parser("measure", help="precision/recall (Opus gold + tag recall; spends a little)")
    m.add_argument("--per-occ", type=int, default=8)
    m.add_argument("--floor", type=float, default=0.7)

    an = sub.add_parser("analyse", help="console coverage report + zero-mention list")
    an.add_argument("--count-mode", choices=["franchise", "entry"], default="franchise")
    an.add_argument("--top", type=int, default=30)

    ex = sub.add_parser("export", help="write the three CSVs")
    ex.add_argument("--count-mode", choices=["franchise", "entry"], default="franchise")

    pl = sub.add_parser("pipeline", help="collect->franchise->extract->estimate (free); optional spend")
    pl.add_argument("--sample", type=int, default=None)
    pl.add_argument("--adjudicate", action="store_true", help="also run Stage-2 + measure + export")

    wb = sub.add_parser("web", help="launch the local data explorer (http://127.0.0.1:8000)")
    wb.add_argument("--port", type=int, default=8000)

    es = sub.add_parser("export-static", help="precompute a static site/ folder for GitHub Pages")
    es.add_argument("--out", default="site")

    sub.add_parser("subtitles-prep", help="Layer C: clone mirror + index + cost estimate")
    sub.add_parser("subtitles-match", help="Layer C: match subtitle folders -> AniList ids")
    sc = sub.add_parser("subtitles-scan", help="Layer C: scan subtitles -> candidates (smart middle)")
    sc.add_argument("--limit", type=int, default=None, help="scan only N titles (test)")

    args = p.parse_args()

    if args.cmd == "collect":
        from ap import collect
        collect.collect_corpus(sample=args.sample, per_page=args.per_page,
                               char_per_page=args.char_per_page, restart=args.restart)
    elif args.cmd == "franchise":
        from ap import collect; collect.assign_franchises()
    elif args.cmd == "extract":
        from ap import extract; extract.generate_candidates()
    elif args.cmd == "estimate":
        from ap import adjudicate; print(json.dumps(adjudicate.estimate(), indent=2))
    elif args.cmd == "adjudicate":
        from ap import adjudicate; print(json.dumps(adjudicate.run(poll_interval=args.poll)))
    elif args.cmd == "measure":
        from ap import measure; measure.measure(per_occ=args.per_occ, floor=args.floor)
    elif args.cmd == "analyse":
        from ap import analyse; analyse.report(count_mode=args.count_mode, top=args.top)
    elif args.cmd == "export":
        from ap import export; export.export_all(count_mode=args.count_mode)
    elif args.cmd == "pipeline":
        from ap import collect, extract, adjudicate
        collect.collect_corpus(sample=args.sample)
        collect.assign_franchises()
        extract.generate_candidates()
        print(json.dumps(adjudicate.estimate(), indent=2))
        if args.adjudicate:
            adjudicate.run()
            from ap import measure, analyse, export
            measure.measure(); analyse.report(); export.export_all()
    elif args.cmd == "web":
        from ap import webapp; webapp.serve(port=args.port)
    elif args.cmd == "export-static":
        from ap import export_static; export_static.export(out_dir=args.out)
    elif args.cmd == "subtitles-prep":
        from ap import subtitles; subtitles.prep()
    elif args.cmd == "subtitles-match":
        from ap import layerc; layerc.build_title_map()
    elif args.cmd == "subtitles-scan":
        from ap import layerc; layerc.scan(limit=args.limit)


if __name__ == "__main__":
    main()
