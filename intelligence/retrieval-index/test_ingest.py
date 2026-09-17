"""Automated tests for component #6 (retrieval-index)'s ingest.py, added
2026-09-17 as part of closing BACKLOG.md item 30b.

ingest.py's real chromadb dependency is heavy but plain host-installable
(already pulled in transitively by three of the other four components,
per BACKLOG.md item 32) -- it does not actually need a container to test,
same finding as component #5. What genuinely needs a *live* Chroma is
never exercised here: `chromadb.HttpClient` is mocked at the module
boundary (`ingest.chromadb.HttpClient`), so these tests run with no
Chroma container and no network call.

Covers: chunk_text()'s boundary behavior (pure function, no mocking
needed) and main()'s document-assembly + upsert-call shape (mocked
Chroma), including the real "no documents matched" early-return path.
"""

import os

import ingest


class TestChunkText:
    def test_short_text_returns_single_chunk(self):
        text = "short text well under the chunk size"
        assert ingest.chunk_text(text, size=800, overlap=100) == [text]

    def test_empty_text_returns_empty_list(self):
        assert ingest.chunk_text("", size=800, overlap=100) == []

    def test_splits_into_overlapping_chunks(self):
        text = "x" * 25
        chunks = ingest.chunk_text(text, size=10, overlap=3)
        # start=0: [0:10], start=7: [7:17], start=14: [14:24], start=21: [21:25]
        assert chunks == ["x" * 10, "x" * 10, "x" * 10, "x" * 4]

    def test_chunks_actually_overlap_by_the_requested_amount(self):
        text = "abcdefghijklmnopqrst"  # 20 chars
        chunks = ingest.chunk_text(text, size=8, overlap=2)
        # chunk[0] = text[0:8], chunk[1] starts at 8-2=6
        assert chunks[0] == text[0:8]
        assert chunks[1] == text[6:14]
        # confirm the actual overlap region matches between consecutive chunks
        assert chunks[0][-2:] == chunks[1][:2]

    def test_last_chunk_stops_exactly_at_text_end_without_trailing_empty_chunk(self):
        text = "y" * 16
        chunks = ingest.chunk_text(text, size=8, overlap=0)
        assert chunks == ["y" * 8, "y" * 8]
        assert "".join(chunks) == text


class _FakeCollection:
    def __init__(self):
        self.upserted = None

    def upsert(self, ids, documents, metadatas):
        self.upserted = {"ids": ids, "documents": documents, "metadatas": metadatas}


class _FakeClient:
    def __init__(self):
        self.collection = _FakeCollection()

    def get_or_create_collection(self, name, embedding_function=None):
        return self.collection


class TestMainIngestFlow:
    def test_ingests_matching_docs_with_deterministic_ids(self, tmp_path, monkeypatch):
        # Only DOC_GLOBS-matching paths should be picked up.
        (tmp_path / "PROGRESS_LOG.md").write_text("hello world, this is short")
        os.makedirs(tmp_path / "lab", exist_ok=True)
        (tmp_path / "lab" / "README.md").write_text("lab readme content")
        # A file that does NOT match any DOC_GLOBS pattern -- must be ignored.
        (tmp_path / "unrelated.txt").write_text("should not be ingested")

        fake_client = _FakeClient()
        monkeypatch.setattr(ingest.chromadb, "HttpClient", lambda host, port: fake_client)
        monkeypatch.setattr(ingest, "REPO_ROOT", str(tmp_path))

        ingest.main()

        result = fake_client.collection.upserted
        assert result is not None
        sources = {m["source"] for m in result["metadatas"]}
        assert sources == {"PROGRESS_LOG.md", "lab/README.md"}
        # deterministic id format: "<rel_path>::<chunk index>"
        assert "PROGRESS_LOG.md::0" in result["ids"]
        assert "lab/README.md::0" in result["ids"]

    def test_no_matching_docs_does_not_call_upsert(self, tmp_path, monkeypatch, capsys):
        fake_client = _FakeClient()
        monkeypatch.setattr(ingest.chromadb, "HttpClient", lambda host, port: fake_client)
        monkeypatch.setattr(ingest, "REPO_ROOT", str(tmp_path))

        ingest.main()

        assert fake_client.collection.upserted is None
        assert "No documents matched" in capsys.readouterr().out
