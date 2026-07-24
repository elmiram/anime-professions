"""Layer C prep (GATED): clone the subtitle mirror, index it, and estimate adjudication
cost — WITHOUT scanning-then-adjudicating. Only counts/locators are ever derived; no
subtitle text is stored or redistributed.

The actual Layer-C run needs: (1) a Japanese extraction pipeline (tokenization + a JP
occupation lexicon — the mirror is mostly Japanese subs), and (2) a fresh cost estimate
approved by the user. This module produces that estimate.
"""
from __future__ import annotations
import re
import subprocess
import random

from . import config, extract

_TS = re.compile(r"^\d\d?:\d\d:\d\d")
_CJK = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")   # hiragana/katakana/kanji
# Anime only; the mirror also holds live-action J-drama we don't want.
ANIME_CATEGORIES = {"anime_tv", "anime_movie"}


def _title_dir(p) -> str | None:
    """subtitles/<category>/<Title>/<file...> -> '<category>/<Title>'."""
    parts = p.relative_to(config.SUBTITLE_MIRROR_DIR).parts
    if len(parts) >= 3 and parts[0] == "subtitles" and parts[1] in ANIME_CATEGORIES:
        return f"{parts[1]}/{parts[2]}"
    return None


def clone_or_update() -> None:
    d = config.SUBTITLE_MIRROR_DIR
    if (d / ".git").exists():
        print(f"[subs] updating {d}")
        subprocess.run(["git", "-C", str(d), "pull", "--depth", "1", "--ff-only"], check=False)
    else:
        print(f"[subs] shallow-cloning {config.SUBTITLE_MIRROR_REPO} -> {d}")
        subprocess.run(["git", "clone", "--depth", "1", config.SUBTITLE_MIRROR_REPO, str(d)], check=True)


def _iter_files():
    d = config.SUBTITLE_MIRROR_DIR
    base = d / "subtitles"
    for cat in ANIME_CATEGORIES:
        cdir = base / cat
        if not cdir.exists():
            continue
        for p in cdir.rglob("*"):
            if p.suffix.lower() in (".srt", ".ass", ".ssa"):
                yield p


def parse_dialogue(path) -> list[str]:
    """Extract plain dialogue lines from .srt/.ass (best-effort, text only)."""
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    out = []
    if path.suffix.lower() in (".ass", ".ssa"):
        for line in raw.splitlines():
            if line.startswith("Dialogue:"):
                parts = line.split(",", 9)
                if len(parts) == 10:
                    txt = re.sub(r"\{[^}]*\}", "", parts[9])   # strip ASS override tags
                    out.append(txt.replace("\\N", " ").strip())
    else:  # srt
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.isdigit() or _TS.match(line) or "-->" in line:
                continue
            out.append(line)
    return out


def _language(lines: list[str]) -> str:
    """'jp' if the dialogue is predominantly CJK, else 'en'."""
    sample = " ".join(lines[:80])
    if not sample:
        return "en"
    cjk = len(_CJK.findall(sample))
    return "jp" if cjk >= 20 else "en"


def index() -> dict:
    d = config.SUBTITLE_MIRROR_DIR
    if not d.exists():
        return {"error": "mirror not cloned; run subtitles-prep first"}
    files = list(_iter_files())
    titles: dict = {}
    by_ext: dict = {}
    total_bytes = 0
    for p in files:
        td = _title_dir(p)
        if td:
            titles.setdefault(td, 0)
            titles[td] += 1
        by_ext[p.suffix.lower()] = by_ext.get(p.suffix.lower(), 0) + 1
        try:
            total_bytes += p.stat().st_size
        except OSError:
            pass
    return {"anime_titles": len(titles), "files": len(files), "by_ext": by_ext,
            "total_mb": round(total_bytes / 1e6, 1)}


