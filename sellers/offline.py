"""Offline processing (no network): used when no LLM provider is configured and inside
the ``--network=none`` worker container. Deterministic, so results are reproducible."""

from __future__ import annotations

import json
import re

_KEYWORDS = {
    "legal": ["contract", "agreement", "court", "plaintiff", "defendant", "clause", "liability", "statute", "attorney", "lawsuit"],
    "medical": ["patient", "diagnosis", "clinical", "treatment", "symptom", "dose", "hospital", "disease", "therapy", "medication"],
    "financial": ["revenue", "invoice", "profit", "loss", "interest", "loan", "equity", "budget", "payment", "tax", "sats", "bitcoin"],
}


def summarize(text: str, max_points: int = 6) -> str:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if len(s.strip()) > 2]
    if not sentences:
        return "- (empty input)"
    words = re.findall(r"[a-z']+", text.lower())
    freq: dict[str, int] = {}
    for w in words:
        if len(w) > 3:
            freq[w] = freq.get(w, 0) + 1
    scored = sorted(range(len(sentences)),
                    key=lambda i: -sum(freq.get(w, 0) for w in re.findall(r"[a-z']+", sentences[i].lower())))
    keep = sorted(scored[:max_points])
    return "\n".join(f"- {sentences[i][:300]}" for i in keep)


def classify(text: str) -> str:
    low = text.lower()
    scores = {label: sum(low.count(k) for k in kws) for label, kws in _KEYWORDS.items()}
    label, hits = max(scores.items(), key=lambda kv: kv[1])
    total = sum(scores.values())
    if hits == 0:
        return json.dumps({"label": "general", "confidence": 0.5, "rationale": "no domain keywords found (offline classifier)"}, indent=2)
    return json.dumps({"label": label, "confidence": round(hits / total, 2),
                       "rationale": f"{hits} {label} keyword hit(s) (offline classifier)"}, indent=2)


def translate(text: str) -> str:
    """No translator is available offline, so say so instead of faking a translation."""
    from sellers.llm_client import parse_translation_input

    try:
        body, _direction = parse_translation_input(text)
    except Exception:  # noqa: BLE001
        body = text
    return f"[offline demo translation]\n{body}"
