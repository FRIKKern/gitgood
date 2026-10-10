# Native host supervision prerequisites

The current native development operator has actual same-boot installation,
interruption, upgrade and retirement evidence. A persistent host needs additional
ownership and recovery behavior before managed Cloud installation can be claimed.
This document records the remaining product dependencies. The accepted
generation design and its verified components do not yet establish a complete
installed supervisor or lifecycle recovery across reboot.

The [systemd capability experiment](native-supervision-profile.md) has since
passed eight actual service checks and four independent custody checks. An
ordinary account managed the delegated children, whole-unit stops cleared
descendants, and manager loss triggered bounded restart. All five group inodes
changed across starts at the same paths. The
[supervision/generation decision](../decisions/0018-native-supervision-generations.md)
is accepted for implementation. Generation records and publication now have
component evidence; the product controller remains unfinished.

The subsequent owned-VM experiment also passed eight actual kernel-reboot
capability checks and four independent custody checks. It preserved synthetic
durable data, machine identity and unit bytes while starting a new manager
generation after reboot. This does not establish Gitgood lifecycle recovery.
The [read-only service observer](native-service-admission.md),
[durable bindings](native-durable-bindings.md),
[generation custody](native-generation-custody.md),
[atomic publication](native-generation-publication.md),
[worker admission](native-worker-admission.md),
[completed-generation reader](native-generation-reader.md), and
[Elixir admission and held-session checks](native-elixir-generation-admission.md)
now have recorded component evidence, including actual kernel-reboot exercises.
The [periodic guard](native-generation-lease-guard.md) remains under actual-service
verification. Application lease wiring, generation-aware markers, lifecycle
admission and the fixed product controller remain required.

## Service ownership

The verified fixture runs under WSL init. Its installed systemd binary is
255.4-1ubuntu8.17, but systemd is not PID 1. The current
[inventory](../../tools/deployment/native_inventory.py) expects children directly
under `/sys/fs/cgroup/gitgood-installation-UUID`.

On a systemd host, systemd owns the root hierarchy. Its
[delegation contract](https://systemd.io/CGROUP_DELEGATION/) gives a service or
scope ownership of a delegated subtree, with one writer beneath that boundary.
The installation therefore needs an independently verified persistent service
parent and driver/native/web/edge/maintenance children. Actual available
controllers, ownership and driver membership must be checked; unit text alone
does not establish those capabilities.

Evaluate `DelegateSubgroup=driver` against the actual supported systemd version.
The [systemd 255 resource-control contract](https://raw.githubusercontent.com/systemd/systemd/v255/man/systemd.resource-control.xml)
describes initial subgroup placement. Whole-unit stop must remove descendants;
[KillMode=control-group](https://raw.githubusercontent.com/systemd/systemd/v255/man/systemd.kill.xml)
covers remaining unit processes. A bounded restart policy may use
[Restart=on-failure](https://raw.githubusercontent.com/systemd/systemd/v255/man/systemd.service.xml)
and start-rate limits. Process restart must still verify artifact identity,
exclusive database responsibility, actual routing and functional access.

## Durable identity and resource generations

Protocol 1 seals persistent database/store/configuration/key identities together
with executable and cgroup identities. Its
[upgrade history](../../tools/deployment/upgrade_history.py) requires one bindings
digest across all operations. Initial inputs also bind the original boot and
namespaces. A reboot can change those kernel identities while preserving the
database and stores. A supervisor cannot silently substitute new values.

The accepted design separates durable installation identity from a current
resource generation. The implemented publication component requires independent
observation of the original database cluster, database/role OIDs, stores,
configuration and keys, plus the new owned service subtree, boot and namespaces.
Names, paths or a healthy endpoint cannot establish continuity by themselves.

Preserve original baselines, journals, observations and lock identities. Any
legacy conversion needs a separately sealed operation and explicit compatibility
rules. Resolve unfinished protocol-1 recovery semantics before supporting a
cross-boot transition; do not rewrite an old allocation or request digest to
make it appear current. Runtime and maintenance markers also need explicit
generation semantics before changed kernel identities can be accepted.

The persistent controller must coordinate with the installation-wide lifecycle
lock and fixed private inputs. Runtime restart, migration, backup, upgrade and
retirement must retain exclusive responsibility. An uncertain lifecycle stage
must remain visible and be reconciled against actual effects.

## Required experiments

Use an owned systemd host to exercise actual service admission, start/stop,
controller loss, runtime descendant cleanup, unavailable database and bounded
restart. Verify existing data, credentials and history survive, unsupported
capabilities refuse early and unrelated processes remain untouched.

Actual reboot with changed kernel resource identities has been exercised for
the linked components above. Same-boot process termination or namespace
recreation remains separate evidence. Repeat installation-stage interruption
and installed upgrade/retirement behavior under the resulting generation-aware
application and controller before claiming complete product reboot recovery.

Host allocation, reservation and cancellation need durable ownership and
reconciliation before provider operations are connected. Establish deployed
database authentication and limited credentials separately from the current
loopback trust privilege experiment. Finally connect Barkpark Cloud through a
supported native workload contract and reproduce the complete J14 criteria.
Existing static/container/node deployment kinds do not establish that contract.
