# Lifecycle references in generation transitions

Required integration under [decision 0018](../decisions/0018-native-supervision-generations.md).
Generation publication must preserve original lifecycle responsibility across a
new controller generation. It cannot treat an interrupted enrollment or upgrade
as an empty history, or rewrite the old request to fit current resources.

`NativeLifecycleHistory` reads the complete bounded journal graph under borrowed
generation custody. It neither acquires another lock nor claims, repairs, writes
or deletes responsibility. Original PID/birth/UID/boot/namespace custody, held
directory descriptors, private file modes, links, canonical bytes and exact
metadata remain checked. Replaced directories or files, changed heads, incomplete
publication, unknown partials and forked borrowers refuse. Closing the view does
not release the caller's lock.

The journal and reader share the same graph validator. Every immutable snapshot
replays its fixed stage events and retains its original request, input seal,
durable binding and first owner. Every operation has one root, one complete tip
and an exact head. References include **all** current operation tips, including
terminal operations, sorted by operation. Each reference has only `operation`,
`request_sha256`, `origin_sha256` and `snapshot_sha256`. Those hashes name retained
metadata; they do not prove a stage effect or authenticate the input files.

`GenerationPublication` now accepts the explicit lifecycle directory only after
this complete validation. A new immutable transition records the captured
references while retaining the old pointer and original generation predecessor.
Each referenced snapshot's claimed generation must be the new generation or one
of its retained ancestors. Older transitions continue to reference their exact
historic snapshots after the journal advances. Missing snapshots, substituted
request/origin hashes, duplicate or unsorted references, and future generations
refuse, even if a pointer is rehashed.

Publication brackets lifecycle references, directory identities/change times and
every original file's full metadata. It rechecks them after generation retention,
before pointer publication, before completion and after completion. A same-byte
rewrite during this operation therefore cannot supply a new unobserved history.
An incomplete publication retry must retain the original reference set. Current
completed publication may be observed again after later legitimate journal
progress; it does not rewrite its historical transition.

Persistent continuity, actual stopped service groups, old-manager absence and
the existing OS/database exclusions remain publication requirements. This view
supplies none of those authorities. Neither generation publication nor a journal
hash reconciles an uncertain product effect. The protected controller must still
observe original sealed inputs and reconcile the actual stage against stores,
schema, artifacts and routing before acting.

The default worker reader still refuses lifecycle history. The explicit
[lifecycle worker reader](native-lifecycle-worker-admission.md) now checks fixed
recorded stage windows and original protected inputs. Generation-aware handoffs,
fixed controller dispatch and complete installation/upgrade/reboot journeys
remain required. This integration does not grant readiness or claim deployment.

Verification must cover complete read-only custody, historical references,
terminal and unfinished operations, wrong/future references, partial refusal,
changed files during publication, lost pointer acknowledgements and independent
process interruption. Service observations and database admission in boundary
fixtures are stand-ins; actual filesystem custody and process termination must be
identified separately. Retain failed fixtures and their original source before
repair, and assess the exact committed candidate independently of required CI.
