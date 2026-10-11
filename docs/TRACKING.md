# Tracking and report contract

Barkpark owns the execution ledger in the private **Gitgood / Delivery / production** scope. Its goal is `gitgood-first-release`, with eight milestone containers `gitgood-m0` through `gitgood-m7` and journey tasks `gitgood-j01` through `gitgood-j17`. These are ordinary task documents with goal/phase/journey labels. The ledger was introduced after native implementation began; creation is not retroactive acceptance. It does not reuse Barkpark Studio's goal.

The milestone and journey catalogs remain normative planning structure. Each journey owns its acceptance criteria. [evidence/ledger.json](../evidence/ledger.json) identifies the authenticated source. [evidence/status.json](../evidence/status.json) is an observation snapshot for derived views, not an editable replacement ledger.

Each journey task's private `gitgood` provenance object records its journey ID, requirement-file SHA256 and explicitly declared implementation state/reference. `planned`, `in_progress` and `implemented` describe implementation. Task lifecycle, closure and criterion stamps cannot create verification or release. The initial population leaves all acceptance criteria unmet until evaluated. Existing development work remains in progress while its full journey is being verified.

## Refresh

Supply a finite, workspace-bound credential through `GITGOOD_LEDGER_TOKEN`, then run:

```sh
npm run status:refresh
npm run generate
npm run check
npm run status
```

The collector makes read-only HTTPS requests, checks the actual token workspace and expiry, and refuses admin credentials. It reads published task documents through the explicit workspace/project/dataset route. Redirects, oversized bodies, duplicate rows, changed counts, missing journeys, changed requirement digests or criterion wording refuse reconciliation. Pagination is bounded to 1,000 documents; this is a refusal bound, not measured capacity. The read is an observation of the API, not a transactional Source export.

The dedicated source identity is restricted to Gitgood and expires after seven days. Its protected local material is outside tracked source. Renew/revoke through Barkpark's supported token contract; do not silently substitute the CLI admin identity. The initial integration found that the installed CLI selected its saved admin identity despite an environment token setting, so the collector uses direct authenticated API reads.

Validate a candidate snapshot before atomic replacement. Keep immutable previous/next snapshots and normalized source revision provenance under private `.gitgood/report-history/` directories. A failed fetch retains previous values and their original observation time, records the source as unavailable, and returns a nonzero result. It cannot refresh old evidence by updating a clock. A source observation older than 24 hours is stale; future timestamps are invalid.

The snapshot's requirement revision is the SHA256 of the ordered journey-to-file-digest map. Verification must additionally name its actual code candidate, criteria, outcomes and protected artifacts. A code/spec change cannot inherit approval. Release requires an actual published record tied to immutable artifacts and the accepted candidate.

## Current limits

Live implementation collection and [delivery evaluation ingestion](implementation/delivery-evaluations.md) are configured. Run `npm run verification:refresh` with the same finite workspace-bound credential to read protected text proof bytes, manifest identities, all criteria and explicit evaluator outcomes. Failed reads retain previous proof provenance without refreshing its observation time; changed or missing previously observed documents refuse. A fresh Source read cannot refresh the age of an old proof. The current collector assessment is inconclusive for complete J11. Release ingestion remains unconfigured. Current source task status is not a product release gate by itself. Full native J11 evidence attachment/access/reassessment remains separate work.

The [progress page](STATUS.md), full Gantt and detailed journey map are generated from catalogs and this observed snapshot. Their assessment is frozen at the saved evaluation time; use `npm run status` for current age checks. The compact illustration at the top of the README explains scope and delivery order, without claiming completion. Unattended collection, deduplicated alerts and automatic publishing are not yet established. The checked-in maintenance workflow remains disabled until those contracts and remote execution are verified. Required GitHub CI runs on the measured isolated ephemeral Linux runtime; exact proposed and integrated revisions need their actual job conclusions. Local results do not waive those checks. See [the native CI boundary](implementation/isolated-ci.md).
