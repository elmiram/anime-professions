"""anime_professions — occupational representation in anime.

Package layout:
  config      paths, constants, credentials
  taxonomy    ISCO-08 hierarchy (436 unit groups) + renderable/fantasy overlay
  lexicon     surface forms per unit group + ambiguity flags + fantasy stratum
  db          SQLite schema + resumable-collection checkpoints
  anilist     AniList GraphQL client (primary source)
  jikan       MAL/Jikan enrichment (optional, best-effort)
  collect     Layer 1 (corpus) + Layer 2 (characters) + ground-truth tags
  extract     Stage 1 — lexicon candidate generation
  adjudicate  Stage 2 — Haiku/Batch precision pass
  analyse     console coverage report + zero-mention list
  export      three CSVs + SQLite is the source of truth

The CLI entrypoint is ../ap.py.
"""
