# Private discovery implementation

This worktree starts J13. It is not an accepted activity/search journey yet.

Implemented primitives:
- Pull requests and review/release events have persisted opaque public UUIDs. Newly emitted links/record IDs use those UUIDs. Numeric pull URLs remain scoped compatibility aliases; merge audit joins retain internal IDs.
- The migration backfills existing rows and refuses a destructive downgrade once collaboration records exist. Populated upgrade/restart proof remains required.
- Access.with_session checks the actual current session credential, expiration and actor, and holds credential/membership share locks for the read callback. Role changes/revocation serialize with it in the established credential-before-membership order.
- Public access context is a keyed digest of current session and membership claims, not exposed primary-key counters.
- Context tests cover changing credentials, downgrade/removal and current revocation. A real-database test observes lock-timeout refusal of concurrent revoke/downgrade, then succeeds after the read ends.

Still required: permission-filtered native search and activity snapshots; opaque scoped pagination; stable event links; shared browser access/cache boundary; delayed-response/account-switch and cross-tab checks; dropped/replayed refresh and outage recovery; complete upgrade/restart and copied-production validation. Supported Barkpark records enter through J10 rather than an invented duplicate task store.

See the experimental [discovery decision](../decisions/0008-private-discovery.md). Current release/browse/private workflow proof must be revalidated when these shared boundaries change.
