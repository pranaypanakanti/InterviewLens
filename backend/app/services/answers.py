"""Resume-tailored answer generation (Quality=7B / Fast=3B)."""
import logging

from ..config import settings
from .ollama import ollama

log = logging.getLogger("interviewlens.answers")

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "why_asked": {"type": "string"},
        "tips": {"type": "string"},
    },
    "required": ["answer", "why_asked", "tips"],
}

SYSTEM = (
    "You are an expert interview coach. You write the best possible spoken answer the "
    "candidate could give, tailored to their real resume. Never invent experience the "
    "resume does not support. Respond with JSON only."
)


def _guidance(category: str) -> str:
    if category == "behavioral":
        return (
            "Structure the answer with STAR (Situation, Task, Action, Result), drawing on a "
            "real project or experience from the resume."
        )
    if category in ("technical", "coding", "system-design", "domain-knowledge"):
        return (
            "Give a correct, concise model answer first, then briefly describe how to reason "
            "about it out loud in the interview. Where relevant, connect it to the "
            "candidate's actual experience."
        )
    return "Answer directly and concretely, connecting to the candidate's background where honest."


async def generate_answer(
    question: dict,
    jd_entities: dict,
    resume_text: str,
    resume_entities: dict,
    mode: str,
) -> dict:
    model = settings.FAST_ANSWER_MODEL if mode == "fast" else settings.ANSWER_MODEL
    projects = "; ".join(resume_entities.get("notable_projects", [])[:5])
    prompt = (
        f"COMPANY: {jd_entities.get('company', 'unknown')}\n"
        f"ROLE: {jd_entities.get('job_title', 'unknown')} ({jd_entities.get('seniority', '')})\n"
        f"KEY JD SKILLS: {', '.join(jd_entities.get('key_skills', [])[:8])}\n\n"
        f"CANDIDATE RESUME (verbatim excerpt):\n{resume_text[:2500]}\n\n"
        f"CANDIDATE'S NOTABLE PROJECTS: {projects}\n\n"
        f"INTERVIEW QUESTION ({question['category']}): {question['question']}\n\n"
        f"Write the best answer the candidate could give. {_guidance(question['category'])}\n"
        "Keep the answer under ~250 words, first person, natural spoken tone.\n"
        "Also provide:\n"
        "- why_asked: one line on why interviewers ask this.\n"
        "- tips: 1-2 short lines of delivery advice."
    )
    try:
        data = await ollama.chat_json(
            model, prompt, schema=ANSWER_SCHEMA, system=SYSTEM, temperature=0.4
        )
        return {
            "answer": (data.get("answer") or "").strip(),
            "why_asked": (data.get("why_asked") or "").strip(),
            "tips": (data.get("tips") or "").strip(),
        }
    except Exception as exc:
        log.warning("Answer generation failed for %r: %s", question["question"][:60], exc)
        return {
            "answer": "Answer generation failed for this question — try re-running.",
            "why_asked": "",
            "tips": "",
        }
