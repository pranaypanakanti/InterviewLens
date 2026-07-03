"""The research pipeline: parse → extract → search → fetch → question-extract →
cluster → answer-generate → store. Publishes SSE progress throughout."""
import asyncio
import hashlib
import logging
import time

from . import db
from .config import settings
from .jobs import Job
from .services import searxng
from .services.answers import generate_answer
from .services.clustering import cluster_and_rank
from .services.extraction import (
    extract_jd_entities,
    extract_questions_from_doc,
    extract_resume_entities,
    generate_generic_questions,
)
from .services.fetcher import fetch_many
from .services.parsing import parse_resume

log = logging.getLogger("interviewlens.pipeline")


def build_queries(entities: dict) -> list[str]:
    company = entities.get("company", "").strip()
    title = entities.get("job_title", "").strip()
    seniority = entities.get("seniority", "").strip()
    skills = entities.get("key_skills", [])
    queries: list[str] = []
    if company and company.lower() != "unknown":
        queries += [
            f'"{company}" "{title}" interview questions',
            f"{company} {title} interview experience",
            f"{company} interview questions site:ambitionbox.com",
            f"{company} {title} interview site:reddit.com",
            f"{company} interview questions site:teamblind.com",
            f"{company} {title} interview questions site:geeksforgeeks.org",
            f"{company} interview questions site:glassdoor.com",
        ]
    # Skill fallbacks always included so low-data companies still get material.
    for skill in skills[:3]:
        queries.append(f"{skill} interview questions {seniority} {title}".strip())
    if title:
        queries.append(f"{title} {seniority} common interview questions".strip())
    return queries


_LEGAL_SUFFIXES = {"pvt", "ltd", "inc", "llc", "limited", "corp", "corporation", "co", "gmbh", "plc"}


def _company_needle(company: str) -> str:
    """Normalized company name without legal suffixes, for mention detection."""
    words = [w for w in company.lower().replace(",", " ").replace(".", " ").split()]
    while words and words[-1] in _LEGAL_SUFFIXES:
        words.pop()
    return " ".join(words)


async def run_pipeline(
    job: Job,
    jd_text: str,
    resume_filename: str,
    resume_bytes: bytes,
    mode: str,
    force: bool,
):
    started = time.time()
    try:
        await _run(job, jd_text, resume_filename, resume_bytes, mode, force, started)
    except Exception as exc:
        log.exception("Pipeline failed")
        await job.fail(f"Research failed: {exc}")


