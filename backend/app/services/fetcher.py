"""Polite async page fetching + clean-text extraction (trafilatura)."""
import asyncio
import logging
import urllib.robotparser
from urllib.parse import urlsplit

import httpx
import trafilatura

from ..config import settings

log = logging.getLogger("interviewlens.fetcher")

HEADERS = {
    "User-Agent": settings.USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_robots_lock = asyncio.Lock()


async def _robots_allows(client: httpx.AsyncClient, url: str) -> bool:
    """Best-effort robots.txt check; failure to fetch robots.txt means allow."""
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    async with _robots_lock:
        if origin not in _robots_cache:
            rp = urllib.robotparser.RobotFileParser()
            try:
                resp = await client.get(f"{origin}/robots.txt", timeout=6.0)
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                    _robots_cache[origin] = rp
                else:
                    _robots_cache[origin] = None  # no usable robots.txt -> allow
            except Exception:
                _robots_cache[origin] = None
        rp = _robots_cache[origin]
    if rp is None:
        return True
    try:
        return rp.can_fetch(settings.USER_AGENT, url)
    except Exception:
        return True


async def fetch_clean_text(client: httpx.AsyncClient, url: str) -> str | None:
    """Fetch one URL and return clean article text, or None on any block/failure."""
    try:
        if not await _robots_allows(client, url):
            log.info("robots.txt disallows %s — skipping", url)
            return None
        resp = await client.get(url, timeout=15.0, follow_redirects=True)
        if resp.status_code != 200:
            log.info("Skipping %s (HTTP %s)", url, resp.status_code)
            return None
        ctype = resp.headers.get("content-type", "")
        if "html" not in ctype and "xml" not in ctype:
            return None
        html = resp.text[:2_000_000]
        text = trafilatura.extract(html, url=url, include_comments=True)
        if text and len(text.strip()) >= 200:
            return text.strip()
        return None
    except Exception as exc:
        log.info("Skipping %s (%s)", url, type(exc).__name__)
        return None


async def fetch_many(urls: list[str], on_progress=None) -> dict[str, str]:
    """Fetch URLs with bounded concurrency. Returns {url: clean_text} for successes."""
    sem = asyncio.Semaphore(settings.FETCH_CONCURRENCY)
    results: dict[str, str] = {}
    done = 0

    async with httpx.AsyncClient(headers=HEADERS) as client:

        async def one(url: str):
            nonlocal done
            async with sem:
                text = await fetch_clean_text(client, url)
            if text:
                results[url] = text
            done += 1
            if on_progress:
                await on_progress(done, len(urls), len(results))

        await asyncio.gather(*(one(u) for u in urls))
    return results
