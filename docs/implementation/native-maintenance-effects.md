# Native migration and first-owner effects

Native maintenance now has two fixed entry points: `Gitgood.Release.native_migrate/0`
and `Gitgood.Release.native_bootstrap_owner/0`. They start a separate permanent
application with the original lifecycle ownership startup first, then the fixed
Repo and maintenance worker. They accept no worker list, program, callback,
input path or authority map. A running product or maintenance application is
refused rather than reused. [Normal native runtime startup](native-default-startup.md)
uses its own fixed callback and prerequisites; maintenance commands do not
establish installation readiness.

The fixed Repo child pins every connection to `pg_catalog, public`, independently
of role/database search-path defaults. Both actions require that exact effective
namespace before effects, and the migrator explicitly selects `public`. Checking
public migration versions cannot authorize writes into a different namespace.
The pinned [Postgrex connection API](https://github.com/elixir-ecto/postgrex/blob/v0.22.4/lib/postgrex.ex)
accepts connection parameters; the pinned [Ecto migrator](https://github.com/elixir-ecto/ecto_sql/blob/v3.14.0/lib/ecto/migrator.ex)
passes its explicit prefix through migration execution.

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
The inventory is flat and closed: only numbered `.exs` migrations and the optional
non-executed `.formatter.exs` file are permitted, with at most 1024 migrations.
Directories and unknown entries refuse before the migrator can recursively
discover code outside that checked inventory.

Migration reads the actual `public.schema_migrations` and requires the exact
sealed before versions. An initial empty history also requires an empty user
relation inventory; an existing application table with missing/empty migration
history refuses. Before versions must be the exact ordered prefix of the package,
not merely a subset; an older missing migration cannot run below an already
applied newer version. The fixed Ecto migrator runs forward only. Its applied versions
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
The fixture gives the actual role a conflicting default search path with an
empty shadow schema. Migrations and first-owner data must still appear in public,
and Root independently checks that the shadow namespace received no relations.

`maintenance-schema-refusal` starts with one unexpected table and an empty sealed
before history. The actual worker must refuse without creating the migration,
user or owner-receipt tables, terminate its original BEAM and leave captured
backends absent. Root verifies unchanged lifecycle head/snapshot and ownership
record/marker inodes. The fixture manager performs only its bounded descendant
cleanup and does not advance the failed lifecycle stage.

The final `maintenance-inventory-refusal` case adds a fixed nested migration file
to this owned disposable copy only after the earlier cases finish. That file would
create a table if executed. The actual worker must refuse the extra directory
before any migration, and Root requires both public and shadow schemas to contain
no relations. Original BEAM/backend absence and retained responsibility checks
still apply; the intentionally changed fixture copy establishes no artifact or
complete application acceptance.

Only a current passing installed receipt establishes these observations. The
fixture's inspection, staging and verification receipts remain synthetic metadata;
the successful business outcomes are independently observed, but are not yet
integrated into a complete lifecycle dispatcher or interruption reconciliation.
An uncertain migration or committed owner followed by a lost acknowledgement
requires actual state reconciliation, not blind command replay. Native runtime
startup, activation, enrollment, reboot and replacement-host recovery, and full
J14/J15 acceptance remain unverified. Original local VM/database/recovery material
must remain retained.
