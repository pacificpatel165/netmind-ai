# Component #1 setup: network lab environment

Step-by-step record of how the containerlab environment was installed and
configured, so it can be rebuilt (new machine, wiped WSL distro, etc.)
without re-deriving the decisions from scratch. Numbering (`01-`) matches
the component map in `PROGRESS_LOG.md` — later components get their own
`0N-<component>.md` file in this folder rather than piling everything
into one document.

For *why* each decision was made, see the session log entries in
`PROGRESS_LOG.md` dated 2026-09-10. This file is the "how", not the "why".

---

## 1. The constraint that shaped this setup

This machine already runs Docker Desktop, integrated with an existing
Ubuntu WSL2 distro used by other projects (AstroLearn-AI, LightYear-AI,
Astro-Quiz). Two things made that setup unsuitable for containerlab
as-is, so containerlab gets its own isolated environment instead of
being installed into that Ubuntu distro:

- Docker Desktop runs its own hidden WSL2 VM (`docker-desktop`,
  `docker-desktop-data`) and proxies the `docker` CLI into integrated
  distros. Containerlab needs direct netns/veth manipulation on the
  distro's own kernel, which this proxy breaks (symptoms: missing
  `xt_recent` kernel module, "link not found" bridge errors, missing
  `docker0`).
- Installing a second, native Docker CE into the existing Ubuntu distro
  to work around that would mean two competing Docker installs in one
  distro — a real source of confusion for the other projects living
  there.

Resolution: a dedicated WSL2 distro, purpose-built for containerlab, with
native Docker CE inside it and Docker Desktop's WSL integration
explicitly turned off for that one distro. The existing Ubuntu distro
and Docker Desktop setup are untouched.

## 2. Prerequisites

Check WSL2 is new enough (containerlab needs ≥ 2.4.4):

```powershell
wsl --update
wsl --version
```

## 3. Install the dedicated containerlab distro

Uses the official `srl-labs/wsl-containerlab` distro image — a `.wsl`
file, installed like any WSL distro:

