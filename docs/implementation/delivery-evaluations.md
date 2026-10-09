# Delivery verification ingestion

This work implements the repository's S09/S16 reporting contract. Barkpark owns
the private delivery evaluations; Gitgood continues to own its product evidence
records. These evaluations assess retained delivery proofs against the repository
journeys. They do not create native criterion evidence or application releases.

The collector reads published `gitgood_verification` documents through the
existing finite Gitgood workspace identity. Each evaluation binds one journey,
all its criteria, exact code and requirement identities, actual observation times,
producer and evaluator, reproduction commands, environment and retained protected
text proofs. Proof bytes are bounded, checksum-verified and never executed. No
external artifact URL or credential can come from the evaluation document.

The latest declared sequence governs each journey. Failed, inconclusive, missing,
stale and unavailable results remain distinct; a newer failed or stale evaluation
cannot fall back to an older pass. A refresh records an observation of Source and
does not renew proof age. Changed code/spec identity remains stale. A failed read
retains prior provenance and observation time without satisfying current gates.
Previously observed documents must remain present with the same manifest digest;
changed or removed protected proofs make the source unavailable. Reassessment
appends another document and sequence instead of overwriting historical bytes.

An authenticated evaluator declaration is an explicit agent assessment, not an
automatic reexecution or independent cryptographic attestation. The collector
checks protected byte integrity and identity, not the truth of a command's claimed
execution. Evaluators must actually inspect retained results under QUALITY.md.

Live ingestion is configured after the actual finite Gitgood identity read and
atomic create/publish experiment. Frozen `01d2c2e` collector bytes read back the
protected published assessment and its 7,258-byte proof with manifest SHA256
`92e4010c66025dccaba38595d6b2b029d81001aae642fe465256d4709791d823`.
Anonymous access to that exact document refused. An actual unauthorized refresh
returned 401, kept prior result bytes and observation time, and made verification
unavailable; restoring the scoped identity recovered the same inconclusive record.
The seven live checks supplement 33 planning/collector checks, including real
loopback denial, redirects, changed/missing protected proofs and changed revisions.

The assessment explicitly remains inconclusive for complete J11. Product browser,
native criterion creation/access/reassessment, binary/external artifact providers,
release ingestion and unattended collection remain separate work.
