"""LLM extraction stages: JD/resume entities, per-document interview questions,
and labeled generic fallback questions."""
import logging
import re

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
        # Strip listing artifacts the model sometimes echoes: "- Q3. ..." etc.
        text = re.sub(r"^[-•*\s]*(?:Q\d+[.)]\s*)?", "", text).strip()
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


# "reason" comes first on purpose: forcing the model to write a one-sentence
# rationale before the boolean makes the small model's verdicts far more
# accurate than a bare boolean (verified: bare boolean was near-random).
RELEVANCE_SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {"type": "string"},
        "keep": {"type": "boolean"},
    },
    "required": ["reason", "keep"],
}


# Words a real question or coding task plausibly starts with. Used only for
# short, question-mark-less texts to separate tasks ("Reverse a linked list")
# from listing fragments ("DSA medium question").
_QUESTION_STARTERS = {
    "what", "why", "how", "when", "where", "which", "who", "can", "could", "would",
    "should", "do", "does", "did", "is", "are", "was", "have", "has", "explain",
    "describe", "design", "implement", "write", "tell", "give", "find", "reverse",
    "sort", "count", "sum", "check", "solve", "walk", "share", "name", "compare",
    "define", "list", "print", "merge", "detect", "build", "create",
}


def _looks_like_question(text: str) -> bool:
    if "?" in text or len(text.split()) >= 8:
        return True
    return text.split()[0].lower().strip("-•*") in _QUESTION_STARTERS


async def filter_relevant_questions(
    questions: list[dict], job_title: str, key_skills: list[str], domain: str = ""
) -> list[dict]:
    """Drop questions clearly unrelated to the target role (e.g. logistics questions
    for a software engineer). Judged one question at a time — small models are far
    more reliable on binary calls than on picking indices out of a list.
    Conservative: keeps everything on LLM failure, and refuses to trust a pass that
    wants to remove more than a third of the set."""
    if not questions or not job_title or job_title.lower() == "unknown":
        return questions
    # Deterministic pre-gate: drop listing fragments that aren't questions at all.
    candidates = []
    fragments = 0
    for q in questions:
        if _looks_like_question(q["question"]):
            candidates.append(q)
        else:
            fragments += 1
            log.info("Dropped non-question fragment: %s", q["question"][:100])
    questions = candidates
    if not questions:
        return questions
    skills = ", ".join(key_skills[:8])
    role_desc = f'"{job_title}"' + (f" ({domain})" if domain else "")
    system = (
        "You screen scraped interview questions for a candidate's prep sheet.\n"
        "KEEP: questions about the role's own field (even very basic ones), and "
        "behavioral/motivational/company-fit questions, which appear in every interview.\n"
        "REMOVE only: questions testing a DIFFERENT profession's field (e.g. logistics "
        "incoterms or nursing procedures asked of a software engineer); contentless "
        "filler like 'What is management?' or 'What is leadership?'; fragments or topic "
        "labels that are not actual questions ('Basic knowledge', 'DSA medium question'); "
        "and small-talk with no prep value ('What is your name?', 'Where are you from?').\n"
        "When unsure, keep. Give a one-sentence reason, then the keep verdict. JSON only."
    )
    verdicts: list[bool] = []
    for q in questions:
        prompt = (
            f"Candidate's target role: {role_desc}."
            + (f" Key skills: {skills}." if skills else "")
            + f"\n\nScraped question: \"{q['question']}\"\n\n"
            "Should this question be kept on the candidate's prep sheet?"
        )
        try:
            data = await ollama.chat_json(
                settings.EXTRACT_MODEL,
                prompt,
                schema=RELEVANCE_SCHEMA,
                system=system,
                temperature=0.0,
            )
            verdicts.append(bool(data.get("keep", True)))
        except Exception as exc:
            log.warning("Relevance check failed, keeping question: %s", exc)
            verdicts.append(True)

    removed = sum(1 for v in verdicts if not v)
    # Sanity guard against a malfunctioning judge. Threshold is deliberately high:
    # junk-heavy batches are real (company pages that mix every profession's
    # questions), so only a pass that guts most of the set is distrusted.
    if removed > max(2, int(len(questions) * 0.6)):
        log.warning(
            "Relevance filter tried to remove %d/%d questions — ignoring this pass",
            removed, len(questions),
        )
        return questions
    keep = []
    for q, ok in zip(questions, verdicts):
        if ok:
            keep.append(q)
        else:
            log.info("Filtered off-role question: %s", q["question"][:100])
    return keep


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
