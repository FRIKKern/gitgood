# Native service supervision and resource generations

Accepted for implementation, 10 October 2026, by the Codex primary agent.
The service capability experiment passed; this decision installs no product
supervisor and establishes no reboot or Cloud acceptance.

## Service boundary

Use one persistent systemd service per installation on the Ubuntu 24.04 x86_64
profile. Its fixed controller runs as an ordinary installation account in the
delegated driver leaf. The account manages native, web, edge and maintenance
siblings beneath that service. systemd owns the hierarchy above the delegation.
Require actual CPU/memory delegation, membership, permissions, unit identity
and bounds. Reject unsupported capabilities before staging.

The [actual experiment](../implementation/native-supervision-profile.md) passed
eight checks on systemd 255.4, including whole-unit descendant cleanup and
bounded restart after manager loss. All five group inodes changed across both
start transitions at unchanged paths. A stable path or unchanged kernel boot
therefore cannot authorize reuse of an old resource binding.

The privileged host allocator establishes the account, service, limited database
role and private resources. The ordinary controller receives no provider token
or database administration privilege. Keep allocation and runtime responsibility
separate. Actual allocation and deployed database authentication remain required.

## Identity and generation

Create a distinct protocol-2 systemd profile. Separate its persistent installation
binding from its current kernel resource generation.

| Record | Required meaning |
|---|---|
| Durable installation binding | Installation UUID, supported host identity/account, private directory identities, configuration/key checksums, PostgreSQL cluster/database/role identity and pinned executable identities. |
| Resource generation | Unique generation, predecessor digest, boot/namespaces, independently observed service definition/parent, current controller birth and exact five group identities. |
| Lifecycle responsibility | Original immutable operation and input digests, durable binding, generation at claim and retained stage observations. |
| Generation transition | Sealed continuity observation, prior/new generations and the exact unfinished responsibility being reconciled. |
| Current publication | A durable atomic pointer to the validated generation; publication requires actual continuity and exclusive ownership. |

Names, paths, numeric generations and healthy endpoints are insufficient.
Observe persistent resources independently before accepting a new generation.
Acquire the existing installation-wide OS lock and establish database writer
exclusion. Prove old same-boot owners and descendants are gone by exact identity;
a previous boot proves an old process cannot remain, but authorizes no signal
against a current process or a recreated group.

Reconcile uncertain stage effects against persistent state. Preserve original
requests, observations, baselines and locks; reference them through the transition.
Never replace their bindings to make old responsibility appear current. Publish
the new generation only after its required observations pass. Interrupted
transition publication must be independently observable and safely resumable.
An unavailable database or uncertain history leaves the service stopped with
visible responsibility.

## Lifecycle coordination

The controller checks the lifecycle lock and retained history before restarting
runtime. It must not revive runtime during migration, backup, restore, upgrade or
retirement, or while an unfinished stage requires reconciliation. PostgreSQL
advisory leases continue to enforce runtime/maintenance writer exclusion.
Runtime and maintenance markers need protocol-2 boot/generation and actual group
identities; a stale protocol-1 marker cannot authorize a changed generation.

Use a private, bounded local command interface for fixed lifecycle commands and
status. Verify peer account identity and independently sealed inputs. Dispatch
the existing stage engines inside the owned service boundary; accept no arbitrary
program, shell, environment or provider command. One mutation owns the lifecycle
lock. Losing a caller response does not abandon or duplicate its operation.
Status distinguishes retained progress, uncertain effects, service failure and
actual functional readiness.

Apply bounded restart and start-rate limits. Distinguish persistent identity or
configuration refusal from transient runtime failure before selecting retry
behavior. Every activation still needs the expected artifact/schema, routing,
authorization and functional access checks. This decision does not promise
zero downtime.

## Protocol-1 compatibility

Retain the existing development profile and original same-boot refusal rules.
Its journals and activation records remain immutable.

A separately sealed conversion may admit a terminal initial baseline and
terminal upgrade chain after full continuity observation. It must refuse any
unresolved initial handoff, nonterminal upgrade, retirement responsibility or
uncertain restore. Do not silently convert an unfinished protocol-1 operation
after its kernel bindings changed. Such recovery requires its own explicit
implementation and evidence; it is outside this first conversion.

Fresh protocol-2 installations must support generation-aware reconciliation of
their own unfinished stages. This preserves the first-release interrupted
provisioning requirement without fabricating legacy support.

## Implementation order and gates

1. Implement read-only service admission and closed generation records; exercise
   actual delegation, unsupported capabilities and replacement/refusal cases.
2. Implement durable continuity, transition custody and atomic publication.
   Test lost publication acknowledgements and competing controllers.
3. Add generation-aware application leases/markers and fixed lifecycle dispatch.
   Reproduce database outage, restart limits and all affected interruption cases.
4. Boot an owned VM with its own kernel. Exercise actual reboot and compare
   changed boot/resource identities with unchanged persistent data and history.
   Process or namespace recreation on WSL is separate evidence.
5. Reproduce initial installation, upgrade, backup and retirement under the new
   profile; add terminal-only legacy conversion and its refusal cases.
6. Implement allocation/reservation/cancellation and the supported Barkpark Cloud
   native workload contract, then reproduce complete J14/J01/J02 criteria.

Each gate needs current source/artifact applicability and required CI. No
journey criterion or release requirement is removed. The [host prerequisites](../implementation/native-host-prerequisites.md)
remain the dependency checklist.
