"""NetMind AI — component #6, retrieval index, stage 1 ingestion.

Chunks this project's own README/design docs and embeds them into
Chroma. Uses Chroma's built-in default embedding function (ONNX
MiniLM-L6-v2) rather than pulling in a separate sentence-transformers +
torch dependency — same underlying model family, much lighter
container build, one less thing to version-pin.

Seed corpus is this project's own docs (see DOC_GLOBS below), not
invented runbooks: real content that exists today, and doubles as a
natural test corpus for component #7's diagnosis assistant later.

Idempotent — chunk ids are deterministic from source path + chunk
index, so re-running after docs change is a plain upsert, not a
clear-and-reload.
"""

import glob
import os

import chromadb
from chromadb.utils import embedding_functions

CHROMA_HOST = os.environ.get("CHROMA_HOST", "clab-netmind-2node-chroma")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8000"))
REPO_ROOT = os.environ.get("REPO_ROOT", "/repo")
COLLECTION_NAME = "netmind-docs"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

# Every doc written so far, component by component — extend this list
# as new components add their own README.
DOC_GLOBS = [
    "lab/README.md",
    "telemetry/README.md",
    "metrics/README.md",
    "grafana/README.md",
    "intelligence/anomaly-detection/README.md",
    "intelligence/retrieval-index/README.md",
    "docs/setup/*.md",
    "docs/architecture/*.md",
    "docs/roadmap/*.md",
    "PROGRESS_LOG.md",
]


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


def main() -> None:
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    embed_fn = embedding_functions.DefaultEmbeddingFunction()
    collection = client.get_or_create_collection(COLLECTION_NAME, embedding_function=embed_fn)

    ids, documents, metadatas = [], [], []
    for pattern in DOC_GLOBS:
        for path in glob.glob(os.path.join(REPO_ROOT, pattern)):
            rel_path = os.path.relpath(path, REPO_ROOT)
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            for i, chunk in enumerate(chunk_text(text)):
                ids.append(f"{rel_path}::{i}")
                documents.append(chunk)
                metadatas.append({"source": rel_path, "chunk": i})

    if not ids:
        print(f"No documents matched under REPO_ROOT={REPO_ROOT} — check the bind mount and DOC_GLOBS.")
        return

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    doc_count = len({m["source"] for m in metadatas})
    print(f"Ingested {len(ids)} chunks from {doc_count} documents into collection '{COLLECTION_NAME}'.")


if __name__ == "__main__":
    main()
