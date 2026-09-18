"""NetMind AI — component #7, automated tests for the provider dispatch
logic (BACKLOG.md item 35, added 2026-09-18).

Scope, deliberately: only `llm_provider.generate()`'s dispatch logic is
covered here -- which provider function gets called for a given
LLM_PROVIDER value, and that an unknown value fails loudly. The actual
HTTP calls inside ollama_client/groq_client/gemini_client are NOT
covered here (no live Ollama/Groq/Gemini connection in this suite) --
that's docs/testing/TESTING.md territory, same split as router.py's
tests versus resolve_metrics()'s live-dependency paths.

Run:
    cd intelligence/diagnosis-assistant
    source ../.venv/bin/activate
    pytest test_llm_provider.py -v
"""

import pytest

import llm_provider


def test_default_provider_is_ollama_when_unset(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    calls = []
    monkeypatch.setitem(
        llm_provider._PROVIDERS, "ollama", lambda prompt, timeout: calls.append((prompt, timeout)) or "ok"
    )
    result = llm_provider.generate("hello", timeout=42)
    assert result == "ok"
    assert calls == [("hello", 42)]


def test_explicit_groq_dispatches_to_groq_client(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    calls = []
    monkeypatch.setitem(
        llm_provider._PROVIDERS, "groq", lambda prompt, timeout: calls.append((prompt, timeout)) or "groq-answer"
    )
    assert llm_provider.generate("what's up") == "groq-answer"
    assert calls == [("what's up", 300)]  # default timeout


def test_explicit_gemini_dispatches_to_gemini_client(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setitem(llm_provider._PROVIDERS, "gemini", lambda prompt, timeout: "gemini-answer")
    assert llm_provider.generate("hello") == "gemini-answer"


def test_provider_name_is_case_and_whitespace_insensitive(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "  GROQ  ")
    monkeypatch.setitem(llm_provider._PROVIDERS, "groq", lambda prompt, timeout: "matched")
    assert llm_provider.generate("hi") == "matched"


def test_unknown_provider_raises_immediately_not_silently_falls_back(monkeypatch):
    # A typo in LLM_PROVIDER must be loud -- silently running against
    # Ollama when the user asked for "groqq" would be a much worse bug
    # than a clear startup error.
    monkeypatch.setenv("LLM_PROVIDER", "chatgpt")
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER 'chatgpt'"):
        llm_provider.generate("hi")


def test_error_message_lists_the_real_valid_options(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "bogus")
    with pytest.raises(ValueError, match="gemini, groq, ollama"):
        llm_provider.generate("hi")
