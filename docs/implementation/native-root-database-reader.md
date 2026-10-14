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

The reader brackets exchanges with original lifecycle/configuration/executable,
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

Thirteen portable grammar, framing and poison checks use explicit process,
kernel and observation stand-ins. They establish neither actual session custody
nor staging performance. Actual original-reader client/backend-loss refusals,
the full production archive, runtime from staged output and all prior handoff
checks remain required before this repair is verified. Complete installation,
activation and recovery remain separate requirements.

The hosted fixture profiles only fixed installed guard functions while serving
the full stage. Its receipt includes bounded call counts and self/cumulative
milliseconds, with fixed source basenames and numeric line numbers. It excludes
arguments, locals, caller maps, arbitrary paths, SQL and exception messages.
These counters locate remaining check cost; they grant no effect authority and
do not change the payload, guards or deadlines.
