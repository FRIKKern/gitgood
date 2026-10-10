# Proposed Gitgood pilot target

Selected for planning by the Codex primary agent on 10 October 2026 after Frikk
asked for the best deployment choice. This is a proposed target and budget,
not a configured provider allocation or a deployment result.

Use a separate Hetzner Cloud project for Gitgood's pilot, with its own Ubuntu
24.04 x86_64 VM in the EU. Prefer Helsinki, subject to actual provider inventory
and the application's deployment capability checks. Target CPX32: four shared
vCPUs, eight GB RAM and 160 GB NVMe. Run the pinned Elixir backend, web service,
Git, edge and Postgres on this installation; keep CI and untrusted execution
outside its credentials and storage.

The size is an initial pilot hypothesis. Verify it against the declared pilot
workload and resource limits before making capacity claims. Shared CPU performance
can vary. Preserve the supported host profile when selecting any alternative;
an ARM host is not admitted by the current x86_64 packaging and service proofs.

## Sizing evidence and rollout

Use the existing [bounded pilot workload](../docs/implementation/pilot-workload.md)
to assess this choice: its deterministic 2,000-file repository, 500 main commits,
eight independently authorized concurrent readers and sequential import/clone
operations. Preserve its four-vCPU, 4-GiB reference profile and fixed targets.
Measure the proposed 8-GB provider host as a separately identified environment;
extra memory is operational headroom, not evidence that the reference passed.
Record actual CPU allocation, service limits, storage, concurrent services,
certificate-validated network paths, every failed sample and candidate identity.

Before inviting the pilot team, pass the native installation and J01/J02 workflow
on the pinned artifact, run the workload with outsider-denial checks, and prove
coordinated recovery on a replacement host. Keep the provider project distinct
from Barkpark's existing production services. Bind Cloud inventory and lifecycle
operations to the independently enrolled project and installation identities.
Review measured CPU, memory, storage growth and recovery cost before resizing;
retain the initial measurements when recording any revised capacity decision.

## Planning budget

The provider's published EU CPX32 price is EUR 35.49/month excluding VAT and IPv4.
Daily provider backups add 20%, and primary IPv4 adds EUR 0.50/month, for a server
and provider-backup subtotal of approximately EUR 43.09/month before VAT.
Recommend EUR 60/month before VAT as the initial planning budget, including an
allowance for separately stored encrypted recovery material and temporary restore
tests. That allowance is an estimate, not a quoted backup-storage order.
The EUR 60 planning envelope covers the pilot installation and recovery allowance;
a separately hosted CI worker fleet and production high availability need their
own budgets. Confirm current prices, availability, project scope and the complete allocation cost
before provisioning. No paid resource has been created by this plan.

## Ownership and recovery

Barkpark Cloud owns constrained deployment, inventory and reported lifecycle
status through a supported native workload contract. Gitgood owns its immutable
artifacts, application admission, migrations, functional readiness and coordinated
recovery. The installed forge must remain operable during a Cloud outage.

Keep the provider administration credential outside the installation account.
Allocation must independently seal the actual project, host and installation
identities. An empty project or a matching resource name does not establish
ownership. Reservations, cancellation and retained uncertain effects require
implementation before connecting provider mutations.

Keep encrypted coordinated backups on separate storage, preferably in another
EU location, and prove replacement-host restoration. Provider snapshots are an
additional recovery layer: running-server snapshots do not guarantee consistent
disk state, attached volumes are excluded, and ordinary server backups disappear
when their source server is deleted. Retain required recovery material independently
of the installation's removal lifecycle.

## Remaining deployment gates

The native controller, application leases and markers, all affected lifecycle
interruptions, deployed database authentication, allocator, supported Cloud
contract and configured project credentials remain required. Complete J14 still
requires clean-host installation and the functional J01/J02 workflow against the
actual pinned artifact. This document changes no journey or release criterion.

## Sources checked on 10 October 2026

- [CPX32 specifications](https://www.hetzner.com/cloud/regular-performance/).
- [Published EU cloud prices](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/).
- [Backup billing](https://docs.hetzner.com/cloud/billing/faq/).
- [Primary IPv4 pricing](https://docs.hetzner.com/general/infrastructure-and-availability/ipv4-pricing/).
- [Provider backup and snapshot limitations](https://docs.hetzner.com/cloud/servers/backups-snapshots/faq/).
