# Native migration and first-owner effects

Native maintenance now has two fixed entry points: `Gitgood.Release.native_migrate/0`
and `Gitgood.Release.native_bootstrap_owner/0`. They start a separate permanent
application with the original lifecycle ownership startup first, then the fixed
Repo and maintenance worker. They accept no worker list, program, callback,
input path or authority map. A running product or maintenance application is
refused rather than reused. The default product application still refuses native
runtime startup; these commands do not establish installation readiness.

## Prerequisites and effects

The worker executes once, only on an explicit request after startup. It obtains
private inputs from the original attached monitor, matches the original action,
and brackets execution with current monitor, SQL lease and fence checks. A
60-second hard process deadline bounds execution. Any refusal, lost original
ownership, worker failure or repeated execution ends the permanent application
and its whole BEAM; it cannot restart children to conceal unfinished effects.

Before either action, clean compiled candidate identity, its declared migration
versions, the actual packaged migration inventory and sealed target must agree.
The migration directory and every ancestor must be Root-owned directories without
group/other write permission; migration files must be single-link, regular,
Root-controlled files. Symlinks are refused.

Migration reads the actual `public.schema_migrations` and requires the exact
sealed before versions. An initial empty history also requires an empty user
relation inventory; an existing application table with missing/empty migration
history refuses. The fixed Ecto migrator runs forward only. Its applied versions
and the independently reread schema must equal the expected difference and target.
No downgrade or compatibility claim follows from that equality.

Bootstrap requires the actual target schema and an absent first-owner receipt
with no existing users/memberships. It invokes the existing transactional owner
command with the original private request and digest, then observes its durable
receipt, authenticates the created actor and checks current owner membership.
The final schema must still match. Outcomes contain installation, operation,
candidate, action and version observations, never passwords or private digests.
OTP status redacts state, messages, reasons and debug log values.

## Evidence and remaining integration

Backend checks cover candidate/package/target mismatches, fixed actions, replay
refusal, status redaction and actual SQL schema mismatch without mutation. A
separate pinned OTP regression compiles the actual maintenance entry, observes its
fixed application specification inside the original startup factory, then requires
that factory's refusal to terminate the whole BEAM. Root validation and the
factory are explicit stand-ins in that loader check; it verifies neither service
admission nor SQL ownership. Hosted
verification adds a fresh `maintenance-effects-boundary` installation: actual
packaged migrations and first-owner creation run under the permanent maintenance
application. Root independently queries the private fixture database for schema,
receipt and current membership. It captures the lease and Repo SQL/kernel backend
identities before execution and after effects, injects original helper/backend
loss, and requires all captured identities absent before the next owner.

`maintenance-schema-refusal` starts with one unexpected table and an empty sealed
before history. The actual worker must refuse without creating the migration,
user or owner-receipt tables, terminate its original BEAM and leave captured
backends absent. Root verifies unchanged lifecycle head/snapshot and ownership
record/marker inodes. The fixture manager performs only its bounded descendant
cleanup and does not advance the failed lifecycle stage.

Only a current passing installed receipt establishes these observations. The
fixture's inspection, staging and verification receipts remain synthetic metadata;
the successful business outcomes are independently observed, but are not yet
integrated into a complete lifecycle dispatcher or interruption reconciliation.
An uncertain migration or committed owner followed by a lost acknowledgement
requires actual state reconciliation, not blind command replay. Native runtime
startup, activation, enrollment, reboot and replacement-host recovery, and full
J14/J15 acceptance remain unverified. Original local VM/database/recovery material
must remain retained.
