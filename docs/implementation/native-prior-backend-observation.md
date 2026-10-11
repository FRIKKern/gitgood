# Original backend absence for native reconciliation

Decision [0018](../decisions/0018-native-supervision-generations.md) requires a
controller to establish that previous owners, backends and descendants are gone
before replacement. `observe_prior_backend_absence` supplies only the database
activity-view part of that observation. It does not reconcile a lifecycle or
authorize restart. `original_backend_absent` describes absence of the original
PID/birth identity from PostgreSQL's activity view. The result explicitly sets
`kernel_backend_absence_observed` to false: it has not independently admitted a
server PID namespace or inspected that kernel process's original identity.

The caller supplies the original immutable session snapshot and independently
admitted database configuration and executable. The observer checks the exact
cluster/database/role identity, then queries the retained backend PID. A live row
with the original microsecond birth refuses, regardless of whether it still holds
the lease. No row establishes original-backend absence. A visible different birth
at the same PID establishes absence of the original identity and reports PID reuse;
it returns no replacement PID or birth. A hidden/null birth, changed database,
malformed or unknown data, duplicate JSON fields or type-aliased snapshot refuses.

All queries use the fixed catalog-only, read-only environment and the existing
three-second statement/four-second child bounds. The shared reader bounds output
and reaps only its own query child. No database backend is signalled. The observer
acquires no advisory lock, adopts no session, writes no marker and provides no
owner-process, descendant, writer-exclusion or readiness authority.

Ten focused tests cover absence, live original refusal, known PID reuse without
adoption, hidden birth, changed identities, malformed wire data and actual bounded
query-child execution. Three existing held-session boundary tests still pass.
Five real PostgreSQL checks pass with two actual ordinary-role BEAM lease owners:
each live original refuses; each normally closed original becomes absent; a new
holder of the same key remains untouched while the old snapshot is observed absent.
The fixture retains hostile role search-path defaults, which these catalog-only
queries override. Real kernel PID reuse is not established by the structural test.

The [kernel identity companion](native-kernel-backend.md) captures a live original
session's kernel birth under an independently admitted server PID namespace and
combines same-boot kernel/activity-view absence. Its component tests do not
substitute for installed capture, retained identity custody or full recovery.

Complete reconciliation still requires independently admitted kernel/backend,
original owner and descendant absence,
current writer exclusion, independently observed persistent continuity, immutable
lifecycle responsibility and current generation/transition admission. The caller
must combine fresh observations under the original guards and preserve uncertain
effects. The native application gate remains closed; required CI and complete
installed controller/lifecycle/Cloud acceptance remain pending.
