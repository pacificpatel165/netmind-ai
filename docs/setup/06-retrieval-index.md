# Component #6 setup: retrieval index (Chroma)

Step-by-step "how" per this folder's convention. For the *why* — this
project's own docs as the seed corpus, Chroma's built-in embedding
function over sentence-transformers+torch, ingestion/query as on-demand
scripts rather than a running service — see
`intelligence/retrieval-index/README.md` and `PROGRESS_LOG.md` entries
dated 2026-09-10.

Prerequisite: component #1 (lab) is deployed — this component doesn't
depend on telemetry/metrics/dashboards being up, only on `srl1`/`srl2`
existing for the docs corpus's content to be meaningful later (it can
technically ingest with any lab state).

---

## 1. Build the image (required before first use)

```bash
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/sync-to-lab.sh
cd ~/netmind-lab/intelligence/retrieval-index
docker build -t netmind-retrieval-tools:latest .
```

Rebuild whenever `ingest.py`/`query.py` change.

## 2. Deploy

```bash
cd ~/netmind-lab/lab/topologies
sudo clab deploy -t netmind-2node.clab.yml
```

## 3. Known gotcha: client/server `chromadb` pin must match

The Chroma server image is pinned to `chromadb/chroma:0.5.23` in the
topology, matching this directory's `chromadb==0.5.23` client pin — not
`:latest`. The client and server share the same package and its
collection-config JSON schema changes across versions; a `:latest`
server paired with this pinned client fails with `KeyError: '_type'`
inside `CollectionConfigurationInternal.from_json` on the very first
`get_or_create_collection()` call. If either pin is ever bumped, bump
the other to match.

## 4. Ingest the docs

```bash
docker run --rm --network netmind-mgmt \
  -v ~/netmind-lab:/repo:ro \
  netmind-retrieval-tools:latest python ingest.py
```

Bind-mounts the whole repo read-only, so it always reads current
content — no image rebuild needed just to re-ingest after docs change,
only to change `ingest.py`/`query.py` themselves. Idempotent — safe to
re-run any time.

## 5. Verify

```bash
docker run --rm --network netmind-mgmt \
  netmind-retrieval-tools:latest python query.py "why was Kafka skipped for the metrics store?"
```

Should return chunks from `docs/roadmap/BACKLOG.md` (item 1) and/or
`metrics/README.md` near the top, with a low distance score. Try a
couple of different questions against real content you know is in the
docs — real retrieval against real content is the exit criterion, not
just "the container started." Full design detail:
`intelligence/retrieval-index/README.md`.

## 6. Automated tests (optional, no lab or Chroma needed)

Since 2026-09-17 (`BACKLOG.md` item 30b), `test_ingest.py`/
`test_query.py` cover `chunk_text()`'s boundary behavior and the
ingest/query call shapes with `chromadb.HttpClient` mocked — no live
Chroma required. Uses the shared venv at `intelligence/.venv` (item
32) — see `docs/testing/TESTING.md`'s "Automated tests" section.
