# Native SSH identity and transport

Status: accepted bounded native SSH design, 8 October 2026. Owner/evaluator: Codex under delegated authority.

Use OTP 29.1.1's SSH daemon with a custom channel and key callback, PostgreSQL-owned Ed25519 public keys and the same Elixir repository/credential/membership leases and push responsibilities used by HTTPS. Run real stateful Git upload-pack/receive-pack with bounded full-duplex stdin/stdout. Git command strings are parsed into a strict repository command grammar; no shell, PTY, SFTP, arbitrary environment or TCP forwarding is granted.

Public-key callbacks bind the connection process to the registered actor/key; only successful public-key authentication activates that binding. Each command resolves the current credential, expiry and repository membership. Key fingerprints are globally unique and remain reserved after revocation; a different actor cannot claim another actor's key. Registration is a transaction with an actor-scoped idempotency key, not an authorized_keys publication job. Loss of a response retries the same durable identity.

An admitted operation holds the credential/membership/repository lease. Revocation prevents new commands (including new channels on existing connections); a Git operation admitted first may finish within its bounded lease. Native push hooks enforce the existing protected main and branch policy. Raw main changes, deletes, tags and force pushes remain denied.

Host private keys are operator-provided persistent files outside replaceable artifacts; startup refuses configured SSH without a usable host key. The daemon advertises an explicit endpoint and host fingerprint. Fixture tests use generated isolated host/client keys and strict known-host verification, never a production private key.

Limits: 16 connections including unauthenticated negotiation, four channels per connection, four shared transport/command slots, 32 MiB input/output, 64 KiB stderr, bounded SSH negotiation/idle/channel/native-process deadlines, stripped child environment, existing process-group/job and memory cleanup. Real OpenSSH/Git clients exercised stream flow, EOF, interruption, strict host verification and cleanup before acceptance.

Alternatives: an OpenSSH forced-command service would add a separate OS identity/authorized_keys publication boundary. A buffered stateless HTTP emulation over SSH would not establish stateful SSH compatibility. The native OTP channel keeps authorization in Elixir while preserving ordinary Git's bidirectional transport.

Acceptance evidence: [PR #13](https://github.com/FRIKKern/gitgood/pull/13), source b58de135e8e378d3d5fbaf2cf4465f5574a82d30, integrated as 874fb8442b5e2e734c4c8dbd35c4cedbb673222d. [Linux CI run 37765503474](https://github.com/FRIKKern/gitgood/actions/runs/37765503474) passed 34 backend tests, three real browser/client flows, recovery and copied-production checks on its recorded merge candidate. Windows copied production passed on the clean source candidate. Artifacts include criterion-linked client receipts, runtime/build identities and private fixture records. Prior failed Linux expectations/clean-stamp checks were repaired and rerun; they are not accepted evidence. This accepts the bounded design, not M4 or a product/Cloud release. Future candidates must reassess current evidence.

Sources: [OTP SSH](https://www.erlang.org/doc/apps/ssh/ssh.html), [server key callback](https://www.erlang.org/doc/apps/ssh/ssh_server_key_api.html), [server channels](https://www.erlang.org/doc/apps/ssh/ssh_server_channel.html). Authentication callback and activation ordering were inspected in OTP-29.1.1 ssh_auth.erl and ssh_fsm_userauth_server.erl.
