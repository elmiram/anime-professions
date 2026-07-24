"""AniList GraphQL client (primary source). Stdlib only, polite, resumable.

Rate limiting: min-interval throttle (~85/min), plus 429 Retry-After handling and
exponential backoff on transient 5xx. ID-cursor pagination (id_greater) makes a full
scan resumable — the checkpoint is simply the last id seen.
"""
from __future__ import annotations
import json
import time
import urllib.request
import urllib.error

from . import config

_last_call = 0.0

# One media query returns corpus core + tags (ground truth) + relations (franchise) +
# the first page of characters (Layer 2). Extra character pages are fetched on demand.
# AniList caps offset pagination at 5000 results, so we chunk by start-year window
# (no year has >5000 anime) and page within each. Checkpoint = (year, page).
MEDIA_QUERY = """
query ($page: Int, $perPage: Int, $charPerPage: Int, $gt: FuzzyDateInt, $lt: FuzzyDateInt) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { hasNextPage currentPage }
    media(type: ANIME, sort: ID, startDate_greater: $gt, startDate_lesser: $lt) {
      id
      idMal
      title { romaji english native }
      format
      countryOfOrigin
      startDate { year }
      episodes
      popularity
      favourites
      averageScore
      source
      genres
      description(asHtml: false)
      tags { name rank category isMediaSpoiler }
      relations { edges { relationType node { id type } } }
      characters(sort: [ROLE, RELEVANCE], perPage: $charPerPage) {
        pageInfo { hasNextPage }
        edges { role node { id name { full } description(asHtml: false) } }
      }
    }
  }
}
"""

# Supplementary: fetch further character pages for one media (rarely needed).
CHAR_PAGE_QUERY = """
query ($id: Int, $page: Int, $perPage: Int) {
  Media(id: $id) {
    characters(sort: [ROLE, RELEVANCE], page: $page, perPage: $perPage) {
      pageInfo { hasNextPage }
      edges { role node { id name { full } description(asHtml: false) } }
    }
  }
}
"""


def _throttle():
    global _last_call
    dt = time.monotonic() - _last_call
    if dt < config.ANILIST_MIN_INTERVAL:
        time.sleep(config.ANILIST_MIN_INTERVAL - dt)
    _last_call = time.monotonic()


def post(query: str, variables: dict, max_retries: int = 6) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    for attempt in range(max_retries):
        _throttle()
        req = urllib.request.Request(
            config.ANILIST_URL, data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json",
                     "User-Agent": config.USER_AGENT},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if "errors" in payload and payload["errors"]:
                # AniList returns 200 with an errors array for some conditions.
                msg = payload["errors"][0].get("message", "unknown")
                if "Too Many Requests" in msg or "rate" in msg.lower():
                    time.sleep(min(60, 5 * (attempt + 1))); continue
                raise RuntimeError(f"AniList GraphQL error: {msg}")
            return payload["data"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = int(e.headers.get("Retry-After", "60"))
                print(f"  [anilist] 429; sleeping {wait}s")
                time.sleep(wait + 1); continue
            if e.code in (500, 502, 503, 504):
                back = min(60, 2 ** attempt)
                print(f"  [anilist] {e.code}; backoff {back}s")
                time.sleep(back); continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            back = min(60, 2 ** attempt)
            print(f"  [anilist] network {e}; backoff {back}s")
            time.sleep(back); continue
    raise RuntimeError(f"AniList: exhausted retries for variables={variables}")


def media_page(page: int, per_page: int = 50, char_per_page: int = 25,
               year: int | None = None) -> dict:
    """Offset page of media (sort: ID), optionally restricted to a start-year window.
    Returns the Page object. Year window includes fuzzy dates stored as YYYY0000."""
    gt = (year * 10000 - 1) if year else None      # e.g. 2020 -> 20199999
    lt = ((year + 1) * 10000) if year else None    # e.g. 2020 -> 20210000
    data = post(MEDIA_QUERY, {"page": page, "perPage": per_page, "charPerPage": char_per_page,
                              "gt": gt, "lt": lt})
    return data["Page"]


def character_page(media_id: int, page: int, per_page: int = 25) -> dict:
    data = post(CHAR_PAGE_QUERY, {"id": media_id, "page": page, "perPage": per_page})
    return data["Media"]["characters"]
