# Native persistent installation observation

[Decision 0018](../decisions/0018-native-supervision-generations.md) requires
independent persistent-resource observation before a new kernel generation can
be admitted. The implementation in progress separates this observation from
record custody, writer exclusion, reconciliation and publication.

## Intended observation boundary

The ordinary controller first establishes its actual systemd service boundary.
It observes the installation beneath the fixed root-controlled
`/var/lib/gitgood/installations/<UUID>` parent. The six private directory
identities, configuration and SSH-key file identities/checksums, root-controlled
machine identity/OS profile and five root-controlled executable identities form
the persistent record. Two complete observations must match, bracketed by
unchanged actual service admission. The generation guard streams each of the
five executable hashes once within its capture, then reuses only that digest
while repeatedly verifying the original canonical path, file identity,
nanosecond ctime/mtime, size, owner, mode, links and protected parent identities.
Configuration, keys and live database identity are observed on both passes.
The standalone persistent observer still hashes executables on every call.
Changed or unavailable executable custody permanently refuses; it cannot
recapture or adopt a replacement. No bytes or digests survive into another
guard. Boot, controller birth and cgroup identities
remain exclusively in the resource generation.

The existing configuration format stays unchanged. No protocol-1 journal or
baseline is converted. Unknown configuration options, path aliases, hard links,
shared permissions and changed observations refuse. Private file descriptors use
nonblocking opens so a malformed FIFO cannot wait indefinitely for a writer.
Configuration/key contents and database credentials never enter the observation.

The fixed, bounded PostgreSQL query observes the actual cluster identifier,
database and owner-role OIDs, database/session role, exact supported version,
encoding and loopback endpoint. Login must be enabled; all five administrative
role flags must be false and role membership count must be zero. Caller process
environment cannot supply connection, service, loader or psql startup overrides.
Timeout/output failure reaps the directly owned query child.
The query explicitly sets `PGPASSFILE=/dev/null`: [libpq otherwise defaults to
the account's password file](https://www.postgresql.org/docs/18/libpq-connect.html#LIBPQ-CONNECT-PASSFILE),
which would introduce an unsealed authentication input when the URL has no password.

## Current verification

Ten database boundary tests passed, including actual pipe size/deadline checks.
A separate disposable PostgreSQL 18.4 experiment passed four checks: exact
ordinary-owner observation, six separate actual privilege/membership refusals,
denied cluster-identity observation and unchanged retained data. Each privilege
restoration reobserved the original identity. Its failed first harness attempt
never connected because ordinary proof-file access was denied; all attempts,
the database, roles and diagnostics remain retained. Source uses disposable
loopback trust; deployed authentication is unverified.

Ten binding boundary checks passed, including real private-file and directory
identities, retained replacement directories, aliases, hard links, a FIFO,
root-controlled executable hashing and private configuration boundaries.
The standalone Linux suite passed 245 checks with 12 expected foreign-platform skips;
all 33 planning checks passed.

The actual service-backed experiment passed 13 checks across two kernel boots.
It used the current four product modules, real PostgreSQL 18.4, generated fixture
keys and pinned root-controlled binaries. The persistent binding stayed identical
while boot and actual service-resource identities changed. An independent
ordinary-role query observed the same retained row and relation ownership on
both boots. Four independent custody checks bound all 41 seeded operator modules
to current source and independently observed six booted fixture groups empty.
Four additional offline checks verified eight actual installed files, including
the four product modules, as root-owned single-link files matching their original
supplied bytes. The powered-off original guest disk remained unchanged.

Earlier failed and successful fixtures, disks and diagnostics remain retained.
The final fixture uses atomic descendant-record publication after an earlier
fixture exposed a partially written PID record during reboot. Earlier harness
attempts do not establish current verification. No network interface, host share
or provider command was exposed to the disposable guest.

The private source archive contains 65 records, with review SHA256
`5b40ee914ed26b6da534187e68ea9f021096ca26d9c4b4c048511f80ec75f44c`
and index SHA256 `a38a3d667744838070cc5a0f2f571362a1a3b2dcfefc91d8214f134782c86127`.
The separate five-record installed-byte archive has review SHA256
`99252651911e6fbbaee9df1945ea84da7fd52716ad8422fd083482a1c5ca1e86`
and index SHA256 `1ceb7ad5d279b46ca9d2b2b7814a4ac81f5e3f71fdccd19e2894b5872d2e942d`.
Current required CI remains a separate integration gate.

After combining the reviewed record-custody dependency, the Linux suite passed
256 checks with 12 expected platform skips and all 33 planning checks passed.
Every one of the 41 originally seeded module bytes stayed unchanged; the added
custody module has its own separate interruption proof. Five combined-source
records retain this applicability decision and the original proof archives:
review SHA256 `fe07da88f0e584e4cf34e796b347d1cba795e55151b41062a3fbe91511980b1c`,
index SHA256 `8e4c6c1726a1e31924a664fa81b46f3e44568cbe746664eb68a741712bc9870d`.

## Remaining authority

This read-only record establishes no lock, database writer exclusion, active
artifact/schema/routing readiness, generation publication or process-kill
authority. Root allocation must independently seal expected unit/runtime/resource
inputs; caller-provided executable paths are not allocation authority. Executable
identity alone does not verify a complete packaged runtime and its libraries.
TLS/SSH file custody alone does not verify usable keys or functional access.

Before publication, establish immutable custody, the installation OS lock,
database writer exclusion, exact old-owner reconciliation and retained lifecycle
responsibility. Add sealed transitions, atomic pointers, lost-acknowledgement and
competing-controller recovery. Application leases, full lifecycle recovery,
allocation and Barkpark Cloud remain separate gates. No full journey or release
acceptance is established here.
