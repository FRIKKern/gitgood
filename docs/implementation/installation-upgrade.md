# Controlled native installation upgrades

Implementation work for J15. The existing populated migration experiment proves
specific data-preservation refusals; it does not activate an installed release.
This work keeps the single-runtime installation lease and independent recovery
custody as operating constraints. Managed Cloud execution remains a separate J14
integration dependency.

## Initial operating profile

Support the measured Ubuntu 24.04 x86-64 installation, PostgreSQL 18.4, one forge
runtime, its TanStack web server and an owned edge route. Use a maintenance window:
two forge versions cannot hold the same installation lease concurrently. Stage
immutable code separately from the mutable database, Git stores, assets, private
configuration and external recovery key. Never downgrade a schema automatically.

The first component is implemented as
`python3 tools/deployment/inspect_native_artifact.py ARCHIVE SHA256 CANDIDATE`.
It opens the archive without following a file symlink on supported Linux, verifies
the independently supplied digest, checks bounded member metadata and matching
build identities, and reads the native ELF platform header. It extracts nothing
and executes nothing. The emitted `inspected` receipt is separate from readiness
or activation. Its structural tests use synthetic inert fixtures; the retained
9392a31 real artifact also passed inspection. No full J15 result follows from this.

The supervisor receives only fixed lifecycle actions and exact owned resources.
A user-supplied descriptor cannot introduce arbitrary host commands. Runtime
processes are identified by PID and creation identity; the dedicated native cgroup
must include all descendants before maintenance. Preserve the previous artifact,
configuration and recovery bundle through activation and subsequent verification.

## Implementation sequence

1. Inspect an immutable native artifact against its independently supplied digest
   and candidate. Verify the forge/web build identities agree, required files and
   Linux x86-64 runtime exist, declared migrations and dependency/requirement
   identities are well formed, and archive paths cannot escape staging. Inspection
   executes no candidate code and changes no installation stores. Tampered,
   duplicate, truncated, foreign-platform and mismatched artifacts must refuse.
2. Introduce a private installation inventory and durable upgrade journal binding
   the installation UUID, old/new artifact identities, database, owned stores,
   supervisor/cgroups, routing and compatibility decision. Persist stages before
   consequential actions. Concurrent requests refuse; retry reconciles the same
   intent and never silently switches candidate or targets. Unknown state remains
   visible. No secrets or expanded environment enter ordinary receipts.
3. Stage and preflight the candidate before stopping the old runtime. Enter
   maintenance, stop its complete owned cgroup and obtain the existing offline
   migration lease. Record the actual schema before/after migration. Start the
   candidate under its own supervisor; require exact identity, all readiness checks
   and authenticated functional probes before changing the public route. Verify
   both the public web/API versions and native HTTPS/SSH operation after routing.
4. Exercise unhealthy artifacts, migration failure, killed stage owners and lost
   activation receipts against populated disposable installations. If schema
   compatibility and actual probes establish that previous code still works,
   restart that artifact with the retained stores; otherwise keep maintenance and
   expose the supported forward-repair or matching-artifact restore path. Retain
   failed candidates and their stage evidence. Do not report rollback from a
   successful process spawn or readiness endpoint alone.

## Evidence gate

J15-A requires an actual old-to-new installed release transition, controlled
migration, identity/readiness/function checks and route activation. J15-B requires
an unhealthy candidate that does not become the working public release, plus an
explicit schema/code compatibility result. J15-C requires failure-stage visibility,
supported retry or recovery, and fresh public/native probes of the final version.

Archive raw stage observations, exact artifact digests, process birth identities,
schema results and public probe receipts privately with digest readback. Record
the producer and evaluator honestly. Inspector tests, populated migration checks,
or the supporting same-host recovery profile alone cannot close J15 or establish
managed Cloud lifecycle or a product release.
