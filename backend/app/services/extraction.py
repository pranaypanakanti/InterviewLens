"""LLM extraction stages: JD/resume entities, per-document interview questions,
and labeled generic fallback questions."""
import logging

from ..config import settings
from .ollama import ollama

log = logging.getLogger("interviewlens.extraction")

CATEGORIES = [
    "technical",
    "coding",
    "system-design",
    "behavioral",
    "role-specific",
    "domain-knowledge",
]

JD_SCHEMA = {
    "type": "object",
    "properties": {
        "company": {"type": "string"},
        "job_title": {"type": "string"},
        "seniority": {"type": "string"},
        "key_skills": {"type": "array", "items": {"type": "string"}},
        "location": {"type": "string"},
        "domain": {"type": "string"},
    },
    "required": ["company", "job_title", "seniority", "key_skills", "location", "domain"],
}

RESUME_SCHEMA = {
    "type": "object",
    "properties": {
        "candidate_skills": {"type": "array", "items": {"type": "string"}},
        "years_experience": {"type": "number"},
        "notable_projects": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["candidate_skills", "years_experience", "notable_projects"],
}

QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "confidence": {"type": "number"},
                },
                "required": ["question", "category", "confidence"],
            },
        }
    },
    "required": ["questions"],
}


async def extract_jd_entities(jd_text: str) -> dict:
    prompt = (
        "Extract structured facts from this job description. "
        "If a field is not stated, infer it if obvious, otherwise use an empty string "
        '(or empty list). Use "unknown" for company only if truly absent.\n\n'
        f"JOB DESCRIPTION:\n{jd_text[:6000]}"
    )
    data = await ollama.chat_json(
        settings.EXTRACT_MODEL,
        prompt,
        schema=JD_SCHEMA,
        system="You extract structured data from job descriptions. Respond with JSON only.",
    )
    data["key_skills"] = [s for s in data.get("key_skills", []) if isinstance(s, str)][:10]
    return data


async def extract_resume_entities(resume_text: str) -> dict:
    prompt = (
        "Extract structured facts from this resume.\n\n"
        f"RESUME:\n{resume_text[:6000]}"
    )
    data = await ollama.chat_json(
        settings.EXTRACT_MODEL,
        prompt,
        schema=RESUME_SCHEMA,
        system="You extract structured data from resumes. Respond with JSON only.",
    )
    data["candidate_skills"] = [s for s in data.get("candidate_skills", []) if isinstance(s, str)][:15]
    data["notable_projects"] = [p for p in data.get("notable_projects", []) if isinstance(p, str)][:6]
    return data


async def extract_questions_from_doc(
    doc_text: str, source_url: str, company: str, job_title: str
) -> list[dict]:
    """Pull actual interview questions out of one document. Returns [] on failure."""
    prompt = (
        f"The document below discusses interview experiences/questions, possibly for "
        f"{company or 'a company'} — {job_title or 'a role'}.\n"
        "Extract ONLY actual interview questions that were asked or are reported as commonly "
        "asked. Rewrite each as a clean, self-contained question. Ignore marketing fluff, "
        "navigation text, and generic advice. If there are no real interview questions, "
        "return an empty list.\n"
        "For each question give: category (one of technical, coding, system-design, "
        "behavioral, role-specific, domain-knowledge) and confidence (0.0-1.0 that this "
        "was really asked in an interview).\n\n"
        f"DOCUMENT:\n{doc_text[: settings.MAX_DOC_CHARS]}"
    )
    try:
        data = await ollama.chat_json(
            settings.EXTRACT_MODEL,
            prompt,
            schema=QUESTIONS_SCHEMA,
            system="You extract interview questions from web pages. Respond with JSON only.",
        )
    except Exception as exc:
        log.warning("Question extraction failed for %s: %s", source_url, exc)
        return []
    out = []
    for q in data.get("questions", []):
        text = (q.get("question") or "").strip()
        if len(text) < 12 or len(text) > 400:
            continue
        out.append(
            {
                "question": text,
                "category": q.get("category") if q.get("category") in CATEGORIES else "role-specific",
                "confidence": max(0.0, min(1.0, float(q.get("confidence", 0.5)))),
                "source_url": source_url,
                "is_generic": False,
            }
        )
    return out


async def generate_generic_questions(jd_entities: dict, count: int) -> list[dict]:
    """Fallback: role- and skill-based questions, clearly labeled, no fabricated sources."""
    skills = ", ".join(jd_entities.get("key_skills", [])[:8]) or "the role's core skills"
    prompt = (
        f"Generate {count} realistic interview questions for this role:\n"
        f"- Title: {jd_entities.get('job_title', 'unknown')}\n"
        f"- Seniority: {jd_entities.get('seniority', 'unknown')}\n"
        f"- Domain: {jd_entities.get('domain', 'unknown')}\n"
        f"- Key skills: {skills}\n\n"
        "Mix categories (technical, coding, system-design, behavioral, role-specific, "
        "domain-knowledge). These are generic role/skill questions — do NOT pretend they "
        "came from a specific company. Confidence should reflect how commonly such a "
        "question is asked for this role."
    )
    try:
        data = await ollama.chat_json(
            settings.EXTRACT_MODEL,
            prompt,
            schema=QUESTIONS_SCHEMA,
            system="You write realistic interview questions. Respond with JSON only.",
            temperature=0.6,
        )
    except Exception as exc:
        log.warning("Generic question generation failed: %s", exc)
        return []
    out = []
    for q in data.get("questions", [])[:count]:
        text = (q.get("question") or "").strip()
        if len(text) < 12:
            continue
        out.append(
            {
                "question": text,
                "category": q.get("category") if q.get("category") in CATEGORIES else "role-specific",
                "confidence": max(0.0, min(1.0, float(q.get("confidence", 0.5)))),
                "source_url": "",
                "is_generic": True,
            }
        )
    return out
