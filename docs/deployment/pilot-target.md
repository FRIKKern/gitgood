# Gitgood Pilot target

Selected planning target on 11 October 2026, following delegated infrastructure
judgment. No provider allocation, paid reservation or Cloud enrollment has run.

Use a separate **Gitgood Pilot** Barkpark Cloud infrastructure project. Keep its
provider resources, installation identity, routes and billing distinct from the
existing Studio and development environments. Barkpark Cloud must provision it
through its supported native workload contract; a static/container/Node job does
not substitute for the required native allocator and supervisor.

The initial host target is Hetzner **CCX23**, with four dedicated AMD vCPUs,
16 GB RAM and 160 GB NVMe, running Ubuntu 24.04 on x86-64. Prefer Helsinki,
with Nuremberg as the capacity fallback. Dedicated CPUs give a predictable
baseline for Git subprocesses, database work and concurrent application reads.
This is a sizing choice; capacity still needs the
[bounded pilot workload](../implementation/pilot-workload.md).

The provider's [general-purpose catalog](https://www.hetzner.com/cloud/general-purpose/)
was checked for these specifications. Its public page currently displays an
unavailable notice. Actual regional stock and the exact payable quote must be
observed through the configured provider account before allocation; availability
is not established by this plan.

Plan **EUR 120 per month before VAT** for the pilot host, encrypted off-host
backup, and modest networking/operating headroom. This is a planning envelope,
not a provider price quotation. Record the actual host, backup, storage and
traffic charges against it once the target exists. CI needs a separate budget
and execution environment; it must not consume application credentials or
installation storage. Growth beyond this small private-team pilot requires
measured demand and a recorded budget/sizing revision.

Start with one native application installation and PostgreSQL on the host, with
separate service roles, protected allocation and private stores. Avoid extra
distributed services until measured load or recovery requirements justify them.
Application/native worker resource limits remain independently enforced; a
larger host does not relax their existing admission checks.

Before inviting users, establish the supported Cloud allocation/enrollment path,
actual installed artifact identity, authorization and Git workflows, and a
successful restoration on a replacement host from encrypted off-host backups.
The remaining product release criteria in PRODUCT.md and QUALITY.md still
apply. Recovery targets must come from the workload experiments, rather than an
unmeasured promise. Current infrastructure credentials and the actual project
identity remain unconfigured.
