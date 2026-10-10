# Native initial installation responsibility and baseline

Accepted for implementation, 10 October 2026. Complete journey acceptance remains
dependent on current deployment and interruption evidence.

The first native install owns an empty, explicitly admitted scope. An upgrade
owns an existing release. Keep these histories distinct: a fake initial upgrade
would invent a previous release, hide incomplete setup and make retirement depend
on a migration that never happened.

Use the fixed initial stages and independently sealed inputs from decisions
0015 and0016. Hold the existing installation-wide OS lock while acting. Publish
an initial anchor before the first journal claim, so loss of that first journal
acknowledgement still excludes upgrade and retirement. The journal retains
uncertain effects after controller loss; a new process must observe actual state
before deciding whether to repeat an effect.

The controller checks current resource bindings and supported runtimes before
staging. It uses fixed packaged migration and owner commands, owned whole-group
shutdown, actual internal build readiness and CA-verified public owner access.
Its access check issues and revokes one temporary session. It creates no hidden
repository: complete J01/J02 Git workflows remain separate acceptance evidence.

Activation records the actual first release. After terminal initial completion,
seal its journal, anchor and activation into an initial baseline. Validate all
seven retained stage observations and their schema, pointer and access-probe
bindings; journal completion or metadata-only checksums alone cannot admit the
handoff. A lost handoff
acknowledgement can finish on exact terminal reopen without claiming another
stage or rewriting history. Until the baseline is valid, upgrades refuse. The
first real upgrade must name that baseline as its parent; retirement can use it
before any upgrade. Status reports zero upgrades and separately exposes initial
progress and an unsealed terminal handoff.

Actual preallocated Ubuntu 24.04 fixtures exercised the happy path, retained
partial staging after SIGKILL, and committed owner creation with a lost controller
acknowledgement. The initial baseline also admitted a real first upgrade between
distinct clean artifacts while preserving initial history, followed by fresh
public function and unchanged terminal CLI replay. Fixed `enroll` and
`enroll-resume` commands expose this coordinator; their exact current source
binding and integration CI remain separate gates.

This does not establish an allocator, reboot supervision, Cloud deployment or
complete J14 acceptance. Other interrupted stages and actual direct initial
retirement remain required evidence. See [current results and limits](../implementation/native-initial-lifecycle.md).
This decision removes no acceptance criterion.