def estimate(sample_files: int = 400) -> dict:
    """Scan a random sample: report language split + an English-proxy candidate rate,
    then project Layer-C adjudication cost as a RANGE. Japanese subs need a JP pipeline
    (deferred), so the JP portion uses the EN per-episode occupation rate as a proxy."""
    files = list(_iter_files())
    if not files:
        return {"error": "no subtitle files; run subtitles-prep first"}
    sample = random.sample(files, min(sample_files, len(files)))
    n_jp = n_en = scanned = 0
    en_lines = en_amb = 0
    for p in sample:
        lines = parse_dialogue(p)
        if not lines:
            continue
        scanned += 1
        lang = _language(lines)
        if lang == "jp":
            n_jp += 1
            continue
        n_en += 1
        en_lines += len(lines)
        seen = set()
        for ln in lines:
            for kind, key, term, amb in extract.scan(ln):
                if amb and (kind, key) not in seen:   # ~one adjudication per occ per episode
                    seen.add((kind, key)); en_amb += 1
    per_file_amb = (en_amb / n_en) if n_en else 0.0
    n_files = len(files)
    projected = n_files * per_file_amb                 # EN-rate proxy applied to all episodes
    cost = projected * 0.0003                           # measured Haiku batched per-call
    return {
        "files_total": n_files,
        "sample_scanned": scanned,
        "language_split_sample": {"japanese": n_jp, "english": n_en,
                                  "pct_japanese": round(100 * n_jp / scanned, 1) if scanned else 0},
        "english_avg_lines_per_file": round(en_lines / n_en, 1) if n_en else 0,
        "english_ambiguous_candidates_per_file": round(per_file_amb, 2),
        "projected_ambiguous_candidates_en_proxy": int(projected),
        "projected_batched_cost_usd_en_proxy": round(cost, 2),
        "caveat": ("Mirror is predominantly Japanese; the EN rate is a proxy for the JP portion. "
                   "Layer C also needs a JP tokenizer + JP occupation lexicon (deferred) and "
                   "title->AniList id matching. Treat as an order-of-magnitude range."),
    }


# Minimal Japanese occupation terms — for SIZING Layer C only (substring match, no
# tokenizer). Noisy on purpose; the real run needs MeCab/fugashi + a full JP lexicon.
JP_TERMS = [
    "医者", "医師", "看護師", "先生", "教師", "教授", "弁護士", "裁判官", "警察", "刑事",
    "探偵", "兵士", "軍人", "社長", "会長", "部長", "店長", "記者", "作家", "漫画家",
    "画家", "歌手", "音楽家", "俳優", "声優", "アイドル", "料理人", "シェフ", "コック",
    "パイロット", "運転手", "運転士", "船長", "農家", "漁師", "大工", "鍛冶", "整備士",
    "メイド", "執事", "秘書", "店員", "美容師", "消防士", "科学者", "研究者", "技師",
    "会計士", "薬剤師", "獣医", "歯科医", "保育士", "宇宙飛行士",
    # fantasy stratum
    "忍者", "侍", "騎士", "魔法使い", "暗殺者", "傭兵", "海賊", "冒険者", "王女", "姫",
]


def jp_estimate(sample_titles: int = 40) -> dict:
    """Sample whole titles, JP-substring-scan every episode, and bound Layer-C adjudication
    calls two ways: per (title x occupation) [dedup, lower bound] and per (episode x occupation)
    [full evidence, upper bound]."""
    from collections import defaultdict
    by_title = defaultdict(list)
    for p in _iter_files():
        td = _title_dir(p)
        if td:
            by_title[td].append(p)
    all_titles = list(by_title)
    if not all_titles:
        return {"error": "no anime subtitle files"}
    chosen = random.sample(all_titles, min(sample_titles, len(all_titles)))

    title_distinct = []       # distinct occupations per title
    ep_distinct_total = 0     # sum over episodes of distinct occupations in that episode
    ep_count = 0
    for t in chosen:
        occ_in_title = set()
        for p in by_title[t]:
            lines = parse_dialogue(p)
            if not lines:
                continue
            ep_count += 1
            text = "".join(lines)
            hit = {term for term in JP_TERMS if term in text}
            ep_distinct_total += len(hit)
            occ_in_title |= hit
        title_distinct.append(len(occ_in_title))

    n_titles = len(by_title)
    n_files = sum(len(v) for v in by_title.values())
    avg_per_title = (sum(title_distinct) / len(title_distinct)) if title_distinct else 0
    avg_per_ep = (ep_distinct_total / ep_count) if ep_count else 0
    lower_calls = n_titles * avg_per_title
    upper_calls = n_files * avg_per_ep
    return {
        "anime_titles": n_titles, "episode_files": n_files,
        "sampled_titles": len(chosen), "sampled_episodes": ep_count,
        "avg_distinct_occ_per_title": round(avg_per_title, 2),
        "avg_distinct_occ_per_episode": round(avg_per_ep, 2),
        "lower_bound": {"granularity": "title x occupation (dedup)",
                        "adjudication_calls": int(lower_calls),
                        "batched_cost_usd": round(lower_calls * 0.0003, 2)},
        "upper_bound": {"granularity": "episode x occupation (full evidence)",
                        "adjudication_calls": int(upper_calls),
                        "batched_cost_usd": round(upper_calls * 0.0003, 2)},
        "caveat": ("JP substring match, no tokenizer -> noisy (over- and under-counts). Real "
                   "Layer C needs MeCab/fugashi + a full JP lexicon and title->AniList matching. "
                   "Order-of-magnitude only."),
    }


def prep() -> None:
    clone_or_update()
    import json
    print("[subs] index:", json.dumps(index(), indent=2))
    print("[subs] JP estimate:", json.dumps(jp_estimate(), indent=2))
