"""NetMind AI — component #6, retrieval index, stage 1 query CLI.

The exit-criterion tool: proves retrieval actually works, not just
that ingestion ran without error. Embeds a question with the same
default embedding function used at ingest time, runs a similarity
search against Chroma, and prints the top matches with their source
doc and distance so you can eyeball whether they're actually relevant.

Usage:
    python query.py "how does gnmic subscribe to srl1?"
"""

import os
import sys

import chromadb
from chromadb.utils import embedding_functions

CHROMA_HOST = os.environ.get("CHROMA_HOST", "clab-netmind-2node-chroma")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8000"))
COLLECTION_NAME = "netmind-docs"
TOP_K = int(os.environ.get("TOP_K", "3"))


def main() -> None:
    if len(sys.argv) < 2:
        print('usage: python query.py "<question>"')
        sys.exit(1)
    query_text = " ".join(sys.argv[1:])

    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    embed_fn = embedding_functions.DefaultEmbeddingFunction()
    collection = client.get_or_create_collection(COLLECTION_NAME, embedding_function=embed_fn)

    if collection.count() == 0:
        print("Collection is empty — run ingest.py first.")
        sys.exit(1)

    results = collection.query(query_texts=[query_text], n_results=TOP_K)
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    print(f"Top {len(docs)} matches for: {query_text!r}\n")
    for doc, meta, dist in zip(docs, metas, dists):
        print(f"--- {meta['source']} (chunk {meta['chunk']}, distance {dist:.4f}) ---")
        print(doc.strip()[:400])
        print()


if __name__ == "__main__":
    main()
