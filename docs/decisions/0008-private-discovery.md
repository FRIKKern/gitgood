# Private discovery and access boundaries

Status: experimental implementation; adversarial/browser/reconnect evidence required before integration.

J13 starts with Gitgood-owned repositories, pull requests, release records and their actual native audit events. Search and activity are bounded permission-filtered database reads, without another authoritative copy of those records. Supported Barkpark work links will extend this view during J10; unconfigured or failed external sources must remain explicit.

Activity uses full bounded snapshots of committed native events. Every refresh replaces the visible snapshot. It does not assume database sequence allocation is commit order or infer gaps from hidden global identifiers. Reconnection and failed/dropped refreshes require a fresh snapshot; failure cannot be displayed as no activity. Historical pagination is scoped to the current actor, credential, access context, filter and expiry through an authenticated encrypted cursor. A changed context requires a reset. Only permitted rows contribute to page boundaries, snippets and has-more flags; no global totals or event sequence positions are returned.

New discovery links use opaque collaboration UUIDs. Internal primary keys remain internal for joins and recovery. Existing numeric pull URLs remain authorized compatibility aliases, while newly rendered links use UUIDs. Backfill must retain records and attribution. Downgrade refuses to discard published link identities when records exist.

The browser needs one access boundary shared by all routes. Account changes, sign-out and authorization denials must discard private query results, transient credentials and actor-bound drafts. Responses started under an older browser access generation cannot refill the newer cache. Foreground session checks detect membership changes; reconnect/focus requires a current access check before private cached views reappear. Unavailable access checks hide private views and offer retry. A periodic check provides bounded detection rather than a claim of instantaneous erasure; already downloaded data cannot be recalled.

Required proof includes two permitted identities with different teams, an outsider and reader, hidden-match and wildcard queries, foreign/expired/tampered cursors, permission changes between pages, account switching while requests are delayed, cross-tab logout, dropped/replayed refreshes, backend outage, stable links across restart/upgrade and retained actual actor/time attribution. Native source fixtures and later supported Barkpark links need separate provenance. Capacity and freshness targets still require M4 workload measurement.

Main candidate `969a336` failed the activity source-unavailable browser assertion;
the captured view retained a successful recent snapshot. Its actual failure and
partial artifacts remain archived. The fixture had installed interception after
navigation could already start its initial activity request. A controlled probe
against the pinned query library confirms that refetch during initial loading
reuses that request, while refetch after a successful baseline reaches the changed
source and fails. The exact failed-run request timing was not recorded, so this
is a supported timing diagnosis rather than a claim about unseen network events.
The browser fixture now awaits the successful initial record, installs the fault,
observes its actual 503 response and retains the same error/no-stale-record checks.
No timeout increase or application behavior change substitutes for that proof.
