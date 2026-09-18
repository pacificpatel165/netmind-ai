# NetMind AI — component #4 (Kubernetes), the k3s proof workload.
# Built and loaded locally (docker build + `k3s ctr images import`) --
# no registry involved, same "no public image, build locally" pattern
# as intelligence/anomaly-detection's Dockerfile.

FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8080
CMD ["python", "app.py"]
