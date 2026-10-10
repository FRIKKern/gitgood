# First installation owner receipt

Implementation dependency for J14. This creates the initial owner on a separately
provisioned, migrated database; it does not perform complete installation,
allocation, routing, enrollment or managed Cloud deployment.

`Gitgood.Release.bootstrap_owner()` accepts the following private environment:

| Variable | Required value |
|---|---|
| `GITGOOD_BOOTSTRAP_INSTALLATION` | Independently expected canonical installation UUID |
| `GITGOOD_BOOTSTRAP_REQUEST` | Stable canonical UUID for this creation request |
| `GITGOOD_BOOTSTRAP_USERNAME` | Lowercase username, 2–40 characters |
| `GITGOOD_BOOTSTRAP_TEAM` | Lowercase team, 2–40 characters |
| `GITGOOD_BOOTSTRAP_PASSWORD` | Private UTF-8 password, 12–256 bytes |
| `GITGOOD_BOOTSTRAP_REQUEST_SHA256` | Independently supplied lowercase request digest |

Usernames and teams follow `[a-z][a-z0-9-]{1,39}`. The digest is SHA256 of compact
UTF-8 JSON encoding of the ordered array:
`["gitgood-installation-owner-v1", installation, request, username, team, password]`.
Use the same JSON string encoding as Jason's default encoder. No password or
request payload belongs in arguments, ordinary logs or evidence. Retain the
private inputs and independently pinned digest for interrupted execution.

The function validates inputs before starting the application, then serializes
bootstrap requests with a transaction-scoped PostgreSQL advisory lock. Initial
creation additionally locks user/membership writes and refuses existing actors.
The user, fixed owner membership and singleton creation receipt commit together.
The receipt stores a keyed commitment under the endpoint installation secret;
plaintext passwords and fast unkeyed password digests are not stored in it.

An exact repeat returns `recorded` metadata with the original actor and request.
Changed input, another installation or a new request refuses after creation.
Replays do not reset credentials or restore changed memberships. Returned
`role_at_creation` describes the original transaction. Current login, membership,
artifact identity, readiness and Git function require separate observations.
Preserve the original installation secret for commitment validation; a changed
secret causes refusal and cannot authorize a password reset.

On Linux production installations, this entry starts the application and requires
the same dedicated runtime group and complete-group shutdown as the existing
local-actor bootstrap. Supply secrets through private environment custody, run
`bin/gitgood eval 'Gitgood.Release.bootstrap_owner()'`, then remove bootstrap
variables. A fixed refusal message never echoes private inputs. The existing
`bootstrap()` remains the documented local/fixture actor-creation command.

Nine real-Postgres component checks passed: creation, lost-response replay,
independently resealed conflicts, invalid inputs, existing-actor refusal, actual
membership-write failure/rollback, changed-access preservation and two independent
connection concurrency cases. The full isolated `mix precommit` run passed all
189 backend tests and the formatting check. Six actual calls to the release entry
function in a separate test-runtime database passed digest refusal, fixed-owner
creation, unchanged-row replay and changed password/request/installation refusal.
These calls used Mix, not a packaged production release.

The production verifier now exercises the packaged entry before its authenticated
browser and HTTPS/SSH workflow. It compares the exact three owner-table hashes
and row counts across replay and changed-input refusals. The offline verifier
replays the same private request against the restored database, compares those
tables again, then requires matching readiness, authorized and anonymous-refused
API access, CA HTTPS Git and pinned SSH Git. These new packaged and restore checks
are pending actual execution. Complete first installation, artifact compatibility
and required CI remain separate gates; no J14 criterion is established here.
