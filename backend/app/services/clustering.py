"""Dedupe + rank questions via nomic-embed-text embeddings and greedy cosine clustering."""
import logging
from urllib.parse import urlsplit

import numpy as np

from ..config import settings
from .ollama import ollama

log = logging.getLogger("interviewlens.clustering")


def _domain(url: str) -> str:
    try:
        host = urlsplit(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return url


async def cluster_and_rank(questions: list[dict]) -> list[dict]:
    """Cluster near-duplicate questions; frequency = distinct source domains.

    Returns ranked clusters: {question, category, frequency, confidence, sources[], is_generic}.
    """
    if not questions:
        return []
    texts = [q["question"] for q in questions]
    try:
        vectors = np.array(await ollama.embed(texts), dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors = vectors / np.clip(norms, 1e-8, None)
    except Exception as exc:
        log.warning("Embedding failed (%s) — falling back to exact-text dedupe", exc)
        vectors = None

    clusters: list[list[int]] = []
    if vectors is not None:
        centroids: list[np.ndarray] = []
        for i in range(len(questions)):
            placed = False
            for ci, centroid in enumerate(centroids):
                if float(np.dot(vectors[i], centroid)) >= settings.CLUSTER_THRESHOLD:
                    clusters[ci].append(i)
                    members = vectors[[*clusters[ci]]]
                    mean = members.mean(axis=0)
                    centroids[ci] = mean / max(float(np.linalg.norm(mean)), 1e-8)
                    placed = True
                    break
            if not placed:
                clusters.append([i])
                centroids.append(vectors[i])
    else:
        seen: dict[str, int] = {}
        for i, q in enumerate(questions):
            key = q["question"].lower().strip().rstrip("?")
            if key in seen:
                clusters[seen[key]].append(i)
            else:
                seen[key] = len(clusters)
                clusters.append([i])

    ranked = []
    for member_ids in clusters:
        members = [questions[i] for i in member_ids]
        rep = max(members, key=lambda q: q["confidence"])
        source_urls = sorted({m["source_url"] for m in members if m["source_url"]})
        domains = {_domain(u) for u in source_urls}
        ranked.append(
            {
                "question": rep["question"],
                "category": rep["category"],
                "confidence": round(max(m["confidence"] for m in members), 2),
                "frequency": max(len(domains), 1),
                "sources": source_urls,
                "is_generic": all(m["is_generic"] for m in members),
            }
        )
    ranked.sort(key=lambda c: (c["frequency"], c["confidence"]), reverse=True)
    return ranked[: settings.QUESTION_LIMIT]
