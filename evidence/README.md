# Evidence contract

A manifest supports an identified criterion, not an entire product by implication. Required fields for future real manifests: journey/criterion IDs, spec revision, code commit, dependency versions, environment, fixture, reproduction command, outcome, producer, observation time, artifact references, and agent verifier/evaluation when required. Acceptance fields mean evidence evaluation under AUTONOMY.md, not human approval.

Keep binary artifacts outside Git and retain the manifest. Access to private code/evidence must remain restricted.

evidence/status.json contains the current reporting snapshot. It begins unconfigured. Task work state comes from the ledger source; verification from the evidence source; published versions from the releases source. Each source carries its real observedAt and status. All journey records require a source reference; verified records additionally require passed acceptance and matching code/spec revision. Released records require matching publication identity and passing release acceptance.

The [delivery evaluation collector](../docs/implementation/delivery-evaluations.md) reads explicit assessments and bounded protected text proofs from Source. It verifies byte checksums, identities, all criterion outcomes, latest sequence, proof age and previously observed manifest custody. It does not reexecute commands or cryptographically attest their truth; evaluators must actually inspect retained results. Binary/external artifact providers and release ingestion remain separate S09/S16 work. Do not hand-edit the snapshot to make progress appear green.

Freshness is independent from recorded result. Invalid or changed revisions become stale; unavailable/unconfigured sources become unknown. A last-known result can be retained with its observation time, but release acceptance requires current input.

The planning snapshot's revision is planning-2026-10-07. When implementation starts, replace it with the actual candidate commit and a spec digest. No product evidence exists in the initial snapshot.