1. Download the latest `.wsl` release from
   https://github.com/srl-labs/wsl-containerlab/releases (this machine
   used `clab-0.79.0-1.0.wsl`, saved to
   `C:\MyWorkSpace\Softwares\Nokia-WSL-CLAB\`).
2. Install it:

   ```powershell
   wsl --install --from-file C:\MyWorkSpace\Softwares\Nokia-WSL-CLAB\clab-0.79.0-1.0.wsl
   ```

3. On first launch it prompts for a shell — this machine chose option
   3, plain bash — and auto-generates an SSH keypair for passwordless
   `ssh clab@localhost -p 2222` access.
4. A `wsl: Failed to start the systemd user session for 'clab'` warning
   appears on first boot. Harmless — containerlab and Docker CE run as
   root-level system services, not user-session systemd units. Only
   worth revisiting if something systemd-dependent misbehaves later.

The distro is named `Containerlab` (`wsl -d Containerlab` to enter it).

## 4. Keep Docker Desktop's WSL integration OFF for this distro

Docker Desktop → Settings → Resources → WSL Integration:

- **Containerlab: OFF**
- Existing distro(s) (e.g. `Ubuntu`): unchanged, left ON

This is the step that actually prevents the conflict described in
section 1 — it stops Docker Desktop's engine from being what `docker`
resolves to inside the `Containerlab` distro.

## 5. Install Docker CE + containerlab inside the distro

One combined setup script, official from containerlab.dev:

```bash
curl -sL https://containerlab.dev/setup | sudo -E bash -s "all"
```

Installs a native Docker CE (not Docker Desktop's engine) and
containerlab together.

## 6. Verify

```bash
docker version   # Client + Server should both say "Docker Engine - Community"
clab version
```

This machine: Docker CE 27.5.1, containerlab 0.79.0.

## 7. Known gotcha: deploy from native filesystem, not `/mnt/c/...`

The NetMind-AI repo lives on the Windows drive
(`C:\MyWorkSpace\AI-Projects\NetMind-AI`, reachable inside WSL as
`/mnt/c/MyWorkSpace/AI-Projects/NetMind-AI`) so it's reachable by the
Claude device bridge and any Windows-side tooling. Topology *source*
files stay there. But running `clab deploy` with the topology file (and
therefore its generated `clab-<lab>/` state directory) under
`/mnt/c/...` fails:

```
Setting permissions for file '/etc/opt/srlinux/config.tmp' failed
with error_code = 1 [Operation not permitted]
```

Cause: WSL2's DrvFs (the `/mnt/c/...` view of the Windows drive) doesn't
support the POSIX permission bits SR Linux needs to chmod its own config
files during commit. Fix: always sync the repo to a native Linux path
before deploying — use `scripts/sync-to-lab.sh` rather than copying
files by hand, since topologies can bind-mount other files (e.g.
`telemetry/collectors/gnmic.yaml` for component #2) that need to move
along with them:

```bash
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/sync-to-lab.sh
cd ~/netmind-lab/lab/topologies
sudo clab deploy -t <file>.clab.yml
```

Edit files in the repo (so git/the device bridge sees them), then
re-run the sync script before the next deploy.

## 8. Install gnmic (gNMI CLI client)

Not bundled with containerlab — install separately, inside the
`Containerlab` distro:

```bash
bash -c "$(curl -sL https://get-gnmic.openconfig.net)"
```

## 9. Install rsync

Not present in the base `wsl-containerlab` image. `scripts/sync-to-lab.sh`
depends on it (see section 11) to mirror the repo — install once per
distro:

```bash
sudo apt update
sudo apt install -y rsync
```

## 10. Personal SSH key for git push

The distro's baked-in key (`id_ecdsa` inside `~/.ssh/`) is identical
across every download of the `wsl-containerlab` image — it's fine for
its original purpose (`ssh clab@localhost`), but not for pushing to a
personal GitHub account: using it as-is produces "no push permission"
errors, since it isn't registered against your account. Generate and
register a personal key instead, once per distro:

```bash
ssh-keygen -t ed25519 -C "<your GitHub email>"
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub   # paste this into GitHub -> Settings -> SSH and GPG keys
ssh -T git@github.com       # should greet you by username if it worked
```

## 11. Deploy the lab and verify it's a live gNMI target

```bash
cd ~/netmind-lab/topologies
sudo clab deploy -t netmind-2node.clab.yml

