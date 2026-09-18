"""NetMind AI — component #4 (Kubernetes), the k3s proof workload.

Deliberately minimal: this app's only job is to prove k3s + Cilium can
run and serve a real, non-synthetic workload (`cilium connectivity
test`'s own pods don't count — they're the CNI's own test fixture, not
an application). Two endpoints:

- GET /healthz -- plain liveness/readiness check, 200 OK + JSON.
- GET /info    -- returns the pod's own hostname (== pod name under
  k3s) and IP, so a real `curl` against the Service can show the
  request actually landing on different pods across replicas --
  concrete, observable proof the Service is load-balancing, not just
  that one pod is up.

No dependency on anything else in this project (Prometheus, Chroma,
Ollama) -- this workload's whole purpose is proving the Kubernetes
layer itself, not integrating with the rest of NetMind yet. If a
component gets migrated onto k3s later (BACKLOG.md, deferred), it
replaces this one; until then this stays as the standing proof that
the deploy/Service/scaling path works.
"""

import socket
from datetime import datetime, timezone

from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/healthz")
def healthz():
    return jsonify(status="ok"), 200


@app.route("/info")
def info():
    return jsonify(
        pod=socket.gethostname(),
        pod_ip=socket.gethostbyname(socket.gethostname()),
        served_at=datetime.now(timezone.utc).isoformat(),
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
