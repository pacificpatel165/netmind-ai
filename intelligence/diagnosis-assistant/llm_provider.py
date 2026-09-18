"""NetMind AI — component #7, diagnosis assistant.

The provider abstraction (BACKLOG.md item 35, reopens item 22).

Item 22 deliberately deferred this: local Llama 3.1 8B via Ollama was
already proving correct with citations, so there was no concrete gap to
close by adding more providers speculatively. A concrete reason has
since been given directly (2026-09-16), which is what reopened it --
see PROGRESS_LOG for the full context.

This module is the ONLY thing `assistant.py` and `router.py` import for
generation -- neither knows or cares which provider is actually running
underneath. Selected by the LLM_PROVIDER env var, defaulting to "ollama"
so nothing about the existing local-only behavior changes unless a user
explicitly opts in to a remote provider.

Every provider module (ollama_client.py, groq_client.py, gemini_client.py)
exposes the same shape: generate(prompt: str, timeout: int = 300) -> str.
That shared shape is the actual interface -- there's no ABC/Protocol
class here because Python's duck typing already gives us the real
contract test (call it with a string, get a string back), and adding a
formal interface over three one-function modules would be ceremony
without a corresponding benefit at this scale.

API keys load from a `.env` file next to this module (not passed on
the command line -- keeps secrets out of shell history and `ps`
output), via python-dotenv. Resolved from this file's own directory,
not the caller's cwd -- same "don't trust the invoker's working
directory" discipline as scripts/run-all-tests.sh's REPO_ROOT, so this
still works whether assistant.py is run from
intelligence/diagnosis-assistant/ or anywhere else. `load_dotenv()`
never overrides a variable already set in the real environment
(python-dotenv's own default), so an explicitly-exported
GROQ_API_KEY/GEMINI_API_KEY still wins if someone sets one -- the
.env file is a convenience default, not the only way in.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

import gemini_client
import groq_client
import ollama_client

load_dotenv(Path(__file__).resolve().parent / ".env")

_PROVIDERS = {
    "ollama": ollama_client.generate,
    "groq": groq_client.generate,
    "gemini": gemini_client.generate,
}


def generate(prompt: str, timeout: int = 300) -> str:
    """Dispatches to whichever backend LLM_PROVIDER names. Raises
    ValueError immediately on an unknown provider name, rather than
    silently falling back to Ollama -- a typo in LLM_PROVIDER should be
    loud, not a silent switch back to a model the user didn't ask for."""
    provider_name = os.environ.get("LLM_PROVIDER", "ollama").strip().lower()
    try:
        provider_fn = _PROVIDERS[provider_name]
    except KeyError:
        raise ValueError(
            f"Unknown LLM_PROVIDER {provider_name!r}. "
            f"Valid options: {', '.join(sorted(_PROVIDERS))}."
        ) from None
    return provider_fn(prompt, timeout=timeout)
