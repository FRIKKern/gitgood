# Ownership attachment to the original monitor

The fixed generation helper accepts one bounded canonical `attach_ownership`
frame after its initial admission. It attaches the retained marker and held-session
observer to its original generation guard and capture. It does not reopen or
recapture a generation, publish ownership, acquire a lease, repair custody or
admit replacement or lifecycle responsibilities.

The Elixir caller supplies the closed ownership record and independently checked
publication receipt. Its record checksum, marker checksum and operation determine
the exact expected ownership acknowledgement. The record must match the monitor's
original pointer, binding, service scope, owner and guard checksums. The protected
Python observer independently verifies the original live session, owner socket,
Root seals and marker custody before acknowledging.

Attachment has a separate three-second deadline. Existing generation heartbeats
cannot extend it. A partial frame cannot renew freshness or acknowledge ownership.
The ordinary stream retains its three-second freshness requirement and original
resource limits. After attachment, every current frame must carry exactly the
same closed ownership token; a generation-only frame, changed checksum or granted
authority stops the linked monitor. The acknowledgement is delivered only after
the entire received batch validates. Duplicate JSON keys, noncanonical frames,
extra fields, changed status, trailing malformed frames and repeated attachment
refuse. The helper uses bounded nonblocking stdin reads; EOF refuses and closes
the original guard. It never waits on an incomplete input frame.

The helper closes its owned selector, marker descriptors and generation guard on
exit. The caller retains responsibility for the whole-BEAM supervision tree. This
is a component API; native startup remains unavailable until the artifact, Root
controller and complete application admission are wired and verified.

Seven attachment tests use explicit observer stand-ins and preserve the original
guard/capture. They cover partial frames, repeat/trailing commands, duplicate and
noncanonical input, wrong action/authority, bounds, construction refusal and
observer loss. Existing stream tests retain timing and seal checks; an additional
test executes against an actual Linux stdin pipe and verifies terminal EOF.
Six Elixir boundary tests cover acknowledgement, immutable owned heartbeats,
partial frames, malformed batches, independent deadlines and canonical decoding.
The combined Linux operator suite passed 448 tests with 18 platform-specific
skips. Backend precommit and protected-service ownership-loss verification are
separate checks; a passing boundary test is not proof of the installed helper.

Isolated backend `mix precommit` passed all 236 tests, and all 33 planning checks
passed. Independent source correspondence matched 330 copied files, including
every backend source and production helper. The only later change was the added
Linux stdin EOF test; the full current operator suite and its complete source
manifest verify that version. No installed-helper or application acceptance
follows from these component results.

Actual protected entry attachment, loss of marker/backend/owner socket, whole-BEAM
termination, original descendants quiescence, prior-owner reconciliation and
controller admission remain required. The earlier VM proof runs against its own
frozen source candidate and cannot verify this later attachment implementation.

An original-entry VM against `af30180` subsequently reached five fresh generation
heartbeats for each worker role. Its initial publication caller received a
retained receipt, but the attachment call terminated with
`installation_generation_lost`; the fixture timed out awaiting its ownership
response. Attachment and owned heartbeats did not pass. Its original scope is
independently empty and QEMU is gone, with failed disk and diagnostics retained.
The cause is unresolved. A fresh fixture adds bounded, passive BEAM receive
tracing while preserving the protected entry, production source and all resource
and freshness limits. This is investigation, not a passing installed-helper
result. Complete native application startup remains unavailable.

The retained receive trace identifies the independent ownership deadline as the
terminal message: it fired 3,032 ms after the attachment request while the last
generation heartbeat was 2,598 ms old. No attachment acknowledgement arrived.
This establishes acknowledgement deadline expiry; it does not measure individual
Python calls. The prior initial path repeated six generation checks and three
held-session observations across construction and the immediate feed response.

Initial observation now performs one complete bracket: original generation and
held session before marker opening, marker custody, original generation again,
and unchanged marker custody before returning. The initial result is consumed
exactly once by that same attachment call, without another whole observation.
Any later fresh check or close invalidates an unconsumed initial result. Every
subsequent heartbeat still performs its full generation/session/marker bracket.
No deadline, resource limit, lease, replacement or readiness authority changes.
Nineteen focused tests pass, including generation loss after capture, failed
session before marker opening, marker change across the final generation check
and refusal of reused initial results. These use explicit observation stand-ins;
the repaired installed attachment still needs a fresh original-entry VM proof.
