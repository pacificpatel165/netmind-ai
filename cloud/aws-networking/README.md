# AWS Networking on LocalStack (BACKLOG.md item 29)

Closes the one explicitly-named resume gap besides Kubernetes: public-cloud
networking, provisioned with real IaC (Terraform), distinct from the
on-prem/telecom NETCONF/RESTCONF background. Runs against LocalStack's free
Community Edition, not a real AWS account — same "prove it, then write the
ADR" discipline as every other component in this project, just against a
simulated AWS API instead of the SR Linux lab.

**Scope (deliberately minimal, matches the backlog exit criterion exactly):**
a 2-tier VPC — public subnet + private subnet, an Internet Gateway, route
tables, and two security groups that reference each other (`web-sg` /
`db-sg`) — the smallest topology that actually exercises VPC, subnet,
routing, and security-group concepts rather than a single flat network.

**Why Terraform:** industry-standard declarative IaC, not yet on the
resume, and it's a real, reusable pattern (state file, plan/apply, modules)
rather than a one-off script — closes an IaC gap alongside the AWS gap in
the same exercise.

**Why the `Containerlab` WSL2 distro:** it already has a proven, working
Docker CE install (same one running the SR Linix lab and k3s/Cilium this
project) — no new environment to stand up or verify from scratch.

## What's here

- `main.tf` — provider config pointed at LocalStack's endpoint, VPC,
  subnets, IGW, route tables + associations, security groups.
- `variables.tf` — region, CIDRs, tags — all overridable, sensible
  defaults committed.
- `outputs.tf` — VPC ID, subnet IDs, security group IDs (what you'd wire a
  real workload to next).

## One-time setup (run inside the `Containerlab` WSL2 distro)

0. **Fix `PATH` first, once, before installing anything.** `pip install
   --break-system-packages` on this distro installs to a per-user
   directory (`~/.local/bin`) that isn't on `PATH` by default, and
   `~/.bashrc` alone doesn't reliably cover every way a terminal gets
   opened here — this bit `localstack`, then `awslocal`, three separate
   times in the same session before being fixed at the root. Do this
   once, covering both `.bashrc` and `.profile` so it survives any shell
   type, then open a genuinely new terminal (not just re-run a command)
   before continuing:
   ```bash
   grep -q '.local/bin' ~/.bashrc || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
   grep -q '.local/bin' ~/.profile 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.profile
   grep local/bin ~/.bashrc ~/.profile   # confirm both actually have it
   ```

1. **Install LocalStack** — the `localstack` package here is only the CLI
   (a host-side Python tool); the actual AWS-API emulator still runs as a
   Docker container, launched by that CLI. `awslocal` (used for
   verification below) is a separate package, install it at the same time:
   ```bash
   pip install localstack awscli awscli-local --break-system-packages
   # or, if you'd rather not touch the system Python at all:
   #   pipx install localstack
   ```

   **Correction, 2026-09-18 — this originally said "free, no account
   needed."** That was true when LocalStack shipped a standalone
   Apache-licensed Community Edition; it isn't true anymore. LocalStack
   merged Community and Pro into one image earlier in 2026 and now
   requires a free account + auth token to start at all, even for
   personal/non-commercial use (the old
   `LOCALSTACK_ACKNOWLEDGE_ACCOUNT_REQUIREMENT=1` bypass expired
   2026-04-06). Sign up free at `https://app.localstack.cloud`, grab the
   auth token from the web app, then:
   ```bash
   localstack auth set-token <your-token-here>
   ```

2. **Start LocalStack** (spins up a Docker container exposing the AWS API
   on `localhost:4566` — confirm it's really containerized with
   `docker ps`, you should see a `localstack-main` container):
   ```bash
   localstack start -d
   localstack status services   # wait until ec2 shows "available"
   ```