async def _run(job, jd_text, resume_filename, resume_bytes, mode, force, started):
    # 1. Parse inputs -----------------------------------------------------
    await job.publish("parsing", "Parsing resume and job description…", 3)
    resume_text = parse_resume(resume_filename, resume_bytes)

    # 2. Entity extraction (with hash cache for instant re-runs) ----------
    await job.publish("entities", "Extracting company, role and skills…", 8)
    input_hash = hashlib.sha256(
        jd_text.strip().encode() + b"\x00" + resume_text.strip().encode()
    ).hexdigest()
    cached_entities = db.get_cached_entities(input_hash)
    if cached_entities:
        jd_entities, resume_entities = cached_entities["jd"], cached_entities["resume"]
    else:
        jd_entities = await extract_jd_entities(jd_text)
        resume_entities = await extract_resume_entities(resume_text)
        db.save_entities(input_hash, {"jd": jd_entities, "resume": resume_entities})

    company = jd_entities.get("company", "") or "unknown"
    title = jd_entities.get("job_title", "") or "unknown"
    await job.publish(
        "entities", f"Detected: {company} — {title}", 12, company=company, job_title=title
    )

    # 3. Cache check -------------------------------------------------------
    if not force:
        cached = db.get_cached_run(company, title, mode)
        if cached:
            cached["from_cache"] = True
            await job.publish("cache", "Found a cached research run for this company + role", 95)
            await job.finish(cached)
            return

    # 4. Search ------------------------------------------------------------
    queries = build_queries(jd_entities)
    await job.publish("searching", f"Searching the web… 0/{len(queries)} queries", 15)
    all_results: dict[str, dict] = {}  # url -> result
    for i, q in enumerate(queries, 1):
        if i > 1:
            await asyncio.sleep(1.0)  # politeness gap so upstream engines don't throttle
        for r in await searxng.search(q):
            all_results.setdefault(r["url"], r)
        await job.publish(
            "searching",
            f"Searching the web… {i}/{len(queries)} queries ({len(all_results)} results)",
            15 + int(15 * i / len(queries)),
            partial_counts={"results": len(all_results)},
        )

    # Prioritize community sources known to be scrapeable and rich.
    def source_score(url: str) -> int:
        u = url.lower()
        for rank, dom in enumerate(
            ["ambitionbox.com", "geeksforgeeks.org", "interviewbit.com", "reddit.com",
             "teamblind.com", "medium.com", "github.io", "indeed.com"]
        ):
            if dom in u:
                return rank
        if "glassdoor.com" in u or "linkedin.com" in u:
            return 99  # will almost certainly block; rely on snippet only
        return 50

    urls_to_fetch = sorted(all_results, key=source_score)[: settings.MAX_FETCH_DOCS]

    # 5. Fetch + clean-text extraction --------------------------------------
    await job.publish("reading", f"Reading sources… 0/{len(urls_to_fetch)}", 30)

    async def fetch_progress(done, total, ok):
        await job.publish(
            "reading",
            f"Reading sources… {done}/{total} ({ok} readable)",
            30 + int(15 * done / max(total, 1)),
            partial_counts={"readable": ok},
        )

    fetched = await fetch_many(urls_to_fetch, on_progress=fetch_progress)

    # Unfetchable-but-relevant results still count as weak snippet evidence.
    snippet_docs: list[tuple[str, str]] = []
    for url, r in all_results.items():
        if url in fetched:
            continue
        blob = f"{r['title']}. {r['content']}"
        if "interview" in blob.lower() and len(r["content"]) > 60:
            snippet_docs.append((url, blob))
    snippet_docs = snippet_docs[: settings.MAX_SNIPPET_DOCS]

    # 6. Question extraction -------------------------------------------------
    docs = [(url, text) for url, text in fetched.items()] + snippet_docs
    # Company-mention detection: a source only counts as company-reported
    # evidence if its text (or title/snippet) actually names the company.
    needle = _company_needle(company) if company.lower() != "unknown" else ""
    mentions_company: dict[str, bool] = {}
    for url, text in docs:
        blob = f"{all_results.get(url, {}).get('title', '')} {text}".lower()
        mentions_company[url] = bool(needle) and needle in blob
    raw_questions: list[dict] = []
    for i, (url, text) in enumerate(docs, 1):
        raw_questions += await extract_questions_from_doc(text, url, company, title)
        await job.publish(
            "questions",
            f"Finding common questions… {len(raw_questions)} found ({i}/{len(docs)} sources)",
            45 + int(20 * i / max(len(docs), 1)),
            partial_counts={"questions": len(raw_questions)},
        )

    # 7. Dedupe + rank ---------------------------------------------------------
    await job.publish("ranking", "Clustering duplicates and ranking by frequency…", 66)
    ranked = await cluster_and_rank(raw_questions)

    # 8. Fallback top-up: never return fewer than MIN_QUESTIONS ---------------
    # "Limited data" means few sources actually name the company — skill-based
    # sources are real evidence for the role, but not company-reported.
    for q in ranked:
        q["company_reported"] = any(mentions_company.get(u, False) for u in q["sources"])
    limited_data = len([q for q in ranked if q["company_reported"]]) < 8
    if len(ranked) < settings.MIN_QUESTIONS:
        need = settings.MIN_QUESTIONS - len(ranked) + 2
        await job.publish(
            "ranking",
            f"Limited public interview data — generating {need} role/skill-based questions…",
            70,
        )
        existing = {q["question"].lower() for q in ranked}
        for g in await generate_generic_questions(jd_entities, need):
            if g["question"].lower() not in existing:
                ranked.append(
                    {
                        "question": g["question"],
                        "category": g["category"],
                        "confidence": g["confidence"],
                        "frequency": 0,
                        "sources": [],
                        "is_generic": True,
                        "company_reported": False,
                    }
                )

    # 9. Answer generation -------------------------------------------------------
    total = len(ranked)
    await job.publish("answering", f"Writing tailored answers… 0/{total}", 72)
    answered = []
    for i, q in enumerate(ranked, 1):
        ans = await generate_answer(q, jd_entities, resume_text, resume_entities, mode)
        answered.append({**q, **ans})
        await job.publish(
            "answering",
            f"Writing tailored answers… {i}/{total}",
            72 + int(26 * i / max(total, 1)),
            partial_counts={"answered": i},
        )

    # 10. Store + return ------------------------------------------------------------
    result = {
        "company": company,
        "job_title": title,
        "seniority": jd_entities.get("seniority", ""),
        "mode": mode,
        "limited_data": limited_data,
        "sources_read": len(fetched),
        "snippet_sources": len(snippet_docs),
        "raw_question_count": len(raw_questions),
        "questions": answered,
        "duration_s": round(time.time() - started, 1),
        "from_cache": False,
    }
    if company != "unknown" and title != "unknown":
        db.save_run(company, title, mode, result)
    await job.finish(result)
