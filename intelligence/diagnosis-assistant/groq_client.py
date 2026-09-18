"""NetMind AI — component #7, diagnosis assistant.

Groq backend for the provider abstraction (BACKLOG.md item 35, added
2026-09-18). Plain `requests` against Groq's OpenAI-compatible REST API
-- no `groq`/`openai` SDK dependency, matching ollama_client.py's own
style and avoiding two new packages for what's a single HTTP call.

Endpoint and auth header verified live against Groq's own docs on
2026-09-18 (https://console.groq.com/docs/api-reference#chat-create).
Default model is "openai/gpt-oss-20b" -- the user's own already-decided
choice from a prior provider config, re-verified live against Groq's
production model list on 2026-09-18
(https://console.groq.com/docs/models: listed under Production Models,
131,072-token context window) rather than assumed -- Groq deprecates
model names often enough that guessing was a real risk here.
"""

import os

import requests

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")


def generate(prompt: str, timeout: int = 300) -> str:
    """Single-shot chat completion. Raises RuntimeError up front if
    GROQ_API_KEY isn't set -- fail loud and immediately, not with an
    opaque 401 three network hops later."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Get a free key at "
            "https://console.groq.com/keys and export it before running "
            "with LLM_PROVIDER=groq."
        )
    resp = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
