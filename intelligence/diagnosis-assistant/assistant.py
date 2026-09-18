"""NetMind AI — component #7, diagnosis assistant. First real build.

Ties together everything decided in PROGRESS_LOG entries 21-23:
parallel retrieval (Chroma, component #6) + structured metrics
(Prometheus, hybrid template/LLM-fallback router), assembled into one
prompt sent to an LLM, answered with citations.

Usage:
    python assistant.py "ethernet-1/1 just flagged an anomaly on carrier transitions, what's going on?"

    LLM_PROVIDER selects the backend (default: ollama, local Llama 3.1
    8B -- see BACKLOG.md item 35 / llm_provider.py for groq/gemini):
    LLM_PROVIDER=groq GROQ_API_KEY=... python assistant.py "..."
    LLM_PROVIDER=gemini GEMINI_API_KEY=... python assistant.py "..."

Design notes:
- Runs host-level, not containerized (see README.md/BACKLOG item 22)
  -- reaches Chroma/Prometheus via their host-published ports and
  Ollama via localhost, no docker network involved.
- Retrieval and metrics are independent lookups (true to "parallel" in
  the roadmap's description) -- one failing doesn't block the other;
  the prompt is assembled from whatever came back.
"""

import sys

import retrieval_client
import router
from llm_provider import generate

PROMPT_TEMPLATE = """You are NetMind's diagnosis assistant. Answer the question using \
only the context below, and cite which source each claim comes from \
(a doc path, or "Prometheus query: <the query>" for metrics).

--- Retrieved docs ---
{docs_section}

--- Metrics ---
{metrics_section}
(query used: {promql}{fallback_note})

--- Question ---
{question}
"""


def format_docs(hits: list[dict]) -> str:
    if not hits:
        return "(no relevant docs found)"
    parts = []
    for hit in hits:
        parts.append(f"[{hit['source']}, chunk {hit['chunk']}]\n{hit['text'][:600]}")
    return "\n\n".join(parts)


def answer(question: str) -> str:
    docs = retrieval_client.retrieve(question)
    promql, metrics_text, used_fallback = router.resolve_metrics(question, generate)

    fallback_note = " -- LLM-generated, not a fixed template" if used_fallback else ""
    prompt = PROMPT_TEMPLATE.format(
        docs_section=format_docs(docs),
        metrics_section=metrics_text,
        promql=promql or "(none)",
        fallback_note=fallback_note,
        question=question,
    )
    return generate(prompt)


def main() -> None:
    if len(sys.argv) < 2:
        print('usage: python assistant.py "<question>"')
        sys.exit(1)
    question = " ".join(sys.argv[1:])
    print(answer(question))


if __name__ == "__main__":
    main()
