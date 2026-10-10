# Native runtime and maintenance worker admission

`tools/deployment/native_worker_scope.py` observes an actual native or maintenance
owner and its observation helper inside the independently sealed installation
service. It retains the service admission requirements: supported host and system
bus, Root-controlled unit definition, ordinary installation account, empty
capability sets, NoNewPrivileges, delegated hierarchy identities and limits.

The manager must remain the actual systemd MainPID in the driver leaf. The helper
and selected owner must occupy the native or maintenance leaf. A bounded ancestry
observation checks each intervening process birth, namespace, credentials and
group membership, then rechecks the parent edges. The complete service and owner
observations must remain identical. An unrelated live process, PID reuse,
reparenting, replaced group or manager, unavailable process and unsupported role
leave admission unavailable. No process command line, environment or payload is
read, and no signals are sent.

This read-only component will support generation-aware Elixir lease admission.
It does not validate a published generation, create a marker, acquire a database
lease, authorize lifecycle dispatch or establish application readiness. The
original controller admission still requires its caller in the driver leaf, and
stopped generation publication still requires the actual manager itself.

Eight boundary checks exercise the fixed roles, ancestor relationship, namespace
and birth changes, reparenting, replaced manager/owner and unavailable observation.
They isolate service admission and process observation with explicit stand-ins.
The actual VM experiment passes 20 checks across manager interruption, recovery
and two kernel boots. Fixed Root-installed observation helpers admit both native
and maintenance owners on each boot. Each role refuses an unsupported role,
wrong unit digest, borrowed manager identity and opposite leaf. Independent Root
observation matches the still-live owner births and service identities; the
helpers are short-lived and are not inspected after exit. Four independent
custody checks bind 45 current operator modules and confirm all ten retained
fixture groups are empty. Four powered-off disk checks verify the exact bytes,
Root ownership and single-link permissions of all twelve installed files without
modifying the original overlay. The full Linux suite passes 287 tests with twelve
expected platform skips; all 33 planning checks pass. Required CI remains a
separate integration gate.

See the [supervision decision](../decisions/0018-native-supervision-generations.md)
for the remaining application, lifecycle, allocation and Cloud requirements.
