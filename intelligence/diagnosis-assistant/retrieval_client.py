"""NetMind AI — component #7, diagnosis assistant.

Thin wrapper around component #6's Chroma collection -- same client
pattern as intelligence/retrieval-index/query.py, factored out so the
assistant can call it as a library rather than shelling out.

Runs host-level, so it reaches Chroma via the port already published
to the host (see README.md's placement decision) rather than the
container-network hostname ingest.py/query.py use.
"""

import os

import chromadb
from chromadb.utils import embedding_functions

CHROMA_HOST = os.environ.get("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8000"))
COLLECTION_NAME = "netmind-docs"
TOP_K = int(os.environ.get("RETRIEVAL_TOP_K", "3"))

_collection = None


def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        embed_fn = embedding_functions.DefaultEmbeddingFunction()
        _collection = client.get_or_create_collection(COLLECTION_NAME, embedding_function=embed_fn)
    return _collection


def retrieve(question: str, top_k: int = TOP_K) -> list[dict]:
    """Returns a list of {source, chunk, text, distance} dicts, closest
    first. Empty list (not an error) if the collection has nothing in it
    yet -- the assistant should still answer from metrics alone rather
    than fail outright."""
    collection = _get_collection()
    if collection.count() == 0:
        return []
    results = collection.query(query_texts=[question], n_results=top_k)
    hits = []
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        hits.append({
            "source": meta["source"],
            "chunk": meta["chunk"],
            "text": doc.strip(),
            "distance": dist,
        })
    return hits
