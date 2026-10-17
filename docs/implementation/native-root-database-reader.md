# Retained read-only observation during staging

The complete production archive must stage within the existing operation bound
while retaining checks before every effect. Reopening a SQL process for each
observation makes those checks expensive. This source component reuses one
original Root read-only session for fresh identity and writer-exclusion SELECTs.
It remains unverified on an actual PostgreSQL/systemd installation until hosted
positive and original-reader-loss checks pass.

`NativeRootDatabaseReader` takes an exact protected
`NativeRootLifecycleObservation` in running `stage`. It independently selects
the pinned executable, private connection configuration and server scope from
that original lifecycle. There are no caller SQL, paths, credentials, environment
maps or callbacks. Each exchange has a fresh nonce, bounded single-line framing,
the same SQL PID/birth, loopback client port, read-only/read-committed settings and
no held advisory lease. Identity and exclusion statements are fixed SELECTs.

During each private read-only observation pass, the fixed exclusion SELECT's
existing `database` result supplies the complete identity as well as writer and
client observations. Both consumers use that one original reply. The shared
result is confined to the original Root process/thread and reader object, copied
defensively, and discarded when the pass ends or fails. The separate final pass
queries again; standalone consumers also query afresh. No result survives an
effect boundary. Initial reader admission still performs its two original
identity exchanges.

The reader brackets every actual exchange with original lifecycle/configuration/executable,
Root process/thread/namespace, owned child/pipe, TCP socket and server-kernel
checks. Lost original custody permanently refuses and closes only its own SQL
child. It never reconnects, adopts a replacement, acquires a writer lease, closes
the ordinary writer or completes a stage.

The shared [targeted TCP observer](native-tcp-socket-observation.md) performs a
fresh bounded kernel query for the already admitted loopback connection. It
still verifies the original process namespace and sole matching descriptor;
no connection identity is cached across checks.

Only the running archive stage retains this reader. Ordinary handoff windows
keep their short-lived observations so the extra connection cannot interfere
with the ordinary writer's one-client check. During Root extraction, identity and
exclusion views share the original reader; exclusion still requires exactly two
clients: the retained ordinary writer and this Root observer. Every existing
effect check remains, and the response deadline remains 240 seconds. Root closes
its reader before acknowledgement, allowing the ordinary owner to independently
check its original writer and staged output before recording completion.

Twenty-one portable grammar, framing and poison checks use explicit process,
kernel and observation stand-ins. They establish neither actual session custody
nor staging performance. They include one original query per pass, separate final
and standalone reads, defensive copying, distinct reader objects, changed writer
observations, malformed identity and original loss before return. Actual
original-reader client/backend-loss refusals,
the full production archive, runtime from staged output and all prior handoff
checks remain required before this repair is verified. Complete installation,
activation and recovery remain separate requirements.

The hosted fixture times fifteen fixed installed methods while serving the full
stage. Its receipt includes only bounded method names, call counts and overlapping
cumulative milliseconds. It excludes arguments, locals, caller maps, arbitrary
paths, SQL and exception messages. These diagnostic counters locate remaining
check cost; they grant no effect authority and do not change the payload, guards
or deadlines. Production deadline acceptance still requires an uninstrumented
complete stage and subsequent runtime from its staged output.
## Private configuration in an observation pass

The original read-only Root reader supplies one private configuration observation
within each existing no-effect Root pass. Its private method checks Root identity,
the original PID/thread and usability, the fixed installation path, and complete
equality with the originally captured file records and database URL. The live
binding, reader base checks and original writer-exclusion base checks reuse that
same reader's result only during the current pass. Constructor captures,
standalone calls, ordinary/non-stage fallbacks and the next pass remain fresh.

No pass spans an effect. The full before/after persistent fingerprints and the
separate final fresh pass remain, along with every original service, process,
namespace, pipe, SQL, socket, history, policy and capacity check. The fixed SQL
exchange, original child lifetime and two-client/one-writer condition are unchanged.
Private configuration values stay within the Root process and are never included
in ordinary receipts or timing output. This observation supplies no admission or
effect authority.

Ten portable cases use explicit parser/process/Root stand-ins for freshness,
returned-data isolation, original-reader separation, owner/path loss and permanent
failure without replacement. Ten actual Root filesystem cases use synthetic
private configuration at an isolated installation UUID; lifecycle, SQL and reader
construction remain explicit stand-ins. They cover leaf/ancestor aliases,
same-byte replacement, restored-mtime edits, owner/mode/link changes, unexpected
entries and closed views. Twenty fresh observations record only count and elapsed
time. Full installed staging/runtime and later uninstrumented deadline evidence
remain required.
