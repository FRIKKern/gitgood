# Supported Barkpark links

Experimental direction, 8 October 2026. J10 and M5 acceptance remain pending.

## Observed contract

Read Barkpark source at 68412eff4a0eb5a22cdc8e755e437c8dc66ceed3 and exercised an existing owned Cloud instance through its supported APIs. The live capability manifest identified build 1b5b65178, version 0.2.27.223. These revisions differ; a source expectation is accepted only after exercising the deployed contract.

Scoped document reads/mutations use /w/:workspace/p/:project/v1/data/... and retain the source's revision, document identity and transaction receipt. Task lifecycle APIs are flat /v1/tasks/... and derive workspace membership from the credential. A dedicated private verification workspace prevents task claims from falling back into unrelated work. The task schema returned private visibility. Two distinct, expiring service credentials each enumerated exactly their own workspace. A real scoped task read succeeded for its credential and returned 403 to both the other credential and an anonymous caller. Private receipts retain the actual principal, workspace, document/revision and transaction IDs; they contain no bearer token.

Use canonical scoped document APIs for linked-record reads. Do not depend on flat task endpoints for project-specific authorization. Capability discovery is read-only; deployment health does not prove task, identity or native forge hosting support.

The native adapter subsequently exercised deployed build 9d4d2bf33, version 0.2.27.225: HTTPS GET/POST, foreign credential denial, original-transaction idempotency replay and unchanged existing document revision passed. Capability brief view omits optional token/build metadata even when requested; use the full view when those fields are needed. Retain the actual build per experiment.

## Ownership and permissions

Gitgood owns code, pull requests and link-operation records. Barkpark owns tasks, specifications and their contents. Persist source locators and operation provenance, rather than a second editable task store.

Each Gitgood account supplies its own selected Barkpark credential and workspace/project context. Store credentials encrypted on the backend; never use the Cloud bootstrap/admin credential for ordinary linked-record reads or writes. A selected machine credential represents that service, not the Gitgood user impersonating a Barkpark human. Record both actors separately. A connection label supplied by a caller cannot establish an upstream identity.

Authorize the native repository first, then read the external record with the requesting account's current connection. Do not show external titles, locators or snippets to a reader refused by Barkpark. Revalidate foreground views, clear their source contents on denial/outage, and reject delayed responses from an older connection/access generation. Missing, denied and unavailable states must remain distinct where the owner can establish them; a 404 alone cannot prove deletion.

## Links and retries

A reverse link must use a source-supported field or schema extension in the owned workspace. The observed task code_refs shape is oriented to GitHub PR numbers and Git commits; it is not evidence of a generic native-forge link widget. Prove actual Studio navigation before accepting J10-A. Do not overwrite a task brief, claim ownership of source fields, or assert that storing an unknown JSON field establishes navigation.

A private prototype used revision comparison to preserve the task purpose/criteria and store one PortableDoc link block. The supported browser token-login form admitted the actual service principal to the canonical scoped Studio task route. However, Studio rendered the task's object-typed brief as escaped JSON, with no usable anchor. This approach does not establish reverse navigation and must not be counted as J10-A. Prefer a source-owned, schema-supported reference/pointer surface whose actual renderer has been exercised; do not silently edit the global task schema or accept a raw JSON URL as completed UI.

A subsequent private Paper experiment exercised deployed build 132f1c86a, version 0.2.27.237. A scoped createIfNotExists mutation created an unfinished specification fixture with native PortableDoc blocks; foreign and anonymous document reads returned 403. Initial server HTML had no target anchor, while the actual Studio browser canvas rendered one hyperlink after initialization. Use this source-owned Paper surface for further reverse-pointer work. Its example URL is nonfunctional and proves rendering only, not J10-A or a reconciled cross-owner write.

Reverse links should contain an opaque native change URL that still authorizes at Gitgood; do not disclose private native repository titles/slugs to all readers of an external task. Keep consequential cross-owner writes in a durable journal. Persist an operation identity before the request, use source revision comparison and supported idempotency, and reconcile unknown outcomes against actual source state. Preserve other links and refuse conflicting revisions. Account/credential changes must not replay an operation as another actor. No cross-system transaction or instantaneous remote revocation guarantee is claimed.

A further owned experiment exercised build 9b389bf7a, version 0.2.27.240 against the actual native development candidate 55a66ada932526cce4002578dea30e6df70a86af. Studio's supported hover/link-preview Open action opened the opaque address. Native sign-in preserved the UUID and reached the permitted private change. Repeating the source action with a native outsider account showed generic refusal and no private title. Thus source permission did not grant native permission. The initial probe incorrectly required a URL without the native page's normal sha/path/view parameters; exact origin and change-path verification plus the real private heading passed. This is private development reverse-navigation proof, not native link/journal or complete J10 acceptance.

## Transport and availability

Only the installation-configured origin is contacted. Require HTTPS with normal peer and hostname validation, refuse redirects and inherited proxies, and pass secrets through subprocess stdin. Bound input, response size, deadline and concurrent workers. An optional installation-managed GITGOOD_BARKPARK_CA PEM file supplies explicit trust for a private source issuer while normal certificate-chain and hostname checks remain enabled; inherited trust variables stay excluded. Development fixtures may explicitly allow loopback HTTP; production must reject it.

Give external I/O a separate bounded supervisor from Git command workers. An external outage must produce an unavailable source, preserve native repository access, and leave pending responsibility visible. The initial adapter is only an I/O utility: Elixir retains authorization, records, retry decisions and ownership.

## Remaining proof

Per-account encrypted backend connections are implemented separately with finite-expiry, single-workspace API service credentials and source-verified identity; see [their contract](../implementation/barkpark-accounts.md). Account settings have browser UI checks using synthetic connection responses and actual native sessions. Complete live browser connections, independent native/external document denial, deleted/missing records, safe reverse navigation, delayed-response invalidation, source outage/recovery and unknown-write reconciliation remain implementation and J10 verification work. Fixture provisioning alone does not configure the live Gitgood implementation ledger or verify a journey.
