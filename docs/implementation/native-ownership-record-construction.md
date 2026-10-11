# Native ownership record construction

Implementation under [decision 0018](../decisions/0018-native-supervision-generations.md).
`Gitgood.NativeOwnershipRecord.build/4` constructs the existing closed ownership
record from a generation monitor's context, an original database-session snapshot,
a controller seal and one fixed runtime or maintenance mode. It performs no
filesystem write, database query, lease acquisition or publication.

The constructor binds the record to the actual calling BEAM PID. Installation,
operation and candidate identifiers must be canonical; the ownership operation
must differ from both installation and generation-publication operations. The
seal's durable digest must match the admitted context. The owner must retain the
scope's UID and namespaces and differ from its service manager. A runtime claim
requires the native worker; backup, restore and migration require maintenance.

The database snapshot has a closed shape and must preserve the admitted ordinary
database identity and bounded original backend PID/birth. Guard fields are closed,
and their scope digest must describe the exact scope, owner and selected worker.
The existing publisher's canonical encoding and request bounds apply to the
constructed record. Extra context, seal, session or guard fields and oversized
results refuse. Complete nested service-record validation remains with the
protected Python publisher.

These are construction and correspondence checks. A caller-supplied seal map does
not establish Root custody, and a snapshot does not prove a live backend. The
[protected publication entry](native-ownership-publication.md) must independently
verify its actual Root seal, original generation, owner/socket/session and storage
before retention. The constructor grants no replacement, readiness or lifecycle
authority. It does not relax the initial-only publication policy.

Eight focused Elixir tests pass against synthetic service/database observations.
They cover runtime and all three maintenance modes, borrowed or changed owner
identities, seal mismatch, malformed session identities, guard mismatch, added
authority and size refusal. A separate experiment invokes the actual constructor
for all four modes and validates their canonical output through the existing
Python closed-record validator; all four pass. The standalone runner uses Root's
retained dependency copy, without changing its permissions. These experiments
establish record compatibility, not live service or database admission.

The reference JSON fixture comes from the existing Python ownership-record fixture
with fixed operation identifiers. All its service, process and database values are
synthetic. Complete backend `mix precommit` now passes all 244 tests in an isolated
source copy and fresh test database as the ordinary Linux test account. The project
formatter removed one trailing blank line from the new module and its test; the
committed files adopt those exact tested bytes. All 334 backend/operator source
files must match that tested copy before retaining the result. Application startup
integration, installed execution of this constructor and full journey acceptance
remain required. Native startup is still refused before mutation.
