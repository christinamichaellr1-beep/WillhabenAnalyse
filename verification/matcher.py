"""Fuzzy matcher for verifying EventCandidate results against a query."""
from __future__ import annotations
import datetime
import re
from dataclasses import dataclass

from verification.clients.base import EventCandidate


@dataclass
class MatchResult:
    candidate: EventCandidate
    name_score: float       # 0.0–1.0 fuzzy name similarity
    date_score: float       # 1.0 if exact, 0.5 if ±7 days, 0.0 if mismatch / no date
    city_score: float       # 1.0 exact, 0.5 partial, 0.0 mismatch / no city
    total_score: float      # weighted average


def _normalize(text: str) -> str:
    """Lowercase, remove punctuation and extra spaces."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _name_similarity(a: str, b: str) -> float:
    """
    Token-based Jaccard similarity between two normalized strings.

    Steps:
    1. Normalize both strings
    2. Split into tokens (words)
    3. Return |intersection| / |union| (Jaccard coefficient)

    Returns 0.0 if either string is empty after normalization.
    """
    na = set(_normalize(a).split())
    nb = set(_normalize(b).split())
    if not na or not nb:
        return 0.0
    return len(na & nb) / len(na | nb)


def _date_score(query_date: datetime.date | None, candidate_date: datetime.date | None) -> float:
    """
    1.0  — exact match
    0.5  — within 7 days (flexible for tour dates)
    0.0  — mismatch or one/both dates missing
    """
    if query_date is None or candidate_date is None:
        return 0.0
    delta = abs((query_date - candidate_date).days)
    if delta == 0:
        return 1.0
    if delta <= 7:
        return 0.5
    return 0.0


def _city_score(query_city: str | None, candidate_city: str | None) -> float:
    """
    1.0  — exact match (case-insensitive)
    0.5  — one is substring of the other
    0.0  — mismatch or missing
    """
    if not query_city or not candidate_city:
        return 0.0
    a = query_city.lower().strip()
    b = candidate_city.lower().strip()
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.5
    return 0.0


def _weighted_total(name: float, date: float, city: float) -> float:
    """Weight: name=0.5, date=0.3, city=0.2"""
    return round(name * 0.5 + date * 0.3 + city * 0.2, 4)


def match(
    query_name: str,
    query_date: datetime.date | None,
    query_city: str | None,
    candidates: list[EventCandidate],
    min_name_score: float = 0.3,
) -> MatchResult | None:
    """
    Find the best-matching candidate.

    Returns None if candidates is empty or no candidate has name_score >= min_name_score.
    Returns the MatchResult with the highest total_score otherwise.
    """
    if not candidates:
        return None

    best: MatchResult | None = None
    for cand in candidates:
        ns = _name_similarity(query_name, cand.event_name)
        if ns < min_name_score:
            continue
        ds = _date_score(query_date, cand.event_datum)
        cs = _city_score(query_city, cand.stadt)
        total = _weighted_total(ns, ds, cs)
        mr = MatchResult(candidate=cand, name_score=ns, date_score=ds, city_score=cs, total_score=total)
        if best is None or total > best.total_score:
            best = mr

    return best
