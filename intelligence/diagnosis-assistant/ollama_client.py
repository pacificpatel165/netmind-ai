"""NetMind AI — component #7, diagnosis assistant.

Talks to the host-installed Ollama daemon directly over its HTTP API
(not the `ollama` CLI) -- see docs/setup/07-diagnosis-assistant.md §5
for why: `keep_alive` has to be set per-request in the API body to
actually take effect. A CLI env var doesn't reach an already-running
`ollama serve`, confirmed the hard way (PROGRESS_LOG entry 22).
"""

import os

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")


def generate(prompt: str, timeout: int = 300) -> str:
    """Single-shot, non-streaming generate call. keep_alive: 0 means the
    model unloads from memory immediately after this response -- the
    confirmed-working fix from the 2026-09-11 memory investigation,
    not a manual `ollama stop` and not the CLI's KEEP_ALIVE env var.

    Every call therefore pays a full cold model load, not just
    generation time. Timeout raised from 180s to 300s on 2026-09-15
    (PROGRESS_LOG entry 37) after a real, timed cold-load run measured
    164s -- only 16s of margin under the old timeout, and a real
    diagnose_and_propose.py call (component #8) did in fact time out
    at 180s. 300s is a deliberate safety margin against that measured
    variance, not a guess."""
    resp = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "keep_alive": 0,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["response"]
