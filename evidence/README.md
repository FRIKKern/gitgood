# Evidence contract

A manifest supports an identified criterion, not an entire product by implication. Required fields for future real manifests: journey/criterion IDs, spec revision, code commit, dependency versions, environment, fixture, reproduction command, outcome, producer, observation time, artifact references, and agent verifier/evaluation when required. Acceptance fields mean evidence evaluation under AUTONOMY.md, not human approval.

Keep binary artifacts outside Git and retain the manifest. Access to private code/evidence must remain restricted.

evidence/status.json contains the current reporting snapshot. It begins unconfigured. Task work state comes from the ledger source; verification from the evidence source; published versions from the releases source. Each source carries its real observedAt and status. All journey records require a source reference; verified records additionally require passed acceptance and matching code/spec revision. Released records require matching publication identity and passing release acceptance.

This skeleton validates reporting shape and refuses invented success without references, but it cannot verify external artifact truth or signatures. Those checks and authenticated fetchers belong to S09/S16. Do not hand-edit the snapshot to make progress appear green.

Freshness is independent from recorded result. Invalid or changed revisions become stale; unavailable/unconfigured sources become unknown. A last-known result can be retained with its observation time, but release acceptance requires current input.

The planning snapshot's revision is planning-2026-10-07. When implementation starts, replace it with the actual candidate commit and a spec digest. No product evidence exists in the initial snapshot.
