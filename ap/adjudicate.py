"""Stage 2 — precision adjudication with Claude Haiku 4.5 via the Batch API.

Only AMBIGUOUS candidates are sent. Unambiguous candidates get a synthetic trusted
verdict with no API call. For each candidate we read the source text in memory to pull
the ONE sentence containing the matched term — that sentence is sent to the model and
never stored. Verdicts (holds/stratum/confidence) are stored; text is not.

The `estimate()` path uses the free count_tokens endpoint to report the exact candidate
count and projected batched cost BEFORE any spend (this is the gate for the full run and
the template for the Layer C estimate).
"""
from __future__ import annotations
import json
import re
import time

from . import config, db, extract
from .lexicon import LEXICON, FANTASY
from . import taxonomy

MODEL = config.ADJUDICATION_MODEL
# Haiku 4.5 batched rates (per token). Batch API = -50%.
IN_RATE = 1.0 / 1e6 * 0.5
OUT_RATE = 5.0 / 1e6 * 0.5
EST_OUTPUT_TOKENS = 40   # the JSON verdict is tiny

SYSTEM = (
    "You judge whether an anime actually depicts a character who holds a specific real-world "
    "occupation or fantasy role.\n\n"
    "You get an OCCUPATION and one SENTENCE from the anime's synopsis or a character "
    "description. Decide whether the sentence asserts that a character in this work genuinely "
    "holds that occupation/role.\n\n"
    'Answer "no" when:\n'
    '- the mention is negated ("not a doctor", "no longer a teacher");\n'
    '- it is hypothetical, aspirational, or future ("if he were a pilot", "wants to become a '
    'nurse", "dreams of being an idol") — not yet true means no;\n'
    "- the word is used in another sense than the occupation (a mecha/robot \"pilot\" or a TV "
    '"pilot", not an aircraft pilot; a company "officer"; "band" = wristband; "model" = role '
    'model; "cook" as a verb; "general" = in general; a surname like "Smith"/"Potter");\n'
    "- it is a metaphor, nickname, or the title of a work, not a real role.\n\n"
    'Answer "yes" when any character in the work holds the occupation/role — including '
    "supporting and minor characters. A real tradesperson working in a fantasy setting (e.g. a "
    "blacksmith who forges swords) still counts as the real occupation.\n\n"
    'STRATUM: "real" for a real-world occupation, "fantasy" for a fantasy-world role '
    '(knight, mage, adventurer), "na" if no/unsure.\n\n'
    'Return ONLY JSON: {"holds":"yes|no","stratum":"real|fantasy|na","confidence":0.0-1.0}'
)

_OUTPUT_FORMAT = {
    "format": {
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {
                "holds": {"type": "string", "enum": ["yes", "no"]},
                "stratum": {"type": "string", "enum": ["real", "fantasy", "na"]},
                "confidence": {"type": "number"},
            },
            "required": ["holds", "stratum", "confidence"],
            "additionalProperties": False,
        },
    }
}

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _label(isco_code: str | None, fantasy_key: str | None) -> tuple[str, str]:
    if isco_code:
        return taxonomy.title(isco_code), f'ISCO "{taxonomy.title(isco_code)}"'
    forms = FANTASY.get(fantasy_key, ((fantasy_key,), False))[0]
    return fantasy_key.replace("_", " "), f'fantasy role "{forms[0]}"'


def _sentence_for(text: str, term: str) -> str:
    """The sentence containing `term` (whole-word), else a window around the match."""
    clean = extract.clean(text)
    pat = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
    for sent in _SENT_SPLIT.split(clean):
        if pat.search(sent):
            s = sent.strip()
            return s[:400]
    m = pat.search(clean)
    if m:
        a, b = max(0, m.start() - 160), min(len(clean), m.end() + 160)
        return clean[a:b].strip()
    return clean[:300].strip()


def _pending(con, only_anime):
    """Ambiguous candidates with no adjudication yet, joined to their source text."""
    where = "c.ambiguous=1 AND a.candidate_id IS NULL"
    params: list = []
    if only_anime:
        qs = ",".join("?" * len(only_anime))
        where += f" AND c.anime_id IN ({qs})"
        params += list(only_anime)
    q = f"""
        SELECT c.candidate_id, c.isco_code, c.fantasy_key, c.term, c.source,
               CASE WHEN c.source='synopsis' THEN an.synopsis ELSE ch.description END AS text,
               c.locator
        FROM candidate c
        LEFT JOIN adjudication a ON a.candidate_id = c.candidate_id
        JOIN anime an ON an.anilist_id = c.anime_id
        LEFT JOIN character ch ON ch.char_id = c.char_id
        WHERE {where}
    """
    return con.execute(q, params).fetchall()


def _sentence(source, text, locator, term) -> str:
    """The one matched sentence. For subtitles, read the file at the locator in memory
    (never stored); otherwise slice the DB-held synopsis/bio text."""
    if source == "subtitle":
        from . import layerc
        return layerc.subtitle_sentence(locator or "", term)
    return _sentence_for(text or "", term)


def _user_message(isco, fant, term, sentence) -> str:
    label, isco_desc = _label(isco, fant)
    return (f"OCCUPATION: {label} ({isco_desc})\n"
            f'MATCHED WORD: "{term}"\n'
            f'SENTENCE: "{sentence}"\n'
            "Does a character in this work hold this occupation, judging the matched word in context?")


