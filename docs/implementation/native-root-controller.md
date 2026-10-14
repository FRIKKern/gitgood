# Root observation before protected artifact staging

Native artifact staging needs a narrow privileged boundary because the installed
runtime requires Root-controlled code. Existing `stage_native_artifact` produces
ordinary-user-owned code and cannot satisfy that requirement. Root must observe
the original allocated controller before any future operation-bound staging
effect. `NativeRootControllerObservation` supplies this read-only prerequisite;
it does not implement staging or complete J14/J15.

## Fixed policy and original observation

The constructor accepts only an installation UUID and requires actual Root
UID/EUID/GID/EGID on supported Linux x86-64. It independently reads the existing
fixed `/etc/gitgood/installations/UUID/controller-endpoint-v2.json` policy. The
closed canonical format binds the ordinary account, protected unit digest,
resource limits, and original private run directory. It accepts no caller path,
program, PID, authority map, callback or environment.

Root observes the actual systemd MainPID. Shared service checks still require
the fixed supported Ubuntu/systemd host, initial UID mapping, protected manager,
system bus, installed unit and executable, exact loaded properties, delegated
cgroup inode identities, resource limits and ordinary MainPID security/birth.
Root must share the observed controller's mount and cgroup namespaces. Root is
never treated as an ordinary process inside a worker group. Ordinary service and
worker entrypoints retain their existing UID/GID, namespace and membership
checks, including refusal of Root.

The view captures its original scope once. Every later check reobserves the same
manager birth, unit, boot, group identities, directory and Root policy, and
returns a detached projection. Changed identity or custody, Root credential
loss, fork/thread reuse or observer failure permanently closes it. Restored
files, modes or bytes cannot revive the instance. It never signals a process,
changes a service, acquires a database lease, modifies a file or adopts another
controller into this instance.

A new view observes the current allocated service; it cannot by itself prove
that a new MainPID is the owner of a prior interrupted operation. The future
Root artifact seal must independently bind the original observed scope to the
installation, operation, request, candidate and protected archive. Endpoint peer
authentication, generation/lifecycle custody, writer exclusion, original inputs
and current stage admission remain separate mandatory conditions.

## Verification and remaining work

Focused tests use explicit host/file/service stand-ins to exercise policy format,
credential separation, detached observations, permanent refusal on replacement
or restoration, and process/thread reuse. Actual Linux file and service custody
are established only by their relevant Linux checks. The hosted ownership proof
also invokes the installed production Root observer and compares its complete
scope with the original independently captured ordinary controller scope before
the real same-controller handoff cases. No artifact effect is claimed by that
comparison.

When an installed fixture fails, its receipt can identify a check through only
the fixed fixture filename, function and source line. No traceback messages,
private paths, source text, arguments or frame values enter that location.
This helps diagnose intermittent failures without treating a prior passing
candidate as evidence that a fresh failed run succeeded.

The next implementation still must inspect authenticated archive bytes, budget
all extraction and temporary allocations, publish fixed Root-controlled code
atomically without replacement, retain uncertain partial effects, and perform
observed interrupted-stage reconciliation. Actual lifecycle dispatch must consume
those results and run the inspected staged release. Activation/enrollment,
upgrade forward repair, reboot/replacement-host recovery and complete browser
journeys remain required for full installation and upgrade acceptance.
