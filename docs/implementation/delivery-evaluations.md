# Delivery verification ingestion

This work implements the repository's S09/S16 reporting contract. Barkpark owns
the private delivery evaluations; Gitgood continues to own its product evidence
records. These evaluations assess retained delivery proofs against the repository
journeys. They do not create native criterion evidence or application releases.

The collector will read published `gitgood_verification` documents through the
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

The Source configuration remains disabled until actual authenticated read/write,
protected proof access, byte integrity, changed-revision handling and failed-read
preservation are demonstrated. Product J11 browser/access/reassessment acceptance,
binary/external artifact providers and release ingestion remain separate work.
