# Bounded pilot workload

## Measurement contract

This is the first measurement profile for M4, recorded before running measurements. It is a target and experiment contract, not a capacity claim. Candidate identity, clean tracked source, runtime versions, fixture manifest, commands, elapsed times and raw samples belong in the private receipt. Failed targets remain visible; changing a target requires a recorded rationale and new measurements.

Use a disposable copied-production installation with PostgreSQL, native Gitgood, the production web service and the actual TLS edge. Preserve private data and runtime logs. A production fixture with tiny repositories does not establish these performance targets.

## Repository and actors

- One deterministic SHA1 repository: 2,000 UTF-8 files of exactly 4,096 bytes in 20 directories, 500 main commits, and 10 additional work-branch commits. Each later commit replaces two files with independently derived content. The final review spans 20 changed files. Record Git object, bundle, working-tree and bare-store sizes; compression is observed, never assumed.
- One separate large UTF-8 file, a NUL-containing binary file and a diff beyond the documented 262,144-byte browse bound are functional refusal fixtures, not part of the supported latency sample.
- One owner, a second writer, eight distinct read-only actors and an outsider. Reader permissions must come from native membership and current credentials. Owner credentials cannot impersonate concurrent readers.
- One bounded import operation at a time. No hosted CI or agent execution is included. Larger repositories, additional installation workers, LFS hosting and public multi-tenant workloads need separate profiles.

## Environment and cache

Record actual host/guest CPU model and allocations, memory, storage backing, operating system/kernel, filesystem, database locale, PostgreSQL version, Git/Elixir/OTP/Node versions, supervisor limits and all concurrent background services. The initial isolated reference target is four virtual CPUs and 4 GiB guest memory. Emulation and a shared physical host must remain explicit limitations.

Measure two network profiles separately: local TLS on the reference guest and an explicitly configured 50 ms round-trip client link. Unconfigured network shaping stays unmeasured. Never substitute loopback results for a remote-team latency claim.

The first request after service restart is a **process-cold, filesystem-cache-uncontrolled** observation. Warm samples follow ten recorded warmups. Do not call a process restart a cold storage cache or drop shared-host caches. Record both phases separately.

## Targets fixed before measurement

| Operation | Samples and workload | Initial target |
|---|---|---|
| Warm branches, directory, 4 KiB file and bounded review diff | 100 samples per route, eight independently authorized concurrent readers | P95 <= 1,500 ms per route on local TLS; no 5xx or wrong-content response |
| Process-cold initial browse | Ten service restarts; original SHA and content checked each time | P95 <= 5,000 ms on local TLS |
| Browser repository/file/review interaction | 30 samples per interaction, production assets, eight readers | P95 <= 2,500 ms on the configured 50 ms RTT profile |
| Activity visibility after a recorded write | 30 independently identified write-to-visible observations | P95 <= 6,000 ms, no actor or event identity drift |
| Fixture full-bundle import | Five new repositories, sequential operations, checksum and all refs checked | Each completes <= 120 seconds; retry creates no additional operation |
| New HTTPS clone and incremental fetch | Five verified clones and 30 sequential fetches | Clone <= 60 seconds; warm fetch P95 <= 5,000 ms on local TLS |
| Runtime resource use | Sample service process trees, database connections, cgroup counters and owned child counts during all workloads | Guest working set <= 3 GiB; no OOM, sustained unbounded queue, leaked subprocess or leftover Git lock |

Percentiles use sorted raw samples and the nearest-rank definition. Keep minimum, median, P95, maximum, count and every failed observation. A route with failed responses cannot pass by excluding them from its percentile. These thresholds cover only this defined profile; refusal caps and integration test durations are not measured capacity.

## Acceptance still pending

First prove fixture identity and authorized correctness, then execute measurements against a clean candidate. Permission denial must remain correct under load. Record actual limits rather than increasing quotas to conceal a failure. M4 also needs the complete daily browser workflow, keyboard/access behavior and all relevant journey criteria; this profile alone cannot verify M4, managed Cloud or release readiness.
