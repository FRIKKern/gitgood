# Native application ownership

Implementation work under decision 0018. Complete application startup, native
leases, generation-aware markers and lifecycle admission remain unfinished.

The preliminary `InstallationProfile` selector distinguishes the development
profile from `systemd-v2`. Native selection requires Linux x86_64, the canonical
installation storage path and a matching actual native or maintenance kernel
leaf. Missing profile selection refuses when native kernel context, a seal,
generation history or retained ownership files exist. Unsupported values and
roles refuse. Selection is not service admission, database exclusion or readiness.

The selector observes only bounded kernel text and named filesystem entries. It
creates no directories, starts no application or database connection, and changes
no marker. Six standalone selector tests pass, including actual preservation of
a malformed native marker and a retained ownership directory. Native selection's
policy tests use explicit synthetic kernel observations; they do not establish
an actual protected startup. Application startup, direct lease initialization
and offline maintenance now apply this gate before their first storage or
database action. Three further standalone tests compile the actual application
and lease with real schema/dependency modules and verify early refusal and
unchanged marker bytes. They do not run a complete application. Explicit native
selection currently refuses with `installation_native_ownership_unavailable`;
native ownership integration remains unfinished.

## Retained ownership records

`tools/deployment/native_ownership_records.py` adds closed immutable record
custody in storage's reserved `.gitgood-ownership-v2` directory. Records bind
the installation, distinct ownership operation, candidate, mode, durable digest,
publication pointer, service scope, owner, database-session snapshot and guard
digests. Unknown fields, invalid identities and a mismatched scope/owner token
refuse. Validation is structural; it does not observe a live service or session.

The caller supplies the independently admitted storage identity. Directory file
descriptors bind writes to that original storage and ownership directory, even
if a pathname is replaced. Records use exclusive private partial files, file
and directory synchronization, atomic link publication without replacement,
partial unlink and final directory synchronization. Identical completed retries
preserve the record inode and bytes. An interrupted publication retains partial
or hard-link responsibility and refuses further retention without reconciliation.
No unknown file is cleaned up. The directory's presence forbids implicit legacy
startup through the profile gate.

Twelve component tests cover closed records and actual ordinary Linux filesystem
custody, including interruption before and after publication, name competition,
directory replacement, permissions, symlinks and synchronization. Service and
database values in these tests are explicit synthetic fixtures. This component
publishes no live marker and grants no lease, lifecycle or readiness authority.
Actual native admission, its fixed writer entry, original-owner reconciliation,
live-marker publication and application integration still require implementation.

## Integration sequence

The preliminary `NativeOwnershipSupervisor` keeps admitted helpers and workers
in a root tree with zero permitted restarts and permanent child specifications.
Loss must end the captured owner instead of starting a new monitor or database
session. The packaged application must start as permanent for root-tree failure
to terminate the whole BEAM. It remains unwired: the profile gate still refuses
native startup before application workers.

Four standalone process tests use actual Elixir/OTP applications and OS processes,
with explicit fixture workers standing in for the monitor and held session.
They check whole-BEAM exit and exactly one start after helper loss, including a
normally stopped session, plus startup refusal before a mutation worker starts.
They do not establish protected service admission, actual PostgreSQL ownership,
live-marker publication, packaged application behavior or full native acceptance.

A further two standalone process cases substitute an actual non-retrying
Postgrex child for the held-session fixture. That child acquires the existing
installation advisory key and validates its actual limited-role database and
backend birth through `InstallationDatabaseSession`. Both a normal child stop
and direct child kill terminate the entire permanent application's BEAM. Each
child starts exactly once, the original backend is independently absent after
exit, and retained fixture data is unchanged. Baseline data is read through the
existing fixture observer; no role grants are added. Monitor and mutation workers
remain stand-ins. Spontaneous backend outage, protected native startup and the
complete packaged application are still required.

`NativeDatabaseLease` adds a dedicated keeper for one non-retrying Postgrex
session. Connection host, port, database and role must match the independently
supplied database identity. It acquires the existing advisory key once, captures
the original session through `InstallationDatabaseSession`, and checks that same
snapshot on each request and periodic observation. Connection-process loss or a
failed session check stops the keeper; it never reconnects or reacquires.

Four actual PostgreSQL process experiments place this keeper under the permanent
root supervisor: normal keeper stop, keeper kill, held backend self-termination,
and normal connection stop. Each terminates the whole BEAM, starts each child
once, leaves the exact original backend absent and preserves retained data.
Passing case logs are retained. Three actual startup cases refuse a competing
owner, wrong cluster and malformed administrative identity before starting the
mutation worker, with no remaining lease backend. Complete database validation
precedes connection creation. The preliminary direct
Postgrex experiment timed out after requesting backend termination; it did not
independently prove backend absence before caller cleanup and establishes no
native acceptance. The keeper remains unwired. Monitor admission, immutable
ownership, live markers, protected service and packaged startup are still required.

The isolated repository `mix precommit` run compiles the complete backend and
passes all 213 tests, using a separate test database and copied dependency
sources. All 306 current backend/operator source files equal the tested copy.
The formatter removed a terminal blank line from the supervisor; independently
checked terminal-newline equality preserves applicability of the seven database
experiments. Planning checks pass all 33 tests. These checks do not establish
native application or journey acceptance.

1. Select the profile before storage creation, pooled database startup,
   reconcilers, listeners or mutation workers. Apply the same gate to offline
   maintenance and direct lease initialization.
2. For native startup, capture the fixed generation monitor, then acquire one
   non-retrying Postgrex session and the existing installation advisory key.
   Validate that same session's database identity and backend birth. Require
   the original generation observation to remain current throughout admission.
3. Publish bounded, private, generation-aware ownership through a fixed trusted
   operation. Bind installation, candidate, mode, current publication, durable
   identity, owner birth and service scope. Synchronize the file and directory;
   retain uncertainty and original ownership instead of erasing unknown records.
   Keep ownership partials and retained records in the reserved
   `.gitgood-ownership-v2` storage directory so their presence forbids downgrade.
4. Start application children only after native ownership passes. Generation or
   held-session loss must stop the whole BEAM without reconnection or recapture.
   Retain its marker and verify backend and descendant absence before replacement.
5. Define closed lifecycle responsibility and reconciliation before allowing its
   history. Current publication-only admission grants no lifecycle authority.
6. Exercise the pinned artifact's actual native startup, functional Git access,
   competing owners, helper/session loss, uncertain marker publication and
   retained recovery. Bind evidence and required CI to the exact candidate.

Keep the original protocol-1 journals and same-boot refusal rules intact. Initial,
upgrade, backup and retirement interruptions, terminal-only conversion, allocator,
deployed authentication, the Cloud contract and complete journey gates still apply.
