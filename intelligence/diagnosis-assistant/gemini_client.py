"""NetMind AI — component #7, diagnosis assistant.

Gemini backend for the provider abstraction (BACKLOG.md item 35, added
2026-09-18). Plain `requests` against the `generateContent` REST endpoint
-- no `google-generativeai`/`google-genai` SDK dependency, matching
ollama_client.py's own style.

Endpoint shape and auth (API key as a query parameter, not a header --
a real point of difference from Groq, verified rather than assumed)
were verified live against Google's own docs on 2026-09-18
(https://ai.google.dev/api/generate-content). Default model is
"gemini-3.5-flash-lite" -- the user's own already-decided choice from a
prior provider config, re-verified live against Google's current model
list on 2026-09-18 (https://ai.google.dev/gemini-api/docs/models:
listed with Stable status). A newer "gemini-3.8-flash" also exists and
is Stable, but the user's own pick is kept as the default here rather
than substituted; "gemini-2.5-flash" (also Stable) was the user's noted
fallback alternative -- see GEMINI_MODEL in .env.example.
"""

import os

import requests

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


def generate(prompt: str, timeout: int = 300) -> str:
    """Single-shot content generation. Raises RuntimeError up front if
    GEMINI_API_KEY isn't set, same fail-loud pattern as groq_client.py."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Get a free key at "
            "https://aistudio.google.com/apikey and export it before "
            "running with LLM_PROVIDER=gemini."
        )
    resp = requests.post(
        GEMINI_URL_TEMPLATE.format(model=MODEL),
        params={"key": api_key},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
