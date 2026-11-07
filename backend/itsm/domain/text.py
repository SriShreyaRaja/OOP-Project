"""
Small, explainable text tools: tokenising, stop-word removal, ITSM synonym normalisation
("down", "failing", "unable" all mean an outage) and Jaccard similarity.
Member 4 can build smarter detectors (TF-IDF, embeddings) on top of `tokens`.
"""
from __future__ import annotations

import re

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "is", "are", "to", "of", "and", "or", "in", "on", "for", "not", "my", "our",
    "we", "i", "it", "be", "can", "cannot", "with", "users", "user", "make", "complete", "this",
    "that", "from", "at", "has", "have", "all", "every", "again", "too", "us",
}
_SYNONYMS = {
    "unavailable": "outage", "down": "outage", "failing": "outage", "fails": "outage",
    "failed": "outage", "unable": "outage", "error": "outage", "broken": "outage",
    "crash": "outage", "crashes": "outage", "unreachable": "outage", "working": "outage",
    "transaction": "payment", "transactions": "payment", "payments": "payment", "pay": "payment",
    "signin": "login", "logon": "login", "password": "login",
    "wifi": "network", "internet": "network", "vpn": "network",
}


def raw_words(text: str | None) -> set[str]:
    """Lower-case words, no filtering."""
    return set(_WORD.findall((text or "").lower()))


def tokens(text: str | None) -> set[str]:
    """Meaningful, normalised tokens."""
    return {_SYNONYMS.get(w, w) for w in raw_words(text) if len(w) > 1 and w not in _STOP}


def jaccard(a: str, b: str) -> float:
    """|A ∩ B| / |A ∪ B|: 0 = nothing shared, 1 = identical."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