3. **Install Terraform** (HashiCorp's apt repo — the standard install
   path):
   ```bash
   wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg

   CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
   echo "codename: $CODENAME"   # sanity check -- must not be blank before continuing

   echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com ${CODENAME} main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
   sudo apt update && sudo apt install -y terraform
   terraform -version
   ```

   **Correction, 2026-09-18** — the original version of this step used
   `$(lsb_release -cs)` to get the distro codename. The `Containerlab`
   distro doesn't have the `lsb_release` command installed (it's a
   minimal WSL2 image), so that substitution silently expanded to
   nothing, producing a malformed `.list` file (`apt` rejected it with
   "Malformed entry 1 (Component)") and leaving Terraform uninstalled.
   Fixed by reading `/etc/os-release` directly instead — present on
   effectively every Debian/Ubuntu system, including minimal ones, so
   nothing extra needs installing first. If a retry leaves a corrupted
   keyring behind (`gpg --dearmor` refusing to overwrite an existing
   file non-interactively), clear both files first:
   `sudo rm -f /usr/share/keyrings/hashicorp-archive-keyring.gpg /etc/apt/sources.list.d/hashicorp.list`.

## Running it

From `~/netmind-lab/cloud/aws-networking/` (synced the same way every other
component is — `scripts/sync-to-lab.sh` already copies the whole repo,
this directory rides along with it):

```bash
cd ~/netmind-lab/cloud/aws-networking
terraform init
terraform plan
terraform apply -auto-approve
```

## Verifying it

Terraform's own `apply` output already proves the resources were created
(LocalStack returns real-shaped AWS resource IDs, `vpc-xxxxxxxx` etc.), but
verify independently against the LocalStack API directly too, the same way
every other component here gets checked against the real system rather
than just trusted:

```bash
# awslocal is a *separate* package (awscli-local) that wraps the real AWS
# CLI and auto-points it at localhost:4566 -- it is NOT bundled with the
# localstack pip package (a wrong claim in an earlier version of this doc);
# install with `pip install awscli awscli-local --break-system-packages`
# (see step 1 above) and make sure ~/.local/bin is on PATH (see step 0).
awslocal ec2 describe-vpcs --query 'Vpcs[*].{Id:VpcId,CIDR:CidrBlock,Tag:Tags[0].Value}'
awslocal ec2 describe-subnets --query 'Subnets[*].{Id:SubnetId,CIDR:CidrBlock,AZ:AvailabilityZone,Public:MapPublicIpOnLaunch}'
awslocal ec2 describe-route-tables --query 'RouteTables[*].{Id:RouteTableId,Routes:Routes}'
awslocal ec2 describe-security-groups --query 'SecurityGroups[*].{Id:GroupId,Name:GroupName,Ingress:IpPermissions}'
```

Expected: one VPC (`10.60.0.0/16`) alongside LocalStack's own pre-populated
default VPC (`172.31.0.0/16` — not something this exercise creates, don't
be surprised to see it), two subnets (`10.60.1.0/24` public,
`10.60.2.0/24` private), the public subnet's route table showing a
`0.0.0.0/0 -> igw-...` route and the private subnet's route table showing
only the local VPC route (no default route — deliberate: this exercise
doesn't stand up a NAT Gateway, so the private subnet is genuinely
unreachable outbound, which is the correct, honest behavior for "private"
rather than faking it), and `db-sg` showing an ingress rule whose source is
`web-sg`'s group ID rather than a CIDR (the security-group-referencing-
security-group pattern, the actual point of building two tiers instead of
one).

**Verified live, 2026-09-18 (PROGRESS_LOG entry 57):** all of the above
confirmed exactly, independently of `terraform apply`'s own output —
`vpc-596022934a8a7da49`, public route table with the IGW default route,
private route table with only the local route, `db-sg`'s ingress rule
showing `UserIdGroupPairs: [{GroupId: sg-...}]` with an empty `IpRanges`.
This exercise is closed (`BACKLOG.md` item 29).

## Tearing down

```bash
terraform destroy -auto-approve
localstack stop
```

## Known LocalStack Community Edition limitation

NAT Gateways are a Pro-only feature in LocalStack — `aws_nat_gateway` isn't
provisioned here for that reason, not an oversight. The private subnet is
real: it has no default route, so anything placed in it is genuinely
unreachable from outside the VPC, same as a real private subnet with no
NAT. If a future exercise needs outbound-from-private (e.g. an instance
pulling packages), that's the point where either LocalStack Pro or a real
AWS account becomes necessary — worth deciding then, not speculatively now.
