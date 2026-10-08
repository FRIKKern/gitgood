# Native smart HTTP transport
Accepted implementation direction, 8 October 2026. D04 evidence breadth remains under active verification.

Elixir authenticates scoped Git credentials, resolves membership and the internal UUID store, and invokes standard
`git upload-pack` / `git receive-pack` in stateless RPC mode.
The advertisement preamble follows [Git's HTTP backend implementation](https://github.com/git/git/blob/v2.53.0/http-backend.c).
Protocol v2 read advertisements omit the v0/v1 service preamble. Push remains the standard receive-pack protocol.
Using pack commands directly avoids requiring git-http-backend in Windows distributions that omit that executable.
Git owns negotiation, packs, quarantine, fsck and conditional ref updates; Gitgood owns access and branch policy.
There is no anonymous or dumb-HTTP object endpoint.

A small Python 3.12+ standard-library adapter closes child stdin correctly, bounds output and lifetime, strips inherited application secrets,
and terminates process groups on Linux or job objects on Windows. It is an I/O utility, with no forge records or policy.
Elixir supervises at most four command adapters and four push workers. A completed upload runs in an independent push worker;
a lost HTTP response cannot discard its database lease or durable responsibility.
A separate short-lived database connection commits the operation intent while a NO KEY UPDATE repository lease serializes mutations.
The pre-receive hook receives an ephemeral operation capability in environment/stdin, calls only the loopback backend, and persists exact
old/new refs before Git can update them. No user commit installs a server hook.
Initialization and recovery do not execute user code.

Current bounds: 32 MiB request/pack input, 32 MiB transport response, 60-second Git RPC deadline, 64 refs per push.
Plain browser API bodies remain capped at 1 MiB.
The initial main branch is initialized by the repository creator; later raw main updates are refused.
Feature branches allow fast-forward writes; deletes, forced rewrites, tags, LFS and broader format interoperability are not yet supported.
HTTP-compressed RPC bodies are refused pending a bounded decompression experiment.
The store format is SHA-1. Compatibility is explicitly limited to the tested clients and fixture workloads.

Reconciliation compares durable proposed refs with actual refs. Applied, failed and uncertain outcomes remain distinct.
An unavailable ref lookup never becomes a missing ref. Uncertain outcomes block further writes.
This does not establish the later protected merge marker and restart protocol in D05; those experiments remain required.
