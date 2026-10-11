# Retaining the original backend with native ownership

New application ownership uses protocol 3. Its closed record adds
`backend_kernel` to the original operation, candidate, durable binding, generation
pointer, service scope, owner, SQL session and guard checksums. The nested kernel
record remains protocol 2: server boot/PID/time namespaces and Postgres account,
original SQL snapshot and original process birth. Its SQL snapshot must exactly
match the claim and its boot must match the service scope. SQL epoch microseconds
and boot-relative kernel ticks remain distinct values.

`NativeOwnershipRecord.build/5` requires this kernel record. The claim obtains
it through the [protected observation bridge](native-backend-observation.md),
then checks both original helpers before construction and publication. An
observation or a constructed map is not Root authority. The protected publisher
independently checks its protocol-3 `ownership-admission-v3.json` and captures
current generation/service/owner/storage observations. It independently reads
the fixed Root-controlled per-boot server scope and compares that scope with
the supplied kernel record before any effect.

The publisher checks the exact retained live process birth before and after a
fresh original SQL/session/socket/held-lease observation. It never recaptures a
different birth. Generation, private configuration, protected executable custody,
ownership seal and server-scope seal observations bracket record retention and
marker publication. Loss after retention keeps the uncertain record and prevents
the marker; loss after publication preserves both effects and reports refusal.
There is no lease acquisition, cleanup or automatic replacement in this path.

The attached monitor uses the same retained-birth check. Its immutable token now
includes `original_backend_kernel_observed` and the canonical nested kernel-record
digest. Missing, changed or downgraded tokens stop the monitor. Scope-file identity
replacement permanently poisons its observer, even if identical bytes or the
original file return. Existing three-second freshness and attachment deadlines,
service limits and one-time attachment remain unchanged.

Ownership-directory and runtime/maintenance marker names retain their `v2`
suffix because they belong to the systemd-v2 resource profile. The marker's
protocol-2 pointer format is unchanged; its digest references the complete new
protocol-3 ownership record. This avoids introducing another pathname that could
bypass existing retained responsibility. The publication request and receipt are
protocol 3; the generation monitor's transport and resource records remain
protocol 2. Version checks are explicit at each boundary.

Existing protocol-2 ownership records are readable only as retained history.
Inspection preserves their canonical bytes, inode and identities. New retention,
publication, marker guards and live observation require protocol 3. Missing old
kernel identity is never synthesized from a current process. A prior legacy
record refuses an initial new claim and must receive independently proven
controller reconciliation; this change implements no conversion or removal.

Current component verification includes 41 ordinary Linux Elixir checks, four
cross-language constructor modes, 533 ordinary Linux operator tests (504 passed,
29 platform or privilege skips), and unchanged before/after digests for all 123
operator sources. The live database proof passes 13 checks with two actual BEAM
lease owners and an independently Root-observed Postgres listener. Retained live
births pass, changed births refuse without disturbing the original holder, closed
originals refuse readmission, and a new same-key holder stays untouched while the
earlier original's absence is checked. Both BEAM owners exit normally.

A separate actual Root-file fixture verifies ordinary-user reading of the
protected fixed scope, identical-byte inode replacement refusal, same-inode
mode/rewrite refusal and permanent refusal after restoring the original. File
metadata and all protected parent identities remain captured. Both file versions are retained. These
scope and database proofs do not admit a product allocator or a real delegated
native service. Filesystem custody tests retain protocol-3 records and preserve
legacy records, uncertain partials and changed same-operation requests.

Installed claim/attachment execution, startup abort of the complete application,
production allocator enrollment, controller reconciliation and functional native
journeys remain required. The native application gate remains closed. Required
CI and full backend integration are separate gates; earlier precommit results
for the SQL-only format do not verify this revision.
