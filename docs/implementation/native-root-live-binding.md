# Root observation of original live resources

Protected artifact authority must refer to the original live installation, not
only its recorded history. `NativeRootLiveBindingObservation` compares actual
directories, private files, runtime binaries and PostgreSQL identity with the
independently sealed original binding. It does not acquire exclusion or grant a
stage effect.

## Fixed admission and shared validation

The public constructor accepts only installation and operation UUIDs. It requires
Root UID/GID and the original process/thread, then obtains the fixed original
controller, request and complete generation/lifecycle history through
`NativeRootLifecycleObservation`. Runtime paths and the expected binding come
from that view's independently protected policies and current generation. There
are no caller paths, programs, environments, callbacks or authority maps.

The ordinary `persistent_identity` entry still requires its original ordinary
UID/GID before reading resources. A separate internal Root entry requires Root
UID/GID and the original controller's mount/cgroup namespaces. Both reuse the
same private resource/hash/database validation. Neither entry creates a binding,
publishes a generation or supplies service admission.

Validation checks the fixed installation directory layout and original ordinary
ownership, private configuration and SSH keys, Root-controlled runtime binaries,
host identity and actual PostgreSQL cluster/database/role identity. The pinned
client uses the existing bounded read-only database query. Credentials stay in
its private environment, outside argv and status output. Initial streamed binary
hashes are cached only under original protected path/metadata, then frozen.

## Original observations and refusal

The view captures the original persistent-file fingerprint before reading the
live binding. Every observation is bracketed by the original controller, policies,
request/history and persistent metadata. Actual binding values must equal the
original sealed current binding, including canonical types. Root namespaces and
cached binary metadata remain checked; changed original files, resources, live
database identity, history or process/thread permanently poison the view.

Status includes only operation/candidate references and fixed observation flags.
It does not return configuration, keys, database details, executable maps or
private payloads. Closing or refusing leaves every original file, directory,
database, policy and history intact.

## Evidence boundaries

Local admission, namespace, observation-order and poison tests use explicit
account/file/database stand-ins. The hosted workflow installs this module and
constructs it against the actual controller and live binding before the first
maintenance owner in lifecycle cases. Those observations remain unverified until
the exact candidate's installed evidence passes; local tests do not establish
actual PostgreSQL or resource custody.

Successful live identity observation still grants no lifecycle/database writer
exclusion, authenticated peer dispatch or artifact allocation. Those boundaries,
actual ordinary inspection/staging, interrupted-effect reconciliation and normal
runtime from staged output remain mandatory before complete J14/J15 recovery or
original VM retirement can be claimed.
