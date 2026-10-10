# Native database writer exclusion

The generation reconciler can now hold one fixed ordinary PostgreSQL session
under the existing application's advisory namespace/key. The caller must
independently establish the trusted psql executable and expected durable database
identity. The component refuses privileged roles, memberships, different
cluster/database/owner identity and unexpected other client connections.

Acquisition uses `pg_try_advisory_lock` once. Subsequent checks independently
observe the actual granted lock, exact backend PID and server birth, unchanged
ordinary identity and absence of other clients. A fresh request nonce binds each
bounded reply. The child receives an explicit private environment, disabled
password-file fallback and no psql startup file. Credentials stay out of argv.
No arbitrary SQL method, marker or generation pointer is exposed.

Failure poisons the object and reaps its directly owned psql child. Forked or
other-thread copies cannot check or close the original session. Closing a client
does not establish a new owner's authority; fresh acquisition must succeed.
Callers must check before and after fixed effects and retain uncertainty after
any lost lease. This primitive installs no continuous controller monitor.

Eight boundary checks passed. Five actual ordinary-role PostgreSQL 18.4 checks
passed: stable held identity, competing writer refusal, unexpected idle-client
refusal, loss of an exactly guarded owned backend, and fresh independent
reacquisition. Original identity and retained data stayed unchanged. Four
independent custody checks bound 43 retained source modules and the psql binary,
observed the original bounded group empty, and found no remaining fixture client
or writer lock. The source-defined key matches the existing Elixir lease; this
experiment executed no packaged Elixir runtime or generation-aware marker.

The full Linux suite passed 264 checks with 12 expected platform skips; all
33 planning checks passed. Twelve immutable private source records retain the
current producer, verifier, source bytes and results: review SHA256
`0a3f5e81b94d2bd4526c5819c71f0e3db1f844f8efe2efa7580c74731228a213`,
index SHA256 `3ef0610c62e0ba922674b28c6005fa0bb9e0685fa9cc60bd35fb88db57ed5da6`.
Current required CI remains a separate integration gate.

Exclusion is cooperative with native writers using the shared lease. Arbitrary
administrative connections remain outside that contract. Deployed authentication,
actual service-controller integration, continuously monitored lease loss,
generation publication, old-owner reconciliation and retained lifecycle recovery
remain separate gates. No complete journey or release acceptance is established.
