"""Console coverage report — clean, copy-pasteable (feeds a slide/design tool).

Headline outputs: top occupations, and the ZERO-MENTION list among renderable ISCO
unit groups (a genuine absence-from-anime finding). Fantasy stratum printed separately,
never folded into ISCO totals. Every percentage prints its denominator N.
"""
from __future__ import annotations
from . import agg, db, taxonomy
from .lexicon import LEXICON, FANTASY


def report(count_mode: str = "franchise", top: int = 30) -> None:
    con = db.connect()
    dens = agg.denominators(con)
    N = dens["with_scannable_text"] or 1
    counts = agg.occupation_counts(con, count_mode)
    isco_counts = {k[1]: v for k, v in counts.items() if k[0] == "isco"}
    fan_counts = {k[1]: v for k, v in counts.items() if k[0] == "fantasy"}

    print("=" * 70)
    print(f"ANIME OCCUPATIONAL REPRESENTATION  (count mode: {count_mode})")
    print("=" * 70)
    print(f"Corpus: {dens['all_in_denominator']:,} titles in denominator "
          f"(Music/CM excluded); {N:,} have scannable text.")
    print(f"Percentages below are of the {N:,} titles with scannable text.\n")

    print(f"-- TOP OCCUPATIONS BY TITLE COUNT (real / ISCO-08) --")
    ranked = sorted(isco_counts.items(), key=lambda kv: -kv[1]["count"])
    for code, v in ranked[:top]:
        print(f"  {v['count']:5d}  {100*v['count']/N:5.2f}%   {code}  {taxonomy.title(code)}")

    # zero-mention headline: renderable ISCO units with no confirmed hit
    renderable = [u["code"] for u in taxonomy.all_units() if taxonomy.is_renderable(u["code"])]
    zero = sorted(c for c in renderable if isco_counts.get(c, {}).get("count", 0) == 0)
    rare = sorted((c for c in renderable if 0 < isco_counts.get(c, {}).get("count", 0) <= 5),
                  key=lambda c: isco_counts[c]["count"])
    print(f"\n-- ZERO-MENTION (renderable ISCO units, {len(zero)}/{len(renderable)}): the headline --")
    for c in zero:
        print(f"  {c}  {taxonomy.title(c)}")
    print(f"\n-- RARE (1-5 titles, {len(rare)}) --")
    for c in rare:
        print(f"  {isco_counts[c]['count']:3d}  {c}  {taxonomy.title(c)}")

    print(f"\n-- FANTASY STRATUM (separate; never in ISCO totals) --")
    for key, v in sorted(fan_counts.items(), key=lambda kv: -kv[1]["count"]):
        amb = "  [ambiguous real/fantasy]" if FANTASY.get(key, ((), False))[1] else ""
        print(f"  {v['count']:5d}  {100*v['count']/N:5.2f}%   {key.replace('_',' ')}{amb}")

    print(f"\nNote: {len(renderable)} ISCO unit groups are actively searched (renderable); the "
          f"other {436-len(renderable)} are structurally un-nameable in fiction and are reported "
          f"as untestable, not absent.")
    con.close()
