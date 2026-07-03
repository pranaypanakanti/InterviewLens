"""Async client for a native Ollama instance (chat with JSON-schema output + embeddings)."""
import json
import logging
import re

import httpx

from ..config import settings

log = logging.getLogger("interviewlens.ollama")

TIMEOUT = httpx.Timeout(600.0, connect=10.0)


def _repair_json(text: str):
    """Best-effort recovery of a JSON object from model output."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError(f"Model did not return valid JSON: {text[:200]!r}")


class OllamaClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=TIMEOUT)

    async def close(self):
        await self._client.aclose()

    async def list_models(self) -> list[str]:
        resp = await self._client.get("/api/tags", timeout=10.0)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]

    async def chat_json(
        self,
        model: str,
        prompt: str,
        schema: dict | None = None,
        system: str | None = None,
        temperature: float = 0.2,
        num_ctx: int | None = None,
    ) -> dict:
        """Chat completion constrained to JSON (schema-constrained when given)."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "format": schema if schema else "json",
            "keep_alive": settings.KEEP_ALIVE,
            "options": {
                "num_ctx": num_ctx or settings.NUM_CTX,
                "temperature": temperature,
            },
        }
        resp = await self._client.post("/api/chat", json=payload)
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        return _repair_json(content)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.post(
            "/api/embed",
            json={"model": settings.EMBED_MODEL, "input": texts, "keep_alive": settings.KEEP_ALIVE},
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]

    async def health(self) -> dict:
        """Report reachability and which required models are present."""
        required = {
            "extract_model": settings.EXTRACT_MODEL,
            "answer_model": settings.ANSWER_MODEL,
            "embed_model": settings.EMBED_MODEL,
        }
        try:
            models = await self.list_models()
        except Exception as exc:
            return {
                "reachable": False,
                "error": f"Cannot reach Ollama at {self.base_url}: {exc}",
                "models": {k: {"name": v, "present": False} for k, v in required.items()},
            }
        # Ollama lists names with tags; treat "nomic-embed-text" == "nomic-embed-text:latest".
        normalized = {m.split(":latest")[0] for m in models} | set(models)
        return {
            "reachable": True,
            "models": {
                k: {"name": v, "present": v in normalized} for k, v in required.items()
            },
        }


ollama = OllamaClient()
