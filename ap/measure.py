"""Precision/recall measurement of the text pipeline (PROJECT_PLAN.md §5).

PRECISION: sample the pipeline's CONFIRMED candidates per occupation, get a reference
"gold" verdict from a stronger model (Opus 4.8) on the same sentence, and compute
per-occupation precision = fraction the reference also confirms. This is model-assisted
gold (labelled as such), a defensible reference over the Haiku adjudicator; it can be
overridden with true manual labels in the gold_label table.

RECALL (proxy): AniList tags are the "should-have-detected" set. For occupations with a
clean tag, recall = |tagged titles the pipeline also confirmed| / |tagged titles|. Biased
(tags are premise-level) but a useful floor.

Occupations whose precision is below `floor` are flagged unreliable in the output.
"""
from __future__ import annotations
import json
import random

from . import adjudicate, config, db

GOLD_MODEL = "claude-opus-4-8"

# occupation -> AniList tag names that mark the same theme/trait (recall proxy)
RECALL_TAGS: dict[tuple, list[str]] = {
    ("isco", "5412"): ["Police"],
    ("isco", "3355"): ["Detective"],
    ("isco", "2211"): ["Medicine"],
    ("isco", "2652"): ["Band", "Rock Music", "Musical Theater", "Hip-hop Music", "Idol"],
    ("isco", "2330"): ["Teacher"],
    ("isco", "0310"): ["Military"],
    ("isco", "5152"): ["Butler"],
    ("fantasy", "samurai"): ["Samurai"],
    ("fantasy", "ninja"): ["Ninja"],
    ("fantasy", "assassin"): ["Assassins"],
    ("fantasy", "pirate"): ["Pirates"],
    ("fantasy", "yakuza"): ["Yakuza", "Mafia"],
    ("fantasy", "mage"): ["Magic"],
}
TAG_RANK_MIN = 40


def _occ_key(isco, fant):
    return isco if isco else f"fantasy:{fant}"


def _sample_confirmed(con, per_occ: int):
    """Stratified sample of confirmed candidates, capped per occupation."""
    rows = con.execute("""
        SELECT c.candidate_id, c.isco_code, c.fantasy_key, c.term, c.source,
               CASE WHEN c.source='synopsis' THEN an.synopsis ELSE ch.description END, c.locator
        FROM candidate c
        JOIN adjudication adj ON adj.candidate_id=c.candidate_id AND adj.verdict='yes'
        JOIN anime an ON an.anilist_id=c.anime_id
        LEFT JOIN character ch ON ch.char_id=c.char_id
    """).fetchall()
    by_occ: dict = {}
    for r in rows:
        by_occ.setdefault(_occ_key(r[1], r[2]), []).append(r)
    sample = []
    for occ, items in by_occ.items():
        random.shuffle(items)
        sample.extend(items[:per_occ])
    return sample


def gold_label(per_occ: int = 8, poll_interval: int = 20) -> int:
    """Get reference gold verdicts (Opus) for a stratified confirmed-candidate sample."""
    con = db.connect()
    key = config.get_api_key()
    if not key:
        raise RuntimeError("no API key")
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    client = anthropic.Anthropic(api_key=key)

    sample = _sample_confirmed(con, per_occ)
    reqs = [Request(custom_id=f"c{cid}",
                    params=MessageCreateParamsNonStreaming(
                        model=GOLD_MODEL, max_tokens=100, system=adjudicate.SYSTEM,
                        messages=[{"role": "user",
                                   "content": adjudicate._user_message(
                                       isco, fant, term,
                                       adjudicate._sentence(src, text, loc, term))}],
                        output_config=adjudicate._OUTPUT_FORMAT))
            for cid, isco, fant, term, src, text, loc in sample]
    print(f"[measure] gold-labelling {len(reqs)} confirmed candidates with {GOLD_MODEL}", flush=True)
    n = 0
    for custom_id, txt in adjudicate.submit_and_collect(client, reqs, poll_interval=poll_interval):
        cid = int(custom_id[1:])
        holds = "no"
        if txt:
            try:
                holds = json.loads(txt).get("holds", "no")
            except Exception:
                pass
        con.execute("INSERT OR REPLACE INTO gold_label(candidate_id,gold_holds,source) VALUES(?,?,?)",
                    (cid, holds, f"model-assisted:{GOLD_MODEL}"))
        n += 1
    con.commit(); con.close()
    return n


def compute(floor: float = 0.7) -> None:
    """Per-occupation precision (vs gold) + tag-recall proxy -> precision_recall table."""
    con = db.connect()
    # precision: over sampled confirmed candidates that have a gold label
    prec: dict = {}
    q = """SELECT c.isco_code, c.fantasy_key, g.gold_holds
           FROM gold_label g JOIN candidate c ON c.candidate_id=g.candidate_id"""
    for isco, fant, gold in con.execute(q):
        k = (isco, fant); d = prec.setdefault(k, [0, 0])
        d[1] += 1
        if gold == "yes":
            d[0] += 1

    # recall proxy via tags
    recall: dict = {}
    for (kind, key), tags in RECALL_TAGS.items():
        placeholders = ",".join("?" * len(tags))
        tagged = {r[0] for r in con.execute(
            f"SELECT anime_id FROM tag WHERE name IN ({placeholders}) AND rank>=?",
            (*tags, TAG_RANK_MIN))}
        if not tagged:
            continue
        col = "isco_code" if kind == "isco" else "fantasy_key"
        confirmed = {r[0] for r in con.execute(
            f"""SELECT c.anime_id FROM candidate c
                JOIN adjudication a ON a.candidate_id=c.candidate_id AND a.verdict='yes'
                WHERE c.{col}=?""", (key,))}
        hit = len(tagged & confirmed)
        recall[(key if kind == "isco" else None, key if kind == "fantasy" else None)] = (
            hit / len(tagged), len(tagged))

    # write precision_recall for ISCO occupations (CSV consumes these)
    con.execute("DELETE FROM precision_recall")
    written = 0
    for (isco, fant), (correct, total) in prec.items():
        if not isco:
            continue  # fantasy precision printed to console, not in the ISCO CSV columns
        p = correct / total if total else None
        rec = recall.get((isco, None))
        con.execute(
            "INSERT OR REPLACE INTO precision_recall(isco_code,precision,recall,n_labeled,reliable) "
            "VALUES(?,?,?,?,?)",
            (isco, round(p, 3) if p is not None else None,
             round(rec[0], 3) if rec else None, total, int(p is not None and p >= floor)))
        written += 1
    con.commit()

    print(f"[measure] precision/recall for {written} ISCO occupations (floor={floor})")
    print("  occ    prec  recall  n   reliable")
    for isco, p, r, n, rel in con.execute(
            "SELECT isco_code,precision,recall,n_labeled,reliable FROM precision_recall "
            "ORDER BY precision"):
        from . import taxonomy
        print(f"  {isco}  {('%.2f'%p) if p is not None else '  - '}  "
              f"{('%.2f'%r) if r is not None else '  - '}  {n:3d}   {'yes' if rel else 'NO '}"
              f"   {taxonomy.title(isco)}")
    con.close()


def measure(per_occ: int = 8, floor: float = 0.7) -> None:
    gold_label(per_occ=per_occ)
    compute(floor=floor)
