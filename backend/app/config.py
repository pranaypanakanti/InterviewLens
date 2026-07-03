import os


class Settings:
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    SEARXNG_URL: str = os.getenv("SEARXNG_URL", "http://searxng:8080")
    EXTRACT_MODEL: str = os.getenv("EXTRACT_MODEL", "qwen2.5:3b-instruct-q4_K_M")
    ANSWER_MODEL: str = os.getenv("ANSWER_MODEL", "qwen2.5:7b-instruct-q4_K_M")
    FAST_ANSWER_MODEL: str = os.getenv("FAST_ANSWER_MODEL", "qwen2.5:3b-instruct-q4_K_M")
    EMBED_MODEL: str = os.getenv("EMBED_MODEL", "nomic-embed-text")
    NUM_CTX: int = int(os.getenv("NUM_CTX", "4096"))
    KEEP_ALIVE: str = os.getenv("KEEP_ALIVE", "30m")
    DATA_DIR: str = os.getenv("DATA_DIR", "/app/data")
    DB_PATH: str = os.getenv("DB_PATH", os.path.join(os.getenv("DATA_DIR", "/app/data"), "app.db"))

    # Pipeline tuning
    RESULTS_PER_QUERY: int = int(os.getenv("RESULTS_PER_QUERY", "8"))
    FETCH_CONCURRENCY: int = int(os.getenv("FETCH_CONCURRENCY", "5"))
    MAX_FETCH_DOCS: int = int(os.getenv("MAX_FETCH_DOCS", "16"))
    MAX_SNIPPET_DOCS: int = int(os.getenv("MAX_SNIPPET_DOCS", "8"))
    MAX_DOC_CHARS: int = int(os.getenv("MAX_DOC_CHARS", "5000"))
    QUESTION_LIMIT: int = int(os.getenv("QUESTION_LIMIT", "30"))
    MIN_QUESTIONS: int = int(os.getenv("MIN_QUESTIONS", "20"))
    CLUSTER_THRESHOLD: float = float(os.getenv("CLUSTER_THRESHOLD", "0.85"))
    USER_AGENT: str = os.getenv(
        "USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    )


settings = Settings()
