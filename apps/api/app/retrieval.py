"""Small in-memory two-channel keyword ranker over active MD/TXT chunks.

This is a diagnostic retrieval baseline, not a model answer or confidence score.
"""

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import jieba

from app.knowledge_store import StoredChunk, knowledge_base_exists, list_active_chunks


_WORD = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u9fff]+")
jieba.setLogLevel(logging.WARNING)


@dataclass(frozen=True)
class SearchHit:
    chunk: StoredChunk
    score: float


def tokenize(text: str) -> list[str]:
    """Original channel: lowercase Latin words and overlapping Chinese pairs."""
    terms: list[str] = []
    for match in _WORD.finditer(text):
        word = match.group()
        if word[0].isascii():
            terms.append(word.casefold())
        elif len(word) == 1:
            terms.append(word)
        else:
            terms.extend(word[index : index + 2] for index in range(len(word) - 1))
    return terms


def _search_words(text: str) -> list[str]:
    """Second channel: words that keep meaning better than cross-word pairs."""
    terms: list[str] = []
    for match in _WORD.finditer(text):
        word = match.group()
        if word[0].isascii():
            terms.append(word.casefold())
        elif len(word) == 1:
            terms.append(word)
        else:
            terms.extend(segment for segment in jieba.cut_for_search(word) if len(segment) >= 2)
    return terms


def _bm25_scores(term_counts: list[Counter[str]], query_terms: set[str]) -> list[float]:
    """Score one tokenization channel; its scale is only for ranking."""
    lengths = [sum(counts.values()) for counts in term_counts]
    average_length = max(sum(lengths) / len(lengths), 1.0)
    document_frequency = Counter(term for counts in term_counts for term in counts)
    total_chunks = len(term_counts)
    k1, b = 1.2, 0.75
    scores: list[float] = []
    for counts, length in zip(term_counts, lengths, strict=True):
        score = 0.0
        for term in query_terms:
            frequency = counts[term]
            if frequency == 0:
                continue
            matching_chunks = document_frequency[term]
            inverse_frequency = math.log(
                1 + (total_chunks - matching_chunks + 0.5) / (matching_chunks + 0.5)
            )
            saturation = frequency * (k1 + 1) / (
                frequency + k1 * (1 - b + b * length / average_length)
            )
            score += inverse_frequency * saturation
        scores.append(score)
    return scores


def search_knowledge_base(
    database_path: Path,
    kb_id: str,
    query: str,
    *,
    limit: int = 5,
) -> list[SearchHit]:
    """Rank only current chunks from one knowledge base; return no zero matches."""
    if not query.strip():
        raise ValueError("Search query must not be empty")
    if not 1 <= limit <= 20:
        raise ValueError("Search limit must be between 1 and 20")
    if not knowledge_base_exists(database_path, kb_id):
        raise ValueError(f"Unknown knowledge base: {kb_id}")

    pair_terms = set(tokenize(query))
    word_terms = set(_search_words(query))
    if not pair_terms and not word_terms:
        return []

    chunks = list_active_chunks(database_path, kb_id)
    if not chunks:
        return []

    # Keep the stored text untouched so returned offsets and lines stay exact.
    pair_counts = [Counter(tokenize(chunk.content) + tokenize(chunk.heading)) for chunk in chunks]
    word_counts = [Counter(_search_words(chunk.content) + _search_words(chunk.heading)) for chunk in chunks]
    pair_scores = _bm25_scores(pair_counts, pair_terms)
    word_scores = _bm25_scores(word_counts, word_terms)
    hits: list[SearchHit] = []
    for chunk, pair_score, word_score in zip(chunks, pair_scores, word_scores, strict=True):
        score = pair_score + word_score
        if score > 0:
            hits.append(SearchHit(chunk, score))

    hits.sort(
        key=lambda hit: (
            -hit.score, hit.chunk.relative_path, hit.chunk.chunk_no
        )
    )
    return hits[:limit]
