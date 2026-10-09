# Native SSH implementation and verification

Gitgood owns account keys in PostgreSQL and runs an OTP SSH daemon. Real upload-pack and receive-pack processes use a bounded full-duplex binary adapter. The existing Elixir leases, trusted push hook, protected-main rules and durable push records remain authoritative.

## Identity and retry

The signed public-key authentication callback binds the connection to one actor and SSH credential. An unsigned key probe alone cannot activate that binding. Commands resolve the current key, expiry and membership again. Only Ed25519 public keys are accepted in this slice; certificates, RSA, hardware-key formats and deploy keys remain outside it.

Keys expire after 365 days. Fingerprints are globally unique and stay reserved after revocation. Reusing a registration's actor-scoped idempotency key and identical body returns the same identity, including after a lost response. A changed body conflicts; a new registration cannot reactivate a revoked identity. Separate sessions for the same actor serialize registration.

Revocation prevents new commands, including new channels on an existing connection. An operation admitted before revocation may finish while its credential/repository/membership lease is held; the revocation update waits for that bounded operation. A receiver disconnect before EOF cancels its native process tree. After the full upload and EOF, an independent push worker keeps responsibility for reconciliation even if the receiver disappears. An uncertain ref outcome blocks further writes.

Successful and failed pushes retain actor and credential IDs, proposed ref updates and reconciled outcome. Authorized repository members can inspect these through the operations endpoint. IDs are attribution, never credentials.

## Configuration

SSH is opt-in. Generate a persistent Ed25519 host key outside the replaceable release:

```sh
mkdir -p /var/lib/gitgood/ssh-host
chmod 700 /var/lib/gitgood/ssh-host
ssh-keygen -q -t ed25519 -N '' -f /var/lib/gitgood/ssh-host/ssh_host_ed25519_key
chmod 600 /var/lib/gitgood/ssh-host/ssh_host_ed25519_key
export GITGOOD_SSH_PORT=2222
export GITGOOD_SSH_HOST_KEY_DIRECTORY=/var/lib/gitgood/ssh-host
export GITGOOD_SSH_PUBLIC_HOST=gitgood.example
export GITGOOD_SSH_PUBLIC_PORT=2222
```

The listener binds loopback. A deployment must explicitly route raw TCP to that listener; an HTTP reverse proxy alone does not publish SSH. Public host/port describe that route. The copied-production experiment proves loopback transport, not a managed Cloud TCP endpoint.

The authenticated SSH-access page publishes the host fingerprint and repository-specific SSH URLs. Verify the fingerprint through a trusted installation channel before accepting it in a client. The displayed key is derived from the configured private host key, not an unchecked public sidecar. Preserve the host key across replacements and backups. Rotate it by quiescing and restarting the service and updating trusted client fingerprints; do not replace it underneath an active daemon.

Configured SSH without a usable host key refuses startup. Loss of the daemon or host key rejects readiness. An installation with SSH disabled can retain registered keys and reports SSH unavailable; registration alone does not promise transport availability. Rollback of the SSH migration refuses when SSH credential history exists. Use compatible rollback artifacts; do not erase keys or push attribution to force a downgrade.

## Bounds and unsupported capabilities

Connections (including unauthenticated negotiation): 16. Channels per connection: four. Shared transport slots and native command processes: four. Pending input before native startup: 1 MiB. Input and stdout per command: 32 MiB each; stderr: 64 KiB. Frames: 64 KiB. Native deadline: 60 seconds, port deadline: native deadline plus five seconds, channel deadline: 90 seconds. Negotiation and idle intervals are bounded. Child environment is stripped; Windows jobs or POSIX process groups clean up descendants, with per-process memory ceilings.

Managed Git commands, including HTTPS and SSH packing, explicitly use `pack.threads=2`. Git's default CPU detection can see all physical-host CPUs despite a smaller deployment CPU allocation, and its packing thread stacks can exhaust the existing 512 MiB process limit. The thread limit overrides repository configuration while preserving process, memory, timeout and byte ceilings. It does not set limits on an external contributor's Git client.

OTP channel sends apply flow control and a five-second send deadline. The receiver mailbox can buffer output up to the command output ceiling; this is a bounded buffer, not constant-memory streaming. These limits target the initial private pilot and are not a large-repository benchmark.

No shell, PTY, SFTP, arbitrary command/environment, password authentication or TCP forwarding is granted. Command grammar accepts only canonical Git upload-pack/receive-pack repository paths. Current HTTPS restrictions also apply: protected main, no force rewrites/deletes, LFS or repository-supplied executable hooks. New immutable tags are supported for private releases; tag replacement/deletion is denied.

## Repeatable evidence

- `mix precommit`: registration ownership/retry/duplicate/expiry/revocation, CSRF, command grammar, stream byte preservation and EOF regression, limits, descendant cleanup, and revocation on an existing OTP SSH connection.
- `npx playwright test`: browser registration with a deliberately lost persisted response, strict OpenSSH host verification, ordinary Git clone/push/fetch, a 1 MiB random binary transfer, protected main, reader/outsider/wrong-account denial, duplicate denial, denied exec/SFTP, interrupted native SSH upload/retry, actor/key attribution and browser revocation.
- `npm run verify:production` in apps/web: repeat browser/client checks against copied release artifacts; restart and prove the same host/account identity and returned SSH URL serve the persisted main SHA.

SSH receipts contain synthetic IDs, refs and public fingerprints. Private client/host keys remain in disposable ignored fixture directories and are excluded from artifacts. Candidate/spec manifests and CI conclusions establish freshness; this document alone does not establish J03 or M4 completion.