gnmic -a clab-netmind-2node-srl1 -u admin -p 'NokiaSrl1!' --skip-verify capabilities
```

Default SR Linux credentials are `admin` / `NokiaSrl1!` unless
containerlab prints a randomized password in the deploy output — check
there first if login fails.

A working `capabilities` response returns SR Linux's full YANG model
list (native `srl_nokia-*` models, OpenConfig models, the IETF NETCONF
monitoring model) plus supported encodings (JSON_IETF, PROTO, ASCII).
That response is the sign this environment is ready for component #2
(the telemetry collector) to point at.

For everyday use once the lab exists, prefer the single-command
wrappers over the raw `clab deploy`/`destroy` shown above and in
section 7 — see `lab/README.md`'s "Starting and stopping the lab"
section:

```bash
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/lab-up.sh
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/lab-down.sh
```

`lab-up.sh` also fixes a real gotcha the raw commands don't: after a
laptop/WSL2 restart, a plain sync + `clab deploy` can leave the SR
Linux nodes stuck `Exited` even though the other containers come back
— see `lab/README.md` for the full diagnosis (a stale `rsync --delete`
wiping containerlab's own generated per-deploy state).

## 12. Tear down

```bash
sudo clab destroy -t netmind-2node.clab.yml --cleanup
```

(or `scripts/lab-down.sh`, shown above in section 11.)

---

## Kubernetes — installed and verified (BACKLOG.md item 4)

**Status (updated 2026-09-18):** this section previously said "not
installed yet." That went stale once k3s + Cilium were actually
installed and verified (2026-09-17, `PROGRESS_LOG.md` entry 53) and a
real workload was deployed on top of them (2026-09-18, entry 62) — same
"catch the stale doc" discipline as every other component here.

Kubernetes is a real, hands-on gap in the current skill set (per
`docs/roadmap/SIGNAL_PATH.md`) and phase 2 of the roadmap, and the
network lab's design anticipated it from the start: component #1's
topology reserves a second interface (`e1-2`) on each SR Linux node for
the lab to sit *underneath* the Kubernetes/Cilium cluster as its
underlay, rather than the two running as unrelated siblings (decided
2026-09-10). That underlay wiring (Cilium peering BGP with `srl1` over
`e1-2`) is the one piece of item 4 still open — see
`docs/roadmap/BACKLOG.md` item 4 for current status.

**Where it actually got installed, and why:**

- **Not** Docker Desktop's built-in Kubernetes toggle. It would run
  inside Docker Desktop's own hidden WSL2 VM — the exact same
  kernel-namespace isolation problem described in section 1, just one
  layer up. A Cilium CNI running there could not reach the veth
  interfaces containerlab creates in the `Containerlab` distro.
- **Instead**, k3s — genuinely upstream Kubernetes, single binary, fast
  to stand up — installed natively inside the same `Containerlab`
  distro, sharing its kernel and network namespace with the
  containerlab-managed nodes:
  ```bash
  curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--flannel-backend=none --disable-network-policy --disable=traefik --disable=servicelb" sh -
  ```
  (no default CNI — Cilium replaces it from the start; traefik/servicelb
  disabled, not needed for this lab). Then Cilium as CNI via the Cilium
  CLI (`cilium install`), verified with `cilium status --wait` and
  `cilium connectivity test` (78/79 passing — the one failure is a
  benign, documented kernel-feature gap, see entry 53).

**Known environment bug, hit and fixed (2026-09-18, entry 62): CoreDNS
crash-looping, all in-cluster DNS broken.** After deploying the first
real workload (`k8s/proof-app/`), every Service-name lookup failed with
`curl: (6) Could not resolve host`. Root-caused, not guessed: `kubectl
-n kube-system get pods -l k8s-app=kube-dns` showed CoreDNS stuck at
`0/1 Ready` with 19+ restarts; its logs showed a repeating
`HINFO ... read udp ...->10.255.255.254:53: i/o timeout` — CoreDNS's
own built-in loop-detection self-check, failing because it couldn't
reach its configured upstream forwarder. That address, `10.255.255.254`,
is WSL2's own internal DNS-forwarding proxy (confirmed matching
`/etc/resolv.conf` on the host) — reachable from the WSL2 shell
directly, but not from inside a pod's separate Cilium-managed network
namespace, a documented WSL2 pattern
([microsoft/WSL#6237](https://github.com/microsoft/WSL/issues/6237)).

**Fix:** k3s's CoreDNS ConfigMap is explicitly "managed by k3s, do not
edit" (overwritten on every k3s restart), but k3s ships a supported
override mechanism for exactly this case — a separate `coredns-custom`
ConfigMap that the managed Corefile already imports
(`import /etc/coredns/custom/*.override`), documented at
[docs.k3s.io/advanced](https://docs.k3s.io/advanced). Applied via
`k8s/coredns-custom.yaml` (committed to this repo so a fresh cluster
rebuild picks up the fix automatically rather than silently
regressing):
```bash
kubectl apply -f k8s/coredns-custom.yaml
kubectl -n kube-system rollout restart deployment coredns
```
Verified live: CoreDNS came back `1/1 Running`, `RESTARTS 0`, held
there across a real test, and its logs no longer show the `HINFO`
timeout. **Apply this manifest on every fresh cluster build, right
after Cilium is verified healthy** — without it, in-cluster DNS is
broken from the start on this specific machine/WSL2 setup.

**First real workload, deployed and verified (`k8s/proof-app/`, entry
62):** a minimal 2-replica Flask app + ClusterIP Service — proof beyond
`cilium connectivity test`'s own synthetic pods that a real
Deployment/Service/scaling path works. Verified with repeated `curl`s
against the Service name landing on different pod names across
requests — genuine Service load-balancing through Cilium's eBPF
datapath, not just "pods say Running." See `k8s/proof-app/README.md`
for the full build/deploy/verify steps.
