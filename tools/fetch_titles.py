"""Light romaji/english/native title fetch for every corpus anime -> data/titles.json.
Writes to a side file (no contention with a running DB job). Reused for the subtitle
title->AniList-id match (Layer C) and the corpus-intersection answer.
"""
import json
from ap import anilist, config

Q = """
query ($page: Int, $per: Int, $gt: FuzzyDateInt, $lt: FuzzyDateInt) {
  Page(page: $page, perPage: $per) {
    pageInfo { hasNextPage }
    media(type: ANIME, sort: ID, startDate_greater: $gt, startDate_lesser: $lt) {
      id title { romaji english native }
    }
  }
}
"""

out = {}
for year in range(1900, 2028):
    gt, lt = year * 10000 - 1, (year + 1) * 10000
    page = 1
    while True:
        data = anilist.post(Q, {"page": page, "per": 50, "gt": gt, "lt": lt})
        p = data["Page"]
        for m in p["media"]:
            out[m["id"]] = m["title"]
        if not p["pageInfo"]["hasNextPage"] or not p["media"]:
            break
        page += 1
    if year % 10 == 0:
        print(f"  ...{year}: {len(out)} titles", flush=True)

path = config.DATA_DIR / "titles.json"
json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False)
print(f"wrote {path}: {len(out)} titles")