def _make_request(cid, isco, fant, term, sentence):
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    user = _user_message(isco, fant, term, sentence)
    return Request(
        custom_id=f"c{cid}",
        params=MessageCreateParamsNonStreaming(
            model=MODEL, max_tokens=100, system=SYSTEM,
            messages=[{"role": "user", "content": user}],
            output_config=_OUTPUT_FORMAT,
        ),
    )


def apply_trusted(only_anime=None) -> int:
    """Synthesize verdicts for unambiguous candidates (no API call)."""
    con = db.connect()
    where = "c.ambiguous=0 AND a.candidate_id IS NULL"
    params: list = []
    if only_anime:
        qs = ",".join("?" * len(only_anime))
        where += f" AND c.anime_id IN ({qs})"
        params += list(only_anime)
    rows = con.execute(
        f"SELECT c.candidate_id, c.isco_code FROM candidate c "
        f"LEFT JOIN adjudication a ON a.candidate_id=c.candidate_id WHERE {where}", params
    ).fetchall()
    con.executemany(
        "INSERT OR REPLACE INTO adjudication"
        "(candidate_id,verdict,real_or_fantasy,prominence,confidence,model) VALUES(?,?,?,?,?,?)",
        [(cid, "yes", "real" if isco else "fantasy", "unknown", 0.9, "trusted") for cid, isco in rows],
    )
    con.commit()
    n = len(rows); con.close()
    return n


def estimate(only_anime=None, token_sample: int = 40) -> dict:
    """Exact ambiguous-candidate count + measured avg input tokens (free) -> projected cost."""
    con = db.connect()
    pending = _pending(con, only_anime)
    n = len(pending)
    result = {"pending_candidates": n, "trusted_candidates":
              con.execute("SELECT COUNT(*) FROM candidate WHERE ambiguous=0").fetchone()[0]}
    if n == 0:
        con.close(); result["projected_cost_usd"] = 0.0; return result

    key = config.get_api_key()
    if not key:
        result["error"] = "no API key (set ANTHROPIC_API_KEY or api_key.txt)"; con.close(); return result
    import anthropic
    client = anthropic.Anthropic(api_key=key)

    import random
    sample = random.sample(pending, min(token_sample, n))
    toks = []
    for cid, isco, fant, term, source, text, locator in sample:
        user = _user_message(isco, fant, term, _sentence(source, text, locator, term))
        ct = client.messages.count_tokens(
            model=MODEL, system=SYSTEM, messages=[{"role": "user", "content": user}])
        toks.append(ct.input_tokens)
    avg_in = sum(toks) / len(toks)
    cost = n * (avg_in * IN_RATE + EST_OUTPUT_TOKENS * OUT_RATE)
    result.update({
        "avg_input_tokens": round(avg_in, 1),
        "est_output_tokens": EST_OUTPUT_TOKENS,
        "in_rate_per_mtok_batched": 0.5, "out_rate_per_mtok_batched": 2.5,
        "projected_cost_usd": round(cost, 2),
    })
    con.close()
    return result


def submit_and_collect(client, requests, batch_size: int = 50000, poll_interval: int = 20):
    """Submit requests to the Batch API in chunks; yield (custom_id, raw_text_or_None)."""
    for i in range(0, len(requests), batch_size):
        chunk = requests[i:i + batch_size]
        batch = client.messages.batches.create(requests=chunk)
        print(f"  batch {batch.id}: {len(chunk)} requests submitted", flush=True)
        while True:
            b = client.messages.batches.retrieve(batch.id)
            if b.processing_status == "ended":
                break
            time.sleep(poll_interval)
        n = 0
        for res in client.messages.batches.results(batch.id):
            if res.result.type != "succeeded":
                yield res.custom_id, None
            else:
                txt = next((bl.text for bl in res.result.message.content if bl.type == "text"), None)
                yield res.custom_id, txt
            n += 1
        print(f"  batch {batch.id}: collected {n} results", flush=True)


def run(only_anime=None, batch_size: int = 50000, poll_interval: int = 20) -> dict:
    """Trusted pass + submit ambiguous candidates to the Batch API, write verdicts."""
    trusted = apply_trusted(only_anime)
    con = db.connect()
    pending = _pending(con, only_anime)
    print(f"[adjudicate] trusted:{trusted}  ambiguous->batch:{len(pending)}", flush=True)
    if not pending:
        con.close(); return {"trusted": trusted, "adjudicated": 0}

    key = config.get_api_key()
    if not key:
        con.close(); raise RuntimeError("no API key; set ANTHROPIC_API_KEY or api_key.txt")
    import anthropic
    client = anthropic.Anthropic(api_key=key)

    reqs = [_make_request(cid, isco, fant, term, _sentence(source, text, locator, term))
            for cid, isco, fant, term, source, text, locator in pending]
    done = 0
    for custom_id, txt in submit_and_collect(client, reqs, batch_size, poll_interval):
        cid = int(custom_id[1:])
        if txt is None:
            row = (cid, "no", "na", "unknown", 0.0, MODEL + ":error")
        else:
            try:
                v = json.loads(txt)
                row = (cid, v.get("holds", "no"), v.get("stratum", "na"),
                       "unknown", float(v.get("confidence", 0.0)), MODEL)
            except Exception:
                row = (cid, "no", "na", "unknown", 0.0, MODEL + ":parse")
        con.execute(
            "INSERT OR REPLACE INTO adjudication"
            "(candidate_id,verdict,real_or_fantasy,prominence,confidence,model) VALUES(?,?,?,?,?,?)",
            row)
        done += 1
        if done % 2000 == 0:
            con.commit(); print(f"    ...{done} verdicts written", flush=True)
    con.commit(); con.close()
    return {"trusted": trusted, "adjudicated": done}
