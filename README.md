# Anime Professions

**Which real-world jobs does anime actually show?** This project scans **21,988 anime** and
counts how often each occupation appears — a complete lookup table keyed to **ISCO-08**, the
UN/ILO's standard occupation classification. The headline finding is the *absence* list: the
jobs anime never names at all.

> 🔎 **Live explorer:** https://elmiram.github.io/anime-professions/ &nbsp;·&nbsp; search any profession, see which anime feature it, and how it trends by decade.

A few things it found:

- **Teachers** are the most-named profession (in ~1,370 anime, 7.6%) — anime lives at school.
- In the **2020s, shopkeepers overtook teachers** for #1, on the back of the isekai/slice-of-life boom.
- If you count fantasy roles, **being royalty** (1,792 titles) out-appears every real job.
- **17 renderable occupations are never named**, even across millions of lines of dialogue —
  financial analysts, systems analysts, driving instructors, printers, fast-food workers, ships'
  engineers… the back-office and service tail.
- Your niche jobs, quantified: software developers **41**, insurance reps **18** (Trigun's leads are
  literally insurance agents), pharmacists **15**, tram/bus drivers **5**.

---

## What this is

A hobby data project. It builds a taxonomy of occupations, detects mentions of them in anime,
classifies each mention with an LLM, and produces per-occupation counts, a decade-by-decade
breakdown, precision/recall estimates, and three CSVs. A small local/static web app explores the
results.

Real occupations are kept strictly separate from a **fantasy stratum** (ninja, mage, adventurer,
royalty, samurai…) — the fictional roles are counted but never folded into the real-job totals.

## How it works

Text-first, in three layers:

1. **Corpus + protagonists** — every anime's plot summary (via AniList).
2. **Supporting characters** — AniList character bios, with a `role` field (main / supporting /
   background) so a doctor who appears in six episodes still counts as representation.
3. **Dialogue** — ~128,000 Japanese subtitle files (from a community mirror), so a job mentioned
   only in passing gets caught too.

Detection is a two-stage pipeline:

- **Stage 1 — high recall.** A keyword lexicon (English + Japanese surface forms mapped to ISCO
  codes) casts a wide net over the text, accepting false positives.
- **Stage 2 — precision.** *Every* ambiguous candidate sentence is judged in context by an LLM
  (**Claude Haiku**): does a character here really hold this job? This kills the classic traps —
  negation ("I'm not a doctor"), hypotheticals ("if I were a pilot"), polysemy ("officer",
  "band"), and fantasy homonyms (a mecha **pilot** is not an airline pilot).

A stronger model (**Claude Opus**) then grades a stratified sample of the confirmed hits to
estimate **precision per occupation**, and AniList tags provide a **recall** benchmark. Occupations
whose precision falls below a floor are flagged **unreliable** in the output rather than reported as
fact.

## Reading the numbers (important caveats)

- **Named, not shown.** We detect jobs that are *named* in text. A profession shown on screen but
  never labeled — a festival food stall, a hotel receptionist standing in frame — is invisible to
  the method. The "never-named" list is exactly that: never *named*.
- **Unreliable flags are real.** ~a quarter of measured occupations are flagged unreliable (e.g.
  "aircraft pilot" is mostly mecha pilots) — treat those counts as upper bounds.
- **Franchise vs entry.** Counts deduplicate to franchise by default (Detective Conan's ~28 films =
  1), but every entry is kept as its own row so you can expand or collapse.
- **Denominator is printed** next to every percentage (of ~18,127 titles with scannable text).

## Data sources & ethics

- Anime metadata, titles, character bios, tags: **[AniList](https://anilist.co)** (GraphQL API).
- Occupation taxonomy: **[ISCO-08](https://isco.ilo.org/en/isco-08)** (International Labour Organization).
- Dialogue: a community archive of Japanese anime subtitles.

**Subtitles are copyrighted works.** This project derives *counts and locators only* — it never
stores or redistributes subtitle text. The exported dataset and the web app contain derived
statistics, titles, and AniList ids; no subtitle text, and not even the raw AniList descriptions.
Non-commercial fan project.

## The explorer

Two ways to run the same UI:

```bash
python ap.py web            # local server at http://127.0.0.1:8000
python ap.py export-static  # precompute a static ./site for GitHub Pages (no backend)
```

The static build turns every API response into JSON and answers the same calls client-side, so it
hosts anywhere as plain files.

## Run the pipeline yourself

Requires Python 3.11+ and an Anthropic API key (for the LLM stages).

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
echo "sk-ant-..." > api_key.txt        # or export ANTHROPIC_API_KEY

python ap.py collect          # AniList corpus + characters + tags (free, ~15 min)
python ap.py franchise        # cluster franchises
python ap.py extract          # Stage-1 lexicon candidates (free)
python ap.py estimate         # exact candidate count + projected batched cost (free)
python ap.py adjudicate       # Stage-2 Claude Haiku via Batch API (spends)
python ap.py measure          # precision/recall (Claude Opus gold + tag recall)
python ap.py analyse          # coverage report + zero-mention list
python ap.py export           # occupation_counts.csv, title_occupation.csv, evidence.csv

# Optional Layer C — subtitle dialogue:
python ap.py subtitles-prep   # clone the subtitle mirror + estimate
python ap.py subtitles-match  # match subtitle folders -> AniList ids
python ap.py subtitles-scan   # extract candidates (text never stored)
python ap.py adjudicate       # adjudicate the new subtitle candidates
```

Cost/scale reference: the full run analysed 21,988 anime and 128k subtitle files with ~101,000
Claude Haiku judgments (+ ~2,000 Opus spot-checks) for roughly **$34** total, in about a day of
mostly-unattended batch processing. Collection is resumable (checkpointed) and respects rate
limits.

## Repository layout

```
ap/                package
  taxonomy.py      ISCO-08 hierarchy (436 unit groups) + renderable/fantasy overlay
  lexicon.py       English surface forms per occupation + ambiguity flags
  jp_lexicon.py    Japanese surface forms (Layer C)
  db.py            SQLite schema + resumable checkpoints
  anilist.py       AniList GraphQL client
  collect.py       corpus + characters + tags + franchise clustering
  extract.py       Stage-1 lexicon candidate generation
  adjudicate.py    Stage-2 Claude Haiku / Batch API + free cost estimate
  measure.py       precision/recall (Claude Opus gold + tag recall)
  layerc.py        subtitle scanning (smart middle; text never stored)
  analyse.py       console coverage report + zero-mention list
  export.py        three CSVs
  webapp.py        local explorer (stdlib server + JSON API)
  export_static.py precompute the static site
ap.py              CLI entrypoint
web/index.html     the explorer frontend (vanilla JS, inline SVG charts)
```

## Credits & license

Built with the [Claude API](https://claude.com). Data © their respective providers (AniList; ILO
for ISCO-08). Code released for reference; the data shown is derived and non-commercial. Not
affiliated with AniList, MyAnimeList, or any studio.
