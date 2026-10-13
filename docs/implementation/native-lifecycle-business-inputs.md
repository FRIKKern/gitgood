# Private inputs for native migration and bootstrap

The native maintenance workers need original migration expectations and first-owner
inputs before applying effects. Their existing input reader checks sealed file
custody and protocol, while the guarded startup API checks the requested action.
Neither currently dispatches business effects.

`NativeGenerationLeaseGuard.private_business_inputs(action)` takes only `migrate`
or `bootstrap`. It brackets a private projection with checks of the original
captured guard and input descriptors. The original recorded stage must be running,
match the action, and admit maintenance. Request digest, operation and candidate
must match the captured observation. Refusal poisons the guard; restoring bytes,
permissions or history cannot revive it. No fresh reader, caller-supplied authority
map, input path, command or alternate owner is accepted by this method.

This is private engine data, with **no stage effects or exclusion granted**. It is
not a status result or public artifact and must never be logged or returned to an
operator. Bootstrap projections contain the original password and its ordered
request digest. Migration projections omit both. The existing monitor wire and
packaged application callback remain unchanged; transport into the permanent BEAM
and fixed business-worker execution are still required.

## Business payloads

These are fresh protocol-2 subdocuments. Existing protocol-1 enrollment/upgrade
inputs and journals are not adopted. Their outer canonical files remain protected
by [operation input custody](native-operation-inputs.md). Other allocation,
artifact and lifecycle-plan semantics still belong to their stage engines.

| Purpose | Fixed file | Closed `business` fields |
| --- | --- | --- |
| Initial enrollment | `inputs.json` | `kind`, `installation`, `operation`, `candidate`, `migrations`, `bootstrap` |
| Upgrade | `plan.json` | `kind`, `installation`, `operation`, `candidate`, `migrations` |

Kinds are `native_initial_business_inputs` and `native_upgrade_business_inputs`.
Installation, operation and candidate must equal the original sealed observation.
The enclosing file must have integer protocol 2. Fixture metadata without the
business subdocument refuses; its synthetic stage receipts cannot authorize a
business projection.

`migrations` contains exactly `before_versions` and `target_versions`. Each is a
sorted list of distinct positive integers below 2^63, capped at 1024 entries. The
target is nonempty and includes every before version. Initial enrollment requires
an empty before list. These are immutable expectations, **not observations of the
current database or proof of candidate compatibility**. The executor must compare
the actual schema and packaged migration inventory before effects, and observe
the resulting schema afterwards. This projection supports no schema rollback.

Initial bootstrap contains exactly `installation`, `request`, `username`, `team`
and `password`. Installation matches the sealed installation and request matches
the original operation. Names use the existing first-owner entry rules; the UTF-8
password is 12–256 bytes with NUL excluded. No role choice is accepted: the existing
durable first-owner command owns that behavior. Its ordered JSON-array SHA256
contract is retained, including Unicode encoding. Upgrade cannot request bootstrap.

## Required execution and evidence

The private parser and projection establish neither writer exclusion nor immutable
ownership publication. Business effects still require the permanent native
ownership boundary, an original live SQL lease/fence, independently verified
artifact/configuration, stage-specific resource/schema prerequisites and exact
interruption reconciliation. They must not be executed from a caller projection
or a journal receipt alone.

Focused tests cover closed formats, wrong stages/purposes/bindings, terminal
refusal, forward-only bounded expectations, bootstrap identity/Unicode digest,
password-free migration projection, detached values and guard poisoning. Guard
orchestration tests use explicit custody stand-ins. A separate ordinary Linux
test uses actual sealed private-file descriptors with a Root/service stand-in.
The existing installed ownership case exercises actual Root/input/journal custody
but executes no business projection or stage effect. Full native startup, effects,
reboot/replacement-host recovery and J14/J15 acceptance remain unverified.
