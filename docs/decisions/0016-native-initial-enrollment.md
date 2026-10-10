# Initial native installation responsibility

Status: implementation design in progress; no execution proof yet.

The fixed upgrade commands start from an enrolled, working installation. Initial
installation has no previous artifact, runtime marker or activation record. Codex
primary agent chooses a separate fixed enrollment coordinator and journal. It
must not manufacture an old release or describe an installation as an upgrade.

The first bounded profile is Ubuntu 24.04, Linux x86_64 and PostgreSQL 18.4 on
one independently allocated host. A private, independently bound request fixes
the installation UUID, operation UUID, artifact/candidate, resource allocation
and private inputs. The coordinator accepts no command strings or callbacks.
The existing archive inspector and safe staging code remain the artifact owners;
the packaged first-owner entry remains the actor-creation owner.

Initial responsibilities are inspection, staging, migration, first-owner
bootstrap, functional verification, activation and handoff to installed
operation. Each consequential stage is reserved durably before execution. A
lost owner leaves an uncertain stage requiring observation of its actual effect;
a successful function return or a historical journal receipt cannot substitute
for that observation. Exact completed requests return recorded responsibility
without mutating access, relaunching services or claiming fresh readiness.

The private journal uses an exclusive OS lock, atomic publication, file and
directory synchronization, bounded closed records, process creation identity,
boot identity and namespace identity. Failed persistence poisons the current
controller. Reopening reads the durable state and cannot continue from its
stale in-memory copy. Read-only status does not claim the lock or establish who
currently owns it. Credentials and remote response bodies are excluded from
ordinary status/evidence.

Installation and upgrade histories need an explicit handoff. Initial activation
must identify the first installation operation and verified artifact. The first
upgrade must compare its previous artifact against that real initial baseline;
it cannot require a fictitious completed upgrade. Existing upgrade/retirement
records and their applicability must be preserved during this extension.

Host allocation, supervision and reboot are separate responsibilities. The OS
supervisor must recreate ephemeral cgroups and verify fresh boot/namespace
bindings. Persistent data and identities survive; old kernel-resource receipts
are historical. Rebinding an OS resource scope must be explicit and observed,
never silent adoption of a path with the same name. Process interruption proof
does not establish cold-reboot or storage power-loss durability.

The initial journal is the next implementation dependency. Its tests must cover
real competing controllers, exact owner loss, uncertain-stage reconciliation,
changed-request refusal, unchanged terminal/status reads and persistence failure.
Complete enrollment still requires actual packaged commands, first-owner replay,
TLS/API/HTTPS/SSH function, activation/handoff, interruption at consequential
boundaries and reboot/supervisor exercises. Root allocation, cancellation,
managed Barkpark Cloud deployment and complete J14 acceptance remain unfinished.
