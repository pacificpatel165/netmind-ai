# Host bootstrap via Ansible (BACKLOG.md item 11)

Closes a real gap named explicitly in `docs/setup/01-network-lab-environment.md`:
everything from "Docker CE installed" through "kubeconfig wired up and the
Cilium CLI present" used to only exist as commands a person typed by hand,
reading that doc top to bottom. Two of those steps (kubeconfig wiring,
Cilium CLI install) were only ever run once, live, in a terminal — found
missing from the doc entirely during a 2026-09-18 audit. This playbook is
the fix: one idempotent, re-runnable file instead of a procedure that lives
in a person's memory.

**Why Ansible, not Terraform, for this specific piece:** Terraform declares
resources that don't yet exist (see `cloud/aws-networking/`, already using
it for exactly that). This is the opposite problem — an *existing* machine
that needs to be brought into a known configuration state (packages
installed, files in place). That's configuration management, Ansible's
actual job. See the "Infrastructure as Code" explainer for the fuller
reasoning behind this split.

## What's here

- `bootstrap-lab-host.yml` — the playbook itself. Every task checks first
  and only acts if something's actually missing — safe to run on a
  brand-new distro or an already-bootstrapped one.

## What it does — and deliberately doesn't

Automates (mirrors `docs/setup/01-network-lab-environment.md`'s numbering):

- §9 — installs `rsync`
- §5 — installs Docker CE + containerlab (the official combined script)
- §8 — installs `gnmic`
- §10 — generates a personal `ed25519` SSH key (key only)
- Kubernetes section — wires up a normal-user `kubeconfig` from k3s's own
  (only if k3s is already installed — see below), and installs the Cilium
  CLI

**Deliberately left manual, and why:**

- §2 (`wsl --update`) and §3 (installing the `wsl-containerlab` distro
  itself) run on Windows, before this distro — and therefore Ansible
  inside it — exists at all.
- §4 (Docker Desktop's WSL integration toggle) is a Windows-side Docker
  Desktop GUI setting, not reachable from inside the distro.
- Registering the generated SSH public key on GitHub needs a human logged
  into GitHub's UI with their own credentials — this playbook can generate
  the key, not register it.
- Installing k3s and Cilium themselves aren't included. Both are already
  effectively single, already-idempotent commands (`curl -sfL
  https://get.k3s.io | ...`, `cilium install`) — the actual pain point this
  playbook targets is everything *around* them that wasn't written down
  anywhere, not those two commands themselves. The kubeconfig task here
  checks whether k3s is already installed and skips (with a clear message)
  rather than failing if it isn't yet.

## One-time setup

0. **Fix the locale first — Ansible won't run at all without it.** Found
   live, 2026-09-19: the `wsl-containerlab` image has no UTF-8 locale
   generated (`locale -a` shows only `C`, `C.utf8`, `POSIX`), and Ansible
   refuses to start with `ERROR: Ansible could not initialize the
   preferred locale: unsupported locale setting` — even `ansible
   --version` alone fails, before this playbook is even involved. Fix with
   glibc's built-in `C.UTF-8` locale (already present, no `locale-gen`
   needed, unlike `en_US.UTF-8` which usually isn't on a minimal image):
   ```bash
   locale -a   # confirm C.utf8 is there before relying on it
   export LC_ALL=C.UTF-8
   echo 'export LC_ALL=C.UTF-8' >> ~/.bashrc
   echo 'export LC_ALL=C.UTF-8' >> ~/.profile
   ```
   Open a new terminal (or `source ~/.bashrc`) before continuing.

1. **Install Ansible itself:**

```bash
pip install --user ansible-core --break-system-packages
```

2. If this is a brand-new distro and `~/.local/bin` isn't on `PATH` yet, fix
that first (same PATH gap hit three times during the AWS/LocalStack
exercise — see `cloud/aws-networking/README.md` step 0 for the full
explanation, same fix reused here):

```bash
grep -q '.local/bin' ~/.bashrc || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
grep -q '.local/bin' ~/.profile 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.profile
```
Then open a genuinely new terminal (not just re-source `.bashrc`) before continuing.

```bash
ansible --version   # confirm it actually installed before using it
```

## Running it

From `~/netmind-lab/provisioning/ansible/` (synced the same way every other
component is — `scripts/sync-to-lab.sh` copies the whole repo):

```bash
cd ~/netmind-lab/provisioning/ansible
ansible-playbook bootstrap-lab-host.yml -e "git_email=you@example.com"
```

`git_email` is used only as the comment on the generated SSH key — pass
your real GitHub-registered email so the key is identifiable later. If
omitted, the playbook still runs (uses a placeholder and warns about it),
it just leaves the key's comment unhelpful.

Safe to re-run any time — on an already-bootstrapped machine, every task
reports `ok` (nothing changed), not an error.

## Verifying it

The playbook itself ends with a summary task that re-checks every tool's
*actual* real state (not the task results, which only say "did I run the
install step," not "does the binary genuinely work now") and prints one
line per tool:

```
TASK [Print end-state summary] ***
ok: [localhost] => (item=Docker) => { "msg": "Docker: OK — Docker version ..." }
ok: [localhost] => (item=containerlab) => { "msg": "containerlab: OK — ..." }
...
```

Independently, the same checks the setup doc's own sections already use:

```bash
docker version
clab version
gnmic version
rsync --version
kubectl get nodes          # only meaningful if k3s was already installed
cilium version --client
```

**Verified live, 2026-09-19**, after fixing a real locale bug (step 0
above — found on this same run, not hypothetical). Real play recap from
the actual machine:

```
PLAY RECAP *********************************************************
localhost : ok=15  changed=1  unreachable=0  failed=0  skipped=9  rescued=0  ignored=0
```

The one `changed` task was `Ensure ~/.kube exists` — tightening that
directory's permissions to `0700`, a genuine correct fix, not a bug.
Every other task reported `ok` (already installed, nothing to do — the
idempotency guards worked exactly as designed) or `skipping` (Cilium CLI
and kubeconfig wiring, both already in place from earlier sessions).

**Important honesty caveat:** because this machine was already bootstrapped
from earlier sessions before this playbook existed, this run only
exercised the "already installed, skip" code paths. The actual
first-time-install branches — the Docker CE/containerlab combined script,
the gnmic install script, and the Cilium CLI download-and-verify block —
were never triggered here, since their `when:` guards all evaluated false.
Those paths stay unverified until a genuinely blank machine runs this
playbook, which is exactly what BACKLOG.md item 41 (from-scratch rebuild
test) is for. Item 11 is closed for the idempotency/skip-path guarantee;
full first-time-install verification is deferred to item 41, not skipped.
See `PROGRESS_LOG.md` for the full entry.

## After running this

1. Register the generated key on GitHub: `cat ~/.ssh/id_ed25519.pub`, paste
   into GitHub → Settings → SSH and GPG keys.
2. `ssh -T git@github.com` should greet you by username.
3. If Docker Desktop's WSL integration for this distro is still ON, turn
   it OFF (§4 of the setup doc) — this playbook can't do that step for you.
4. Continue with `docs/setup/01-network-lab-environment.md` §11 onward
   (deploy the lab) as normal.
