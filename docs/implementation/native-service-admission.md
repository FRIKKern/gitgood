# Native systemd service admission

The read-only [service scope observer](../../tools/deployment/native_service_scope.py)
implements the first component of [decision 0018](../decisions/0018-native-supervision-generations.md).
It does not create a supervisor or admit a durable generation transition.
Existing protocol-1 operators and their original identity rules remain intact.

## Allocation contract

The allocator must independently retain the installation UUID, the SHA-256 of
the root-owned unit definition, CPU quota and memory limit. The ordinary account
name is `gg_` followed by the lowercase, unpadded base32 encoding of the UUID's
16 bytes. This preserves the entire identity within Linux's account name limit.
The unit is `gitgood-installation-<UUID>.service` under `/etc/systemd/system`.
Allocation and provisioning of these resources are still implementation work.

The caller must execute in that unit's `driver` subgroup as its ordinary account.
An external shell cannot establish service admission by supplying matching names.
The fixed observer checks the actual manager's PID birth, UID, cgroup and mount
and cgroup namespaces, then re-observes them before returning.

Both manager and caller require the expected non-root GID, no supplementary
group beyond that GID, empty inherited/permitted/effective/bounding/ambient
capability sets and the kernel `NoNewPrivs` flag. The allocated unit must use
`NoNewPrivileges=yes`, `CapabilityBoundingSet=` and `AmbientCapabilities=`.
A non-root UID by itself cannot establish the ordinary-account boundary.

## Required host boundary

Admission requires Ubuntu 24.04 x86-64, root-owned PID 1 with the systemd command
name, the root-controlled system bus and installed and live manager version 255,
plus the initial user namespace. Linux denies ordinary users access to
`/proc/1/exe`; the observer does not claim it read that privileged link.
A remapped namespace cannot provide
apparently root-owned trust. Unit and executable files must be canonical,
root-owned, single-link, stable files beneath root-owned directories without
group or other write access. The independently supplied unit digest must match.

The observer queries a fixed selection of service properties through the trusted
`/usr/bin/systemctl`. It excludes caller credentials, bus/host overrides and
pager programs from the subprocess environment. Output and elapsed time are
bounded; failed, duplicate, missing or unexpected properties refuse admission.
No environment or credential-bearing properties are requested.

The active unit must have the expected ordinary user/group, fragment and parent
path, no drop-ins, CPU/memory delegation, `DelegateSubgroup=driver`,
`KillMode=control-group` and `Restart=on-failure`. Actual cgroup files must confirm
the retained quota with a 100 ms period, memory limit and zero swap.

The delegated parent must be empty, carry the kernel `user.delegate` marker and
enable CPU/memory controllers. Its driver/native/web/edge/maintenance groups
must belong to the service account, including the three delegated process,
kill and subtree control files. Paths and identities are re-observed to reject
replacement during observation.

## Meaning and verification limits

The returned protocol-2 observation includes the current boot, unit definition,
manager birth, group identities and limits. It explicitly sets
`installation_readiness_established` to false. It is transient evidence; callers
must never use it to signal a later process or reuse a cgroup path after a
generation change.

Twelve boundary tests cover invalid identities and limits, malformed manager
responses, credential/environment exclusion, excess output, failed processes and
timeouts and privileged process state. The complete Linux operator suite passed 221 tests with 12 expected
foreign-platform skips; 33 planning checks passed. Required candidate CI remains
a separate gate.

## Initial admission and reboot evidence

On 10 October 2026, the owned VM fixture
`7c8ede52-1b6f-4ea5-ac7c-cb572ad02986` executed the initial observer revision as UID 65503
under systemd 255.4 and kernel 6.8.0-142-generic. Admission passed on the first
boot and again after an actual kernel reboot. The boot changed from
`c460b221-ff19-43e8-9bc1-035b0b533afb` to
`2f4d0fc4-b294-4bd1-ac39-41187ff1c34c`; synthetic durable state, machine identity
and the root-owned unit definition were unchanged.

