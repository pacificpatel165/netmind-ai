# NetMind AI — component #5, anomaly detection.
# No public image exists for this (it's project code) — build locally
# before first `clab deploy`, see README.md.

FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY detector.py .

EXPOSE 9805
CMD ["python", "detector.py"]
