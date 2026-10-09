# Retained usability after original resource removal

Status: accepted execution design; actual installed implementation passed scoped
verification and awaits its current required CI/integration.

The installed pre-removal controller verifies the original snapshot and requires
the original database to remain present. It cannot establish final archive
usability after deletion. The final retirement stage needs separate observed
absence while retaining the same archive, target, artifact, actors and process
custody. A prior functional receipt alone cannot complete that stage.

Codex primary agent chooses a fixed `retention_verify` profile. It is admitted
only after the owned journal has acknowledged quiescence, actual pre-removal
restoration, exact database removal and exact store removal. Original database
absence is checked through its pinned cluster, role, endpoint and database
identity. Original store absence is checked through the sealed root and store
inventory. A replacement database or extra/replaced store remains preserved and
refuses; no force-disconnect, role deletion or replacement cleanup is permitted.

Before database removal, the owner durably retains the original configuration
bytes in the private installation history under a fixed filename. Their SHA256
must equal the already independently sealed configuration binding. This file
stays outside removable stores, uses no-follow/exclusive publication, private
single-link ownership and file/directory sync, and is never included in ordinary
evidence. It retains the exact local database authority needed to observe
absence after the original configuration store is gone. Same-byte publication
can be reconciled; changed, aliased or incomplete publication refuses. This
retained file and actor credentials remain part of the documented private
retention inventory rather than credential cleanup.

The final profile permits only actual existing-target observation. It cannot
reimport a database, create an empty materialization, invoke the original live
snapshot helper or weaken the pre-removal profile. It authenticates retained
archive/key/code again, observes restored data and the separately bound stopped
marker/materialization, starts only the fixed loopback verification application,
repeats independent actor/API/HTTPS/SSH checks, stops every target group and
reobserves target fingerprints plus original absence. Only that fixed combined
receipt can acknowledge `retention_verify`.

An interrupted final verification stops only its sealed target groups. It must
observe original absence and retained input identities before reconciling the
unacknowledged read-only stage and repeating the same full function checks.
It does not undo removal or infer usability from absence alone. Malformed or
unavailable retained targets and invalid/expired actor credentials remain visible
failures; this profile requires valid independently retained probe credentials.

Actual disposable installed verification completed all five journal stages.
After independently verified pre-removal function, the fixed controllers removed
only the sealed original database and three stores, then started the same retained
target. An exact-birth SIGKILL of the ready final owner preserved uncertainty and
live target services. A new fixed owner stopped those groups and refused/preserved
changed archive/key/private configuration, an actual replacement source database
and store, and an unexpected target file. After fixture-owned witnesses were
removed, fixed final retry repeated authenticated independent actors/API/HTTPS/SSH
function, stopped all target groups and observed unchanged target data plus source
absence before publishing complete responsibility. Exactly one database import
occurred across the entire lifecycle. Eleven lifecycle checks, seven adversarial
checks and two repeated read-only CLI observations passed; all115 retained history
files were unchanged by the CLI. The145-file evidence archive passed digest and
credential checks. The first resume fixture inherited read-only database creation
options; its refused witness setup and producer remain retained separately.
Current operator regressions pass129 Linux checks with ten foreign skips.

These are actual same-host/kernel observations against clean installed application
`ea3a2adbc2377138a66ea97fb90247509003fc9e` and independently hashed draft operator
bytes, rather than complete release or native lifecycle CLI acceptance. See
[the implementation evidence](../implementation/installation-retirement.md).
Shared roles, the retained verification installation, private
credentials/materials, installation history/artifacts, kernel groups and provider
resources are retained; no host deallocation, cancellation, managed Cloud or
complete release acceptance follows from this design.
