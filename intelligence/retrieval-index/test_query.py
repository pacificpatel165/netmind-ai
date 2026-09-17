"""Automated tests for component #6 (retrieval-index)'s query.py, added
2026-09-17 as part of closing BACKLOG.md item 30b.

Same mocking approach as test_ingest.py: `chromadb.HttpClient` is
replaced at the module boundary so no live Chroma container or network
call is needed. Covers the two real behaviors query.py has: refusing to
query an empty collection (the exit-1 guard), and the actual
collection.query() call shape / output formatting when results exist.
"""

import sys

import pytest

import query


class _FakeCollection:
    def __init__(self, count=0, query_result=None):
        self._count = count
        self._query_result = query_result
        self.last_query_call = None

    def count(self):
        return self._count

    def query(self, query_texts, n_results):
        self.last_query_call = {"query_texts": query_texts, "n_results": n_results}
        return self._query_result


class _FakeClient:
    def __init__(self, collection):
        self.collection = collection

    def get_or_create_collection(self, name, embedding_function=None):
        return self.collection


class TestQueryMain:
    def test_no_query_argument_exits_with_usage(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["query.py"])
        with pytest.raises(SystemExit) as exc:
            query.main()
        assert exc.value.code == 1

    def test_empty_collection_exits_without_querying(self, monkeypatch, capsys):
        fake_collection = _FakeCollection(count=0)
        fake_client = _FakeClient(fake_collection)
        monkeypatch.setattr(sys, "argv", ["query.py", "how does gnmic work?"])
        monkeypatch.setattr(query.chromadb, "HttpClient", lambda host, port: fake_client)

        with pytest.raises(SystemExit) as exc:
            query.main()

        assert exc.value.code == 1
        assert fake_collection.last_query_call is None
        assert "empty" in capsys.readouterr().out.lower()

    def test_real_query_joins_argv_and_passes_top_k(self, monkeypatch, capsys):
        fake_collection = _FakeCollection(
            count=5,
            query_result={
                "documents": [["chunk one text", "chunk two text"]],
                "metadatas": [[{"source": "lab/README.md", "chunk": 0}, {"source": "PROGRESS_LOG.md", "chunk": 3}]],
                "distances": [[0.12, 0.45]],
            },
        )
        fake_client = _FakeClient(fake_collection)
        monkeypatch.setattr(sys, "argv", ["query.py", "how", "does", "gnmic", "subscribe?"])
        monkeypatch.setattr(query.chromadb, "HttpClient", lambda host, port: fake_client)
        monkeypatch.setattr(query, "TOP_K", 2)

        query.main()

        # argv words after the script name are joined into one question string
        assert fake_collection.last_query_call == {
            "query_texts": ["how does gnmic subscribe?"],
            "n_results": 2,
        }
        out = capsys.readouterr().out
        assert "lab/README.md" in out
        assert "PROGRESS_LOG.md" in out
        assert "chunk one text" in out
