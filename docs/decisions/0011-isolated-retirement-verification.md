# Isolated functional retirement verification

Status: accepted design; implementation and installed verification remain open.

## Question

J17 requires an actually usable restoration before removal and again after it.
Authenticated inspection and restored database fingerprints cannot establish
application startup, retained access rules or usable Git transport. Starting a
verification copy also starts durable workers: `SourceReturnWorker` scans on
startup and can resume pending external writes. Verification must retain original
writer custody and keep those external effects outside this temporary copy.

## Alternatives and evidence

The current snapshot/data controllers retain the original journal lock, startup
fence, exact empty runtime groups, pointer, artifact and database observations.
Their receipts deliberately lack functional-restoration authority. The current
combined operator suite passed 115 Linux checks with eight foreign skips; the
separate actual encrypted-export/database experiment passed twelve checks. These
are component results, not installed functional retirement acceptance.

Copied-production offline restoration already exercises recovered sessions,
private collaboration/assets, outsider denial and actual HTTPS/SSH refs, clone and
a new authorized push. Its controlled Source and independent installation setup
do not establish continuous retirement custody. Reusing that procedure without a
fixed controller would separate destructive authority from its actual observations.

Using the original installed root or runtime groups for verification breaks
original quiescence. Launching a second ordinary restored instance can resume
queued external writes. Merely describing a restoration as successful, or accepting
caller-supplied booleans, provides no executable verification boundary.

## Decision and consequences

Codex primary agent accepts this boundary on 9 October 2026:

- Keep the original journal/driver lock and fence throughout verification and
  every subsequent action. Original runtime groups stay empty. Revalidate the
  original database and resources, archive/key and immutable code at the required
  boundaries; interruptions leave visible responsibility.
- Allocate and independently seal a separate operation-derived database, private
  root and verification installation UUID, with four fresh delegated runtime
  groups. The original controller remains in its original driver group. Pin all
  new resource identities before use and retain failed/ambiguous targets.
- Authenticate and inspect the original archive, import its database into the
  exact empty target, verify restored fingerprints and materialize its private Git,
  SSH and configuration contents separately. Preserve original keys/credentials
  and record the fixed operational adaptations: target UUID, paths, database and
  local ports. Rebind only managed Git hooks to that target.
- Add an explicit verification runtime mode. Disable automatic reconciliation and
  block external Barkpark calls, including foreground requests. Retained Source
  credentials stay private. Report this mode in readiness and refuse its use as
  ordinary upgrade/production activation evidence.
- Initially support the pinned Linux x64/PostgreSQL18.4/Node22.23.3 local profile
  with a loopback HTTPS origin whose retained certificate validates that host.
  Bind every verification listener to loopback and use independently reserved,
  distinct ports. Other origins/profiles refuse until their adaptation is verified.
- Launch only the fixed forge/web/edge commands from the digest-pinned artifact,
  under the new exact groups. Run real clean-candidate readiness, independently
  retained actor credentials, recovered private records/access-rule refusals and
  actual HTTPS/SSH Git probes. No arbitrary command/callback may assert success.
- Stop the complete new groups and reobserve their emptiness and target database
  clients before acknowledging restoration. Account for the target root/database,
  groups, credentials, diagnostics and any scratch in retention; they are not
  silently removed or called provider cleanup.
- Repeat archive authentication and actual usability after scoped source removal.
  Original absence must be observed through original identities, while the retained
  verification target remains independently bound. A snapshot observer that
  requires the original database present cannot serve this final absence check.

The full restoration plan needs a closed versioned form that binds both data and
functional verification inputs to the existing restoration digest. The current
five-field data-only plan remains supported for its existing scope and cannot
authorize removal by itself. The fixed coordinator must produce its own combined
receipts from actual observations; callers cannot supply a success flag.

Cancellation before destructive actions, interrupted-target reconciliation,
complete installed retirement and managed Cloud/provider deallocation remain
implementation work. Shared database roles, host identities and upstream user
credentials are retained shared resources, not installation cleanup. A local
retained archive cannot authorize destruction of the only host storing it.

This decision changes the execution design, not J17 acceptance criteria. No
current product release, functional-restoration pass or Cloud capability is
established by accepting it. Revisit the local-origin restriction with actual
certificate, routing and replacement-host evidence before extending the profile.
