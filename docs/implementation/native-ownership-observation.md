# Original ownership observation

`NativeOwnershipObservation` combines an already captured generation guard with
the original database session and retained ownership-marker descriptors. It does
not capture a replacement generation, acquire a lease, publish a marker, reconnect
an owner, or admit a lifecycle responsibility. It remains an unwired component.

Construction validates the closed ownership record against the captured worker,
service scope, owner, pointer, binding checksum and three generation checksums.
The database identity must match both the captured binding and Root generation
seal. A canonical Root-owned ownership seal must bind the same installation,
operation, candidate and binding; its original bytes and identity bracket every
generation observation.

Each check observes the original generation, verifies the held database session
and its actual owner's kernel socket, checks retained marker custody, observes the
original generation again, and checks marker custody again. Private configuration
must remain identical before and after the read-only database query. Failure closes
the marker guard's own descriptors and permanently poisons this observer. The
caller owns the generation guard and must close it when the enclosing helper
fails. No uncertain files are repaired or removed.

Seven tests use explicit stand-ins to verify ordering and refusal boundaries:
changed original worker/owner, changed seal operation/candidate, replaced Root
seal, lost backend or borrowed owner socket, changed private configuration, and
lost marker custody without repair or recapture. They establish these boundaries,
not a protected helper or complete running application. Actual protected entry
attachment, whole-BEAM loss, prior-owner reconciliation and controller wiring are
still required. The native installation profile remains unavailable.

## Live systemd reads

The generation reader now obtains all required unit fields in two live typed
`GetAll` replies, one each for Unit and Service, instead of fifteen separate
property calls. Both observations still read every required field; manager
version remains a separate live read. Replies and manager state are never cached.
Original Root library custody brackets each call. Required variants must have
their exact signature, names must be unique, replies must be fully consumed, and
all required fields must exist. Strings, arrays and dictionary entries have fixed
bounds. Unknown properties are skipped without becoming authority. Any refusal
permanently closes the original connection without reconnecting.

An actual private D-Bus daemon exercised the real libsystemd dictionary/array ABI,
unknown-property skipping, missing-property refusal, wrong variants and permanent
connection loss. This fixture substitutes its endpoint and destination and runs
no systemd manager or protected service. Boundary tests also cover duplicate keys,
entry bounds, invalid booleans, trailing body data and library replacement after a
complete reply. Actual native service timing remains unproved for these bytes.

The prior ownership-publication VM failed the unchanged three-second freshness
limit for both worker roles before publication. Its original process scope is
empty and original Qemu process is gone; original disk, seed, runtime, diagnostics
and checksummed failure evidence are retained. Batching targets the measured
observation overhead without increasing deadlines or resource limits. A fresh
native VM proof must establish the result; the failure is not acceptance evidence.

The combined ordinary-user Linux operator suite passed 440 tests with 18
platform-specific skips, and all 33 planning checks passed. The private suite
receipt records the exact six changed observer/decoder/test source checksums.
These checks establish component behavior and reporting consistency; they do not
establish protected installation, lifecycle or complete journey acceptance.
