# Initial enrollment journal dependency

`tools/deployment/enrollment_journal.py` implements a private Linux responsibility
record for first installation. It executes no installation commands and does not
allocate a host, create an owner, activate an artifact or establish J14 acceptance.
See [the design](../decisions/0016-native-initial-enrollment.md) for the remaining
coordinator, activation/history handoff and supervisor responsibilities.

The independently expected request digest is SHA256 of canonical compact UTF-8
JSON for `{protocol: 1, purpose: "native_initial_enrollment", operation, intent}`,
with sorted object keys. `operation` and `intent.installation` are canonical UUIDs.
The intent has exactly `installation`, `candidate`, `artifact_sha256`,
`allocation_sha256` and `inputs_sha256`. Keep the request, private inputs and
journal private. Ordinary status excludes the private-input checksum.

The fixed stages are `inspect`, `stage`, `migrate`, `bootstrap`, `verify`,
`activate`, `enroll`. Beginning a stage durably reserves responsibility. Success
requires a closed receipt checksum from the future fixed action. A checksum alone
does not establish that action's correctness; the coordinator must produce and
validate its actual artifact, database, owner or functional observations.

An interrupted running stage becomes uncertain. A new controller must reconcile
its effect before proceeding. An observed applied effect advances once; an
observed absent effect permits retry of that same stage. There is no previous-code
recovery action because first installation has no previous working release.
Failure reasons are bound to the current stage and retained in the event history.

An exclusive OS lock, its persistent file identity and a private directory bind
the controller. Ownership includes UID, PID creation identity, boot and mount/
cgroup namespaces. Event replay validates stage order, owner claims and epochs.
Replacing the named lock cannot create a second admitted controller. Journals
have at most 256 events and 524,288 bytes. Symlinks, shared permissions, hardlinks,
unknown fields and changed independently sealed requests refuse.

Publication synchronizes the temporary file, atomically replaces the record and
synchronizes its directory. A failed write/acknowledgement disables the current
controller. It must reopen durable state; it cannot continue from memory. An exact
completed request and read-only status leave record bytes unchanged. Reported
process liveness is separate from exclusive lock ownership and current readiness.
An archived or copied journal cannot silently adopt a different lock inode.

Fourteen component checks passed on Ubuntu 24.04 as the disposable `gitgood`
actor. They include a real competing process, actual SIGKILL after one inert
synthetic effect, explicit reconciliation, changed requests, malformed private
payload refusal, namespace-aware liveness, lock/record replacement, failed atomic
publication, symlink/hardlink/shared-directory refusal, lost durable-write acknowledgement and unchanged terminal/status
reads. This is journal/OS boundary proof, not migration, bootstrap or installed
application proof. PR64's required integration CI passed for 73530a2 with the
exact proposed tree executed at f35bc24; the journal merged at a216d03.
The complete enrollment controller remains a separate gate.

The full isolated operator snapshot passed 169 tests: 157 Linux checks and
12 expected foreign-platform skips. This includes both real database locale
boundary tests against the retained disposable PostgreSQL18.4 cluster. No
application code or published artifact was changed by the journal checks.
