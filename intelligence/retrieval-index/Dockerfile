# NetMind AI — component #6, retrieval-index tooling (ingest.py /
# query.py). No public image exists for these — build locally, see
# README.md. This image is never itself a topology node; it's run
# on-demand against the `chroma` container's network.

FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ingest.py query.py .

CMD ["python", "ingest.py"]
