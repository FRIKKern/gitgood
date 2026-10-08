# Native Barkpark link records

Work package following opaque change addresses. J10 remains pending until actual two-way navigation, denial, outage and recovery all pass.

## Intended behavior

A repository writer attaches a supported task or Paper by exact document identity through their current account connection. Gitgood stores a link identity, scoped source locator, verified revision and the actual native/service actors. It stores no editable task/specification or cached source title/body.

Each native reader checks repository access first. Their own current Barkpark connection supplies source access; the creator's credential is never reused. Native link listings expose only opaque identities and lifecycle state. Source titles, locators, Studio URLs and snippets appear only after a successful current source read. A source 404 means unavailable/missing to this actor, not proof of deletion.

## Durable native operations

Serialize link mutations under the existing native repository writer lease and a current connection generation check. Compare source scope by installation origin and verified workspace/project/dataset IDs, not a caller label. Bound supported document identities and link count. Enforce database uniqueness and actor-scoped request digests. An exact replay returns its historical receipt and never reactivates a removed link. A new attach request for a removed identity may explicitly reactivate it and gets a new generation.

Remove leaves a tombstone and operation provenance. Unknown or foreign link IDs have the same native refusal. Attachment/removal are native operations; no reverse source write is claimed by their success.

## Independent read boundaries

External I/O holds no native database lock. Recheck current native access, link generation and connection generation after I/O. A changed account connection invalidates foreground source content, even if an old response was permitted when it began. Source denied, unavailable, unconfigured, connection changed and unknown/missing states are bounded, contain no original response body, and preserve ordinary Gitgood browsing.

## Next dependent work

The dependent [return-pointer journal](barkpark-return-pointers.md) records source-write responsibility before contacting Barkpark. Use a deterministic owned Paper block, source revision comparison, a stable source request key and actual source reconciliation after an unknown outcome. Neither native attachment nor a prototype Paper pointer substitutes for that journal.

## Required evidence

Exercise real Postgres constraints, duplicate native requests, different actor requests, removal/replay/reactivation, independent source actors, foreign native records, changed source connection and source replies held through native role removal. Use actual supported scoped HTTP paths. Test schema upgrade/rollback refusal with populated records and separate process restart. Browser, live source and complete J10 acceptance remain separate gates.


## Browser and transport

The change page lists opaque native links and offers source context on demand. Foreground polling checks current native link and account connection state. Connection errors, generation changes, source refusal and failed source refresh hide prior source titles/snippets. Mutation completions re-fetch native state; lifetime/access tickets refuse old-account updates.

GITGOOD_BARKPARK_CA optionally names an installation-managed PEM trust bundle for the pinned source origin. Default operation uses normal platform trust. Only this explicitly configured trust file is passed to the source worker; inherited proxy/trust variables remain excluded. TLS chain and hostname checks stay enabled. This permits owned private HTTPS verification without adding a certificate bypass.

The native API accepts links at /api/repos/:team/:name/pulls/:id/links. Attachment accepts exactly type, document_id and connection_generation. GET lists native identities; GET /:link with connection_generation retrieves currently authorized source context. POST /:link/remove accepts only the current native link generation. Writes use the native CSRF/idempotency boundary.


## Upgrade and persistence fixtures

verification/source_links_upgrade.exs starts from the previous schema with a native account/change and an actually verified synthetic HTTPS connection. It exercises empty downgrade, two concurrent same-key attachment requests held together at source I/O, eight concurrent same-key removals through an ordinary Postgres pool, original attach replay after removal, populated and link-only downgrade refusal, and an explicitly constructed event-only corruption fixture. That last fixture temporarily removes its FK only inside the owned disposable database, then restores the exact row/constraint. A separate VM checks retained native/source identity, credential encryption binding, lifecycle and original request receipts. These checks do not establish coordinated backup or replacement-host restoration.
