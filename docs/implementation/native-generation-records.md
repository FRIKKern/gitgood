# Closed native resource-generation records

[Decision 0018](../decisions/0018-native-supervision-generations.md) separates
durable installation identity from replaceable kernel resources. The
[record module](../../tools/deployment/resource_generations.py) implements the
closed representation and predecessor checks. It performs no filesystem,
process, database, continuity or publication operation.

## Format

Each record has protocol 2, kind `resource_generation`, a unique generation UUID,
installation UUID, durable-binding SHA-256, predecessor SHA-256 or an explicit
null for the first record, a validated service-scope observation and a UTC
creation timestamp with six fractional digits. Canonical JSON sorts keys and
rejects nonfinite values. Its SHA-256 provides the predecessor identity.

The scope must identify the installation's fixed root-owned unit, actual manager
birth, boot/namespaces, service account, parent and five groups. Directory
identities must be distinct, belong to the account and use one cgroup device.
Paths must match the installation and subgroup names. Manager credentials must
have a non-root GID, no other supplementary group, empty capability sets and
`NoNewPrivileges`. CPU, memory and zero-swap bounds are explicit.

The observation must report service admission and explicitly leave installation
readiness false. A generation record cannot establish artifact readiness or
confer authority merely by changing that flag.

All nested objects have closed field sets. Unknown fields, commands, credentials,
duplicate JSON properties, boolean numeric identities, malformed paths,
privileged state, aliased groups and oversized payloads refuse. Constructors
copy their input so subsequent caller edits cannot mutate the created record.
Namespace identities use the same positive unsigned 64-bit bound as other
kernel identities; a well-formed numeric string above that limit refuses.

## Chain behavior

A successor must reference the exact canonical predecessor digest, preserve
installation and durable-binding identity, use a different generation UUID and
describe a changed resource scope. An unchanged scope cannot be renamed as a
new generation. A changed durable binding requires a separately specified
continuity or replacement-host restore protocol.

Timestamps describe record creation and do not authorize transitions. The
predecessor relation establishes record order. This validator does not infer
that an old process is dead or signal any PID or cgroup.

## Verification and remaining authority

Sixteen tests cover exact links, replay/reuse, unknown fields, privileges,
aliasing, malformed identities and bounded decoding. A separate syntax exercise
consumed both actual boot observations from the privilege-hardened admission VM,
roundtripped the records, rejected three malformed-chain cases and preserved the
original observations.

The full ordinary-account Linux suite passed 225 checks with 12 expected
foreign-platform skips, and all 33 planning checks passed. The private source
archive contains eight immutable records, including the exact module, tests,
actual-scope consumer receipt and logs. Its review SHA-256 is
`ef3b070060812d2bae98379a8d5a69dc44479d7aee011b237abec3659c0bdc85`;
its digest-index SHA-256 is
`e8e07a7996b1b4e483869ccd03b8c83e16c72c090175da148e3b145b364cfef5`.
Every archived file passed digest readback. The review also binds the current
29-record admission and five-record installed-source archives.
This second archive binds the namespace-bound revision. The initial eight-record
archive and its original producer/receipt remain retained under their earlier
revision; they are not substituted for the revised source evidence.

That exercise deliberately used a synthetic fixture-data digest. It observed
no PostgreSQL, store, configuration or key installation binding. It validates
the record format against actual scope data and establishes no generation
publication or durable continuity.

Before publication can exist, implement independently observed durable bindings,
private immutable record custody, installation locking, database writer
exclusion, exact old-owner reconciliation, sealed transitions and atomic current
pointers. Caller-response loss and competing controllers require actual recovery
tests. Runtime/maintenance leases, lifecycle recovery, allocation and Cloud remain
separate unfinished work. Required current CI and source applicability also remain
integration gates.
