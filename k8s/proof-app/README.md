# k8s/proof-app/

Component #4 (Kubernetes) — the first real workload deployed on k3s,
closing the "not yet done" item from `PROGRESS_LOG.md` entry 53:
`cilium connectivity test`'s 78/79 passing tests only exercised
Cilium's own synthetic test pods, never an actual application.

## What it is

A deliberately minimal Flask app (`app.py`) with two endpoints:

- `GET /healthz` — plain liveness/readiness check.
- `GET /info` — returns the serving pod's own hostname (== pod name
  under k3s) and IP. The point of this endpoint specifically: repeated
  `curl`s against the Service should show *different* pod names
  answering, which is real, observable proof the Service is
  load-balancing across replicas — not just that one pod happens to be
  up.

2 replicas (`deployment.yaml`), fronted by a `ClusterIP` Service
(`service.yaml`) — kube-proxy is disabled in this cluster (Cilium's
eBPF datapath handles Service routing instead, per the connectivity
test's own verified config from entry 53), so this also exercises that
same path.

No dependency on any other NetMind component (Prometheus, Chroma,
Ollama) — this workload's only job is proving the Kubernetes layer
itself works end to end with a real app. If a real component gets
migrated onto k3s later, it replaces this one; until then this stays
as the standing regression check that deploy/Service/scaling work.

## Building and deploying

No registry — the image is built locally and imported straight into
k3s's containerd, same "no public image, build locally" shape as
`intelligence/anomaly-detection`:

```bash
cd ~/netmind-lab/k8s/proof-app
docker build -t netmind-proof-app:latest .
docker save netmind-proof-app:latest | sudo k3s ctr images import -
kubectl apply -f deployment.yaml -f service.yaml
```

## Verifying it's real

```bash
kubectl get pods -l app=netmind-proof-app -o wide   # 2/2 Running, different nodes/IPs
kubectl get svc netmind-proof-app                     # note the ClusterIP

# from inside the cluster network namespace (a throwaway debug pod is
# the simplest way to reach a ClusterIP without port-forwarding):
kubectl run curl-test --image=curlimages/curl --rm -it --restart=Never -- \
  sh -c 'for i in 1 2 3 4; do curl -s http://netmind-proof-app/info; echo; done'
```

Real proof, not just "pods say Running": the `/info` responses across
those 4 curls should show at least two distinct `pod` values — that's
the Service actually balancing across both replicas through Cilium's
datapath, not one pod quietly answering every request.
