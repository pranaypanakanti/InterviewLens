"""Client for the self-hosted SearXNG metasearch JSON API."""
import logging

import httpx

from ..config import settings

log = logging.getLogger("interviewlens.searxng")


async def search(query: str, max_results: int | None = None) -> list[dict]:
    """Run one query; returns [{title, url, content}] (empty list on any failure)."""
    max_results = max_results or settings.RESULTS_PER_QUERY
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"{settings.SEARXNG_URL.rstrip('/')}/search",
                params={
                    "q": query,
                    "format": "json",
                    "categories": "general",
                    "language": "en",
                    "safesearch": 0,
                },
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
    except Exception as exc:
        log.warning("SearXNG query failed (%s): %s", query, exc)
        return []
    out = []
    for r in results[:max_results]:
        url = r.get("url")
        if not url or not url.startswith("http"):
            continue
        out.append(
            {
                "title": (r.get("title") or "").strip(),
                "url": url,
                "content": (r.get("content") or "").strip(),
            }
        )
    return out


async def health() -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.SEARXNG_URL.rstrip('/')}/search",
                params={"q": "test", "format": "json"},
            )
        if resp.status_code == 403:
            return {
                "reachable": True,
                "json_api": False,
                "error": "SearXNG returned 403 — enable 'json' in search.formats in settings.yml",
            }
        resp.raise_for_status()
        return {"reachable": True, "json_api": True}
    except Exception as exc:
        return {"reachable": False, "json_api": False, "error": str(exc)}
