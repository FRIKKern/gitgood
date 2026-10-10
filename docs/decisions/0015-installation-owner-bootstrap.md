# Durable first-install owner bootstrap

Status: accepted implementation design; verification pending.

First installation needs an owner before authenticated repository and Git checks.
The existing release bootstrap creates a user and membership transactionally but
has no durable request receipt. A lost response cannot safely distinguish the
created actor from a conflicting actor. Codex primary agent chooses a separate
fixed first-owner entry point as a J14 dependency. Existing fixture/local actor
bootstrap remains available for its documented scope.

The new entry point accepts an independently digest-bound private installation
UUID, request UUID, username, team and password. It fixes the role to owner,
accepts no commands or callbacks, and creates at most one installation-owner
receipt per database. Database transaction locking serializes admission. The
initial database must contain no users or memberships; existing installations
cannot be silently adopted. User, membership and receipt commit together.

The receipt stores a keyed input commitment under the installation secret, never
the plaintext password or an exposed fast password digest. Exact request repeats
return recorded metadata. Different input, a new request after completion, or a
different installation refuses. Repeats cannot reset passwords or restore changed
memberships. Historical creation metadata is distinct from present login,
permissions, readiness and artifact verification, which the installation
coordinator must observe separately.

This does not allocate resources, perform complete enrollment, configure Cloud,
or establish J14 acceptance. It adds one schema migration; compatibility and
restoration must be verified for the resulting artifact before installation.
Required checks include exact lost-response replay, input conflict, existing-data
refusal, transaction rollback and competing initial requests on actual Postgres.

Interrupted execution also needs a separate read-only observation. Its entry uses
only a temporary database repository, a READ COMMITTED/READ ONLY transaction and
the same creation lock. It reports committed absence or exact recorded creation
without starting application services, creating an actor or restoring changed
access. Existing unreceipted actor data and mismatched requests refuse. The
controller must not interpret absence as a reservation or historical metadata as
current authorization.
