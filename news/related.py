"""
Compute cross-related news links using Jaccard similarity on headline tokens.

Runs entirely in memory across the current 12h window (~50-200 items).
Same-ticker pairs are automatically considered related (score = 1.0).
Stores top-5 related IDs per item as a JSON string in NewsItem.related_ids.
"""
from __future__ import annotations

import json
import re
import string
from typing import Optional

_STOP_WORDS = {
    # English
    "a","an","the","and","or","but","in","on","at","to","for","of","with",
    "is","are","was","were","be","been","being","have","has","had","will",
    "would","could","should","may","might","do","does","did","not","from",
    "by","as","up","it","its","this","that","these","those","he","she","they",
    "we","you","i","their","our","your","my","his","her","stock","shares",
    "market","says","news","report","today","new","after","amid",
    # Chinese stop words
    "的","了","在","是","我","有","和","就","不","人","都","一","一個","上","也",
    "很","到","說","要","去","你","會","著","沒有","看","好","自己","這","那",
}


def _tokenize(text: str) -> set[str]:
    text = text.lower()
    # Remove punctuation and CJK/ASCII split
    text = re.sub(r"[^\w一-鿿\s]", " ", text)
    tokens = set(text.split())
    return tokens - _STOP_WORDS


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union > 0 else 0.0


def compute_related_ids(
    items: list[dict],
    top_k: int = 5,
    min_score: float = 0.15,
) -> dict[int, list[int]]:
    """
    Given a list of {id, ticker, headline} dicts, return {id: [related_id, ...]}.

    Scores same-ticker pairs at 1.0. Otherwise uses Jaccard on tokenised headlines.
    Only pairs above min_score are included; result is capped at top_k per item.
    """
    if not items:
        return {}

    token_sets = {item["id"]: _tokenize(item["headline"]) for item in items}
    result: dict[int, list[tuple[float, int]]] = {item["id"]: [] for item in items}

    for i, a in enumerate(items):
        for b in items[i + 1:]:
            if a["id"] == b["id"]:
                continue

            same_ticker = (
                a.get("ticker") is not None
                and a.get("ticker") == b.get("ticker")
            )
            score = 1.0 if same_ticker else _jaccard(token_sets[a["id"]], token_sets[b["id"]])

            if score >= min_score:
                result[a["id"]].append((score, b["id"]))
                result[b["id"]].append((score, a["id"]))

    return {
        item_id: [rid for _, rid in sorted(pairs, reverse=True)[:top_k]]
        for item_id, pairs in result.items()
    }


def related_ids_json(related: list[int]) -> Optional[str]:
    return json.dumps(related) if related else None
