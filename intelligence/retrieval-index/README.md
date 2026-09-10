# intelligence/retrieval-index/

Component #6 — vector store for runbooks/past incidents, running
continuously in the background per the roadmap. The first component
that isn't a straightforward extension of the existing telemetry
pipeline: nothing in the stack so far needed an embedding model or a
vector store, so this is a genuine branch point, not an incremental
add.

## Design decisions (2026-09-10)

- **Corpus: this project's own docs, not invented runbooks.** Every
  README/design doc written so far (`lab/`, `telemetry/`, `metrics/`,
  `grafana/`, `intelligence/anomaly-detection/`, `docs/setup/`,
  `docs/architecture/`, `docs/roadmap/`, `PROGRESS_LOG.md`) is real
  content that exists today. It also doubles as a natural test corpus
  for component #7 (diagnosis assistant) later — a question like "why
  did we skip the Kafka buffer" should retrieve `BACKLOG.md` item 1
  directly.
- **Vector store: Chroma, containerized.** Matches the roadmap's own
  first-listed option and the same "own node in the topology" pattern
  every prior component used. No persistent volume yet — same
  deliberate simplification as Prometheus in component #3 (see
  `docs/roadmap/BACKLOG.md`): proving the retrieval pattern comes
  before solving the container-user-vs-host-owner permission question
  a bind mount would raise.
- **Embeddings: Chroma's built-in default function (ONNX
  MiniLM-L6-v2), not sentence-transformers + torch.** Same underlying
  model family, a much lighter container build, and one less
  dependency to version-pin. No external embedding API, no API key —
  runs entirely inside the lab.
- **Ingestion and query are on-demand scripts, not topology nodes.**
  Only the store itself (`chroma`) needs to stay running continuously;
  chunking/embedding docs and querying them are cheap, idempotent
  operations run against `chroma`'s network when needed, not a
  permanently-running service. Re-running `ingest.py` after docs
  change is the whole "keep it current" story for stage 1 — a
  scheduled/automatic re-ingest is a deliberate stage 2 (see
  `docs/roadmap/BACKLOG.md`).

## Layout

- `ingest.py` — chunks the docs listed in `DOC_GLOBS`, embeds them,
  upserts into Chroma's `netmind-docs` collection. Idempotent: chunk
  ids are deterministic from source path + chunk index.
- `query.py` — the verification tool: embeds a question, runs a
  similarity search, prints the top matches with source and distance
  so you can judge relevance by eye, not just "it didn't error."
- `requirements.txt`, `Dockerfile` — project code, no public image;
  build locally like `intelligence/anomaly-detection/`.

**Known gotcha:** the Chroma server image is pinned to `chromadb/chroma:0.5.23` in the topology, matching this directory's `chromadb==0.5.23` client pin — not `:latest`. The client and server share the same `chromadb` package and its collection-config JSON schema changes across versions; a `:latest` server paired with this pinned client failed with `KeyError: '_type'` inside `CollectionConfigurationInternal.from_json` on the very first `get_or_create_collection` call. If either pin changes, bump the other to match rather than letting them drift.

## Building the image (required before first use)

```bash
cd ~/netmind-lab/intelligence/retrieval-index
docker build -t netmind-retrieval-tools:latest .
```

Same native-fs reason as everything else — run
`scripts/sync-to-lab.sh` first if you haven't this session, and
rebuild whenever `ingest.py`/`query.py` change.

## Running it

```bash
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/sync-to-lab.sh
cd ~/netmind-lab/intelligence/retrieval-index
docker build -t netmind-retrieval-tools:latest .
cd ~/netmind-lab/lab/topologies
sudo clab deploy -t netmind-2node.clab.yml
```

Once `chroma` is up, ingest the docs (bind-mounts the whole repo
read-only so it always reads current content, no rebuild needed just
to re-ingest):

```bash
docker run --rm --network netmind-mgmt \
  -v ~/netmind-lab:/repo:ro \
  netmind-retrieval-tools:latest python ingest.py
```

## Verifying it

```bash
docker run --rm --network netmind-mgmt \
  netmind-retrieval-tools:latest python query.py "why was Kafka skipped for the metrics store?"
```

Should return chunks from `docs/roadmap/BACKLOG.md` (item 1) and/or
`metrics/README.md` near the top, with a low distance score. Try a
couple of different questions against real content you know is in the
docs — that's the actual exit criterion for component #6 stage 1: real
retrieval against real content, not just "the container started."
