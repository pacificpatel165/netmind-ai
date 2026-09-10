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
files during commit. Fix: always copy the topology file to a native
Linux path before deploying —

```bash
mkdir -p ~/netmind-lab/topologies
cp /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/lab/topologies/<file>.clab.yml ~/netmind-lab/topologies/
cd ~/netmind-lab/topologies
sudo clab deploy -t <file>.clab.yml
```

Edit the topology in the repo (so git/the device bridge sees it), then
re-copy before the next deploy. This is annoying enough that it's worth
a small sync script once there are more than one or two topology files
— not built yet.

## 8. Install gnmic (gNMI CLI client)

Not bundled with containerlab — install separately, inside the
`Containerlab` distro:

```bash
bash -c "$(curl -sL https://get-gnmic.openconfig.net)"
```

## 9. Deploy the lab and verify it's a live gNMI target

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

## 10. Tear down

```bash
sudo clab destroy -t netmind-2node.clab.yml --cleanup
```

---

## Kubernetes — not installed yet

Kubernetes is real, hands-on gap in the current skill set (per
`docs/roadmap/SIGNAL_PATH.md`) and phase 2 of the roadmap, and the
network lab's design already anticipates it: component #1's topology
reserves a second interface (`e1-2`) on each SR Linux node for the lab
to sit *underneath* a future Kubernetes/Cilium cluster as its underlay,
rather than the two running as unrelated siblings (decided
2026-09-10, see `PROGRESS_LOG.md`).

That constrains **where** Kubernetes should get installed, when it's
time:

- **Not** Docker Desktop's built-in Kubernetes toggle. It would run
  inside Docker Desktop's own hidden WSL2 VM — the exact same
  kernel-namespace isolation problem described in section 1, just one
  layer up. A Cilium CNI running there could not reach the veth
  interfaces containerlab creates in the `Containerlab` distro.
- **Instead**, a lightweight cluster (k3s is the natural choice —
  genuinely upstream Kubernetes, single binary, fast to stand up)
  installed natively inside the same `Containerlab` distro, sharing its
  kernel and network namespace with the containerlab-managed nodes.
  That's what makes a Cilium-as-underlay design actually reachable
  later.

Nothing has been installed for this yet — it's queued behind finishing
component #1's topology work and isn't required to start component #2
(the telemetry collector only needs the SR Linux nodes, not Kubernetes).
When it's time, the expected first steps are: install k3s in the
`Containerlab` distro, verify with `kubectl get nodes`, then install
Cilium as the CNI before wiring it to the lab's reserved interfaces.
