"""ISCO-08 hierarchy + renderable/fantasy overlay.

Codes are self-describing: major = digit 1, sub-major = 2 digits, minor = 3, unit = 4.
Parents are derived by truncation, so any unit rolls up for free (§2 store-fine-report-up).
"""
from __future__ import annotations
import json
from functools import lru_cache

from . import config
from .lexicon import LEXICON, NOTES, FANTASY


@lru_cache(maxsize=1)
def _nodes() -> dict[str, dict]:
    data = json.loads(config.ISCO_JSON.read_text(encoding="utf-8"))
    return {n["code"]: n for n in data}


def title(code: str) -> str:
    n = _nodes().get(code)
    return n["title"] if n else f"<unknown {code}>"


def all_units() -> list[dict]:
    """The 436 unit groups, in canonical order."""
    return [n for n in _nodes().values() if n["level"] == "unit"]


def rollup(unit_code: str) -> dict:
    """Full ancestry for a 4-digit unit code, codes + titles at every level."""
    major, submajor, minor = unit_code[0], unit_code[:2], unit_code[:3]
    return {
        "unit_code": unit_code, "unit_title": title(unit_code),
        "minor_code": minor, "minor_title": title(minor),
        "submajor_code": submajor, "submajor_title": title(submajor),
        "major_code": major, "major_title": title(major),
    }


def is_renderable(unit_code: str) -> bool:
    """A unit group we actively search for. Zero here == genuine absence-from-anime.
    A zero for a non-renderable group just means it was never testable."""
    return unit_code in LEXICON


def note(unit_code: str) -> str | None:
    return NOTES.get(unit_code)


def validate() -> list[str]:
    """Return a list of problems (empty == clean). Every lexicon code must be a real unit."""
    problems = []
    nodes = _nodes()
    for code in LEXICON:
        n = nodes.get(code)
        if n is None:
            problems.append(f"LEXICON code {code} not in ISCO-08")
        elif n["level"] != "unit":
            problems.append(f"LEXICON code {code} is a {n['level']}, not a unit group")
    for code in NOTES:
        if code not in LEXICON:
            problems.append(f"NOTES code {code} not in LEXICON")
    return problems


def summary() -> dict:
    units = all_units()
    renderable = [u for u in units if is_renderable(u["code"])]
    return {
        "unit_groups": len(units),
        "renderable": len(renderable),
        "not_renderable": len(units) - len(renderable),
        "fantasy_terms": len(FANTASY),
        "lexicon_surface_forms": sum(len(t) for t, _ in LEXICON.values()),
    }
