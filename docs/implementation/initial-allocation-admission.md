# Fresh native allocation admission

`capture_initial_allocation()` in `tools/deployment/native_allocation.py` observes
an already allocated empty host scope. It allocates nothing and executes no
candidate code. The fixed first profile requires Ubuntu24.04 on Linux x86_64
and an owned loopback PostgreSQL18.4 UTF-8 database. Unsupported OS/architecture
refuses before executable hashing or database observation.

The private installation root contains exactly `configuration`, `storage`,
`ssh-host`, `history` and `staging`. Storage/history/staging must be empty private
directories. Configuration and SSH key custody, executable hashes, exact
database/cluster/owner identity and delegated cgroup identities use the existing
native resource observer. Closed forge/web environment keys and the configured
installation UUID are checked. No reusable configuration values are returned;
keep their checksums and allocation records private as well.

A fixed read-only SQL statement checks for non-system relations, functions,
types, schemas and extensions other than the standard `plpgsql` extension.
The `public` schema needs both USAGE and CREATE. Both privilege checks are
independent; having only one does not admit a host. Existing data refuses and is
retained. The four native/web/edge/maintenance groups must be unpopulated;
their identity is re-observed. The controller already belongs to its exact
delegated driver group.

The returned allocation binds the resources, empty-directory identities,
database emptiness result and current boot, mount and cgroup namespaces.
`allocation_sha256` is SHA256 of canonical compact sorted-key UTF-8 JSON for
the `allocation` object. Repeat reads of unchanged resources preserve the digest.
Resources are re-observed after the emptiness checks. This read is not a lock or
reservation against subsequent writes by the same trusted actor. The future
coordinator must claim responsibility and re-observe before consequential work.
Resource capacity policy, host/user/database creation and supervision belong to
the allocator/supervisor and are not established by this observer.

`capture_native_resources()` separates shared resource observation from runtime
admission. `capture_native_inventory()` retains its existing runtime-marker
requirement and output shape. Initial admission fabricates no marker or previous
release and cannot qualify a fresh host as an enrolled installation.

The full isolated operator snapshot passed 176 checks: 164 Linux checks and
12 expected platform skips. New checks cover read-only closed SQL, private
credential confinement, unsupported profiles, unchanged filesystem observation,
existing stores/history/staging, live-group refusal, wrong installation and
changed resources. A real disposable PostgreSQL18.4 database exercised empty
admission and preserved existing relation/function/type/schema objects. Extension
count refusal has component coverage; this pinned server contains no optional
extension package for a real extension fixture.

A separate actual delegated-host exercise passed eight checks using the real
private configuration, SSH keys, disposable database and kernel groups. It
observed unchanged allocation replay, preserved existing bytes/rows, refused an
actual live maintenance process without killing it, refused an enrolled-runtime
read with no marker, and retained the exact digest after configuration restoration.
All five owned groups were empty after the controller exited. Failed fixture
setup attempts and the optional-extension test failure were retained separately.

These are admission checks. Packaged installation, first-owner creation,
functional workflow, activation/history handoff, Root allocation, cancellation,
reboot/supervision and managed Cloud remain unfinished. No journey criteria are
verified by this dependency. Required integration CI remains a separate gate.