Each boot exercised six actual refusal cases: wrong unit digest, CPU limit,
memory limit, a boolean limit, foreign installation and a non-string digest.
Caller bus, host and pager overrides were ignored. Independent observation
matched the returned manager birth and all five groups to actual workers. The
eight reboot capability checks, four post-exit custody checks and four offline
installed-file checks passed. All three fresh fixture groups were empty after
exit, and private disks and diagnostics remained retained.

The first two attempts did not complete the fixture proof. The first exposed
the ordinary account's inability to read the privileged PID 1 executable link;
the next producer reused a variable and overwrote its synthetic worker-state
record. Separately named producers corrected the observer and harness. Neither
failed attempt was relabelled successful.

Read-only inspection of the powered-off guest disk verified the actual installed
module, manager, control agent and unit against the supplied bytes and root-owned
single-link mode 0644 metadata. The original overlay stayed byte-identical.
Private raw copies were retained; no mounted, physical or loop device was used.
The executed module SHA-256 is
`bdbe3a3f1ca81bb9fdf03b068ec2bb3ea27b33810149610cb9addfe12d8f03ba`.

The private 23-record admission archive passed digest readback. Its review
SHA-256 is `1a66377027aa297689385c98a2f9ab10c81c6a74441ec985b6ed36ae2d81209c`;
its index SHA-256 is
`abdadfa50029fee25d70471bbb04f2704d006d05efe5fe63d220da304aeffadb`.
The separate five-record installed-source archive binds that archive and all
four actual installed files. Its review SHA-256 is
`8566dd861651d87868966823b5c292df3d6240e8a4e68faf3202d21b05e35615`;
its index SHA-256 is
`03cf859891ae832ba318bf3d7b4290ec52c89a684c9719572d5f1e6eb91a4be1`.

## Privilege-hardened admission revision

The fresh fixture `faf43a03-45a2-4e4d-bd75-a8bc21fb4c4e` exercised the stricter
observer on both actual boots. Its kernel boot changed from
`df20dec1-6351-4644-ba42-e096e695b461` to
`619cebac-8cdd-4c56-8c87-a4a1202eb315`. Admission and the six earlier refusal
cases passed on each boot. The actual manager had GID 1000, supplementary group
1000 only, all five capability sets empty and `NoNewPrivs=1`.

Eight reboot checks, four independent custody checks and four read-only offline
installed-file checks passed. All four admission fixtures remain retained and
empty after exit. The actual installed current module SHA-256 is
`6ea29354bdcec0df0452518eb1280780c64f74d8daa2880333499dc0967ca13a`.
The earlier archives describe their original revision and remain unchanged.

A separate bounded Source kernel experiment passed three actual process-security
checks: empty capabilities without `NoNewPrivs` refused; retained bounding
capabilities with `NoNewPrivs` refused; empty capabilities with `NoNewPrivs`
passed. Only these child processes changed their own capability state. This
tests the security validator under WSL init, and does not claim service admission
in that environment.

The current private admission archive has 29 verified records, including the
original failed archive writer. Its review SHA-256 is
`29b1a8d9fb01071d9e40e2cce9b1d8ba14805f2acd7763a991fd1e53bd4a5285`;
its index SHA-256 is
`6049a5296262c1c70dc8a394c79a98d6da45407d494afc9c7ea06054b9e229ef`.
The five-record installed-source archive binds those records and the four actual
installed current files. Its review SHA-256 is
`3dd871eee9f25ac231f7b5f4f44376d874f51d0e0c2f29e51276cbfe9180eb50`;
its index SHA-256 is
`c51100090533f9d26219487900a6d168704be569e40ba6d9d39f5e9d5908dcd9`.

Durable identity records, atomic generation publication, application writer
leases, lifecycle dispatch, installation/upgrade/backup/retirement recovery,
legacy conversion, allocation and Barkpark Cloud remain unfinished. No complete
journey or release acceptance follows from this component.
