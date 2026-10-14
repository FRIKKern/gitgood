# Root observation of original lifecycle history

Protected artifact allocation must first identify the original installation
operation and its complete retained history. `NativeRootLifecycleObservation`
adds a fixed read-only Root view for that prerequisite. It does not acquire
exclusion, allocate artifact policy, dispatch a stage or establish recovery.

## Fixed original inputs

The constructor accepts only installation and operation UUIDs. Root UID/GID and
the original process/thread are mandatory. It obtains the original ordinary
controller through `NativeRootControllerObservation` and reads the fixed
generation, lifecycle-worker, ownership and operation seals beneath
`/etc/gitgood/installations/INSTALLATION`. Unit identity, limits, binding,
candidate, request hash and input-seal hash must agree across those policies.
There are no caller paths, programs, environments or authority maps.

The original private files are fixed beneath
`/var/lib/gitgood/operation-inputs/INSTALLATION/OPERATION`. Held read-only
descriptors, exact directory entries, ordinary owner/group, 0700 directories,
0600 single-link files, original metadata and independently sealed byte hashes
are checked. The opened directory must match the seal and its pathname. The
existing closed request and file formats are reused; ordinary readers continue
to require their original ordinary caller. Private payloads stay inside the view
and do not appear in its status result.

## Complete recorded history

A separate internal Root file-custody adapter reads the original fixed history
and lock file beneath `/var/lib/gitgood/installations/INSTALLATION/history`.
It holds original directory descriptors and checks file metadata without taking
the ordinary controller's lock, creating a store, retaining records or publishing
a generation. Its write, publication, borrowed-custody and worker-admission
entry points refuse.

The view reuses generation publication validation and complete lifecycle replay,
including retained operations away from the current tip. Unknown layouts,
partials, missing publication completion, changed files/directories, detached or
branched responsibility, a generation that differs from the original controller,
and another unfinished operation refuse. The selected operation must have the
original sealed request and input seal, be recorded as running, and refer to the
current complete generation. Its status and metadata remain the captured original
snapshot; later progress requires a separate explicitly admitted observation.

Any original-resource change permanently poisons the public view and closes its
owned descriptors. An interrupted history constructor also closes temporary
reader descriptors. All policies, inputs, locks and retained history remain.

## Evidence and remaining authority

Local closed-policy, refusal, metadata-race and interruption tests use explicit
controller/account/filesystem stand-ins. Root-only input tests use actual
ordinary-owned files and Root descriptors with an explicit scratch ancestor
policy stand-in. They check byte/mode/inode preservation and refusal after a
same-byte replacement; their hosted execution remains required. The workflow
also installs the production module and constructs this view in lifecycle cases
after the ordinary manager records its first maintenance reservation. It compares
repeated observations of the actual controller, fixed policies, original private
inputs and complete recorded histories before allowing the fixture to launch its
owner. This is read-only fixture scheduling, with every effect/exclusion grant
still false. Successful execution of those cases remains required; actual Root
observation is not yet verified by the source or local tests.

Recorded history is not evidence of actual stage effects. This component does
not re-observe the live durable resource/database identity, authenticate a stage
dispatch peer, establish lifecycle/database writer exclusion or allocate the
protected artifact seal. Those checks, actual inspection/staging, interrupted
effect reconciliation, runtime use of the staged code and full J14/J15 recovery
remain required. Its result explicitly keeps effect authority, exclusion, live
resource verification and complete journey acceptance false.
