# Isolated development CI

## Purpose and acceptance

GitHub-hosted jobs currently stop before executing any steps because of account billing. Required checks remain required. Investigate a disposable self-hosted Ubuntu 24.04 guest without changing billing, purchasing infrastructure, or weakening a check. This is infrastructure for developing the private repository; it does not add hosted CI execution to Gitgood's product scope.

The initial branch-only dispatch probe must execute as a real GitHub job. Its job ID, candidate, actual environment and conclusion belong in private evidence. A successful probe establishes dispatch only; it does not establish the planning or forge checks. Required job names and test behavior remain intact while their runner selection changes to the measured isolated guest. Integration still requires those actual jobs to pass; dispatch alone cannot replace them.

## Isolation

Use a fresh overlay over the verified Ubuntu image, separate SSH keys, separate networking and a new instance identity. The guest has four virtual CPUs, 8 GiB memory and a 48 GiB disk. It shares the physical Windows host and a WSL parent with development infrastructure. Emulation and those shared resources are explicit limits; this is not an independently operated cloud runner.

Do not mount host directories or transfer native application credentials, Source credentials, production databases, Git stores or recovery keys into the guest. Run the GitHub worker as the non-root `ci` account. Administrative access inside this disposable guest is limited to installing development dependencies; it is not access to the application's host. Keep runner diagnostic files private. Do not upload runner configuration, credentials or raw diagnostics as ordinary verification artifacts.

Run the guest emulator under its own non-login host identity. Its output firewall rejects new IPv4 and IPv6 connections to loopback, private, link-local and multicast destinations. Permit only the actual configured resolver on DNS port 53 and replies to established connections. This protects development services reachable through the emulator's host gateway, including passwordless fixture databases. Do not apply these rules to another emulator or account. Verify denial against a listening parent-host canary and database-port TCP probes, plus ordinary certificate-validated public GitHub HTTPS, before dispatching repository code. Preserve the previous disk and diagnostics when changing the isolation boundary.

Register with a short-lived repository registration token supplied through `ACTIONS_RUNNER_INPUT_TOKEN`, never a command-line argument or tracked configuration. Use an ephemeral runner that accepts one job and automatically deregisters. Before reusing a name or stopping a process, check the exact owned runner ID or process creation identity. Preserve evidence and recovery resources. A stopped or occupied runner must not be reported as available capacity.

A repository-scoped just-in-time registration is also supported. Supply `encodedJitConfig` through masked `ACTIONS_RUNNER_INPUT_JITCONFIG`; do not put it in arguments, tracked files or ordinary artifacts. Its decoded configuration and credential files remain private. Verify the installed runner's actual input and decoding contract rather than inferring JSON field names or types.

## Current status

### Native execution boundary

The emulated `Nehalem` guest at 0af6246 completed planning but passed only 68 of 155
backend tests, with process-start and database timeouts. Its failure remains retained.
A native Linux rootless OCI alternative now uses a dedicated non-login host identity,
private image storage and an owned 4 CPU / 8 GiB cgroup allocation. It shares the parent
kernel and physical host; it does not establish VM or independent cloud isolation.

The runner executes as `ci` inside a separate container filesystem and PID/network
namespaces. Container root maps to the dedicated unprivileged host identity through
subordinate UID/GID mappings. Nested Docker requires capabilities in that user namespace;
never substitute a rootful privileged container. Product files, Windows mounts, Source
credentials, application data and recovery materials are absent. The sole extra bind
mount exposes the newly owned CI cgroup subtree for disposable job resources. It must
not expose the host's complete cgroup hierarchy or application runtime groups.

Apply destination-denial rules only to the dedicated host identity before public
network use. Retain the actual resolver exception and established replies. Rootless
networking has host-loopback forwarding disabled. Before JIT registration, check actual
rootless execution, filesystem/PID separation, a reachable parent-host canary with
positive control and zero container connections, private/metadata destination denial,
certificate-validated public GitHub HTTPS, owned cgroup movement and a real nested
PostgreSQL service start/readiness/stop under `ci`. Docker daemon availability alone is
insufficient. Preserve stopped containers and private diagnostics until actual GitHub
results and evidence custody are confirmed. Do not upload runner credentials or raw
configuration with ordinary artifacts.

The [build recipe](../../tools/ci/native-runner.Containerfile) pins the Ubuntu base digest
and verifies the published runner package checksum. Signed Ubuntu package updates mean
new builds can differ: record their resulting image identity and runtime versions.
The observed v3 image was `7447a74b4c0486f6dc6e0ee2c3bded325b172848bdaa21d931e2e1b1f6dc71f4`;
this checked-in recipe additionally installs OpenSSH clients and is not that observed
image. The workflow installs and verifies its required SSH tools independently.

At 9392a31, actual native planning job 113725734694 passed and forge job 113725734307
passed 171 of 172 backend tests. The remaining test refused because `ssh-keygen` was
absent from the minimal image. No assertion or timing target was relaxed. The failed
run and native isolation/service-container proof have private digest-checked archives.
At f3d6324, planning job 113734921544 passed. Forge job 113734921747 passed all 172
backend checks, nine database recovery checks and the deliberate crash/reconciliation
loops, then failed the populated upgrade experiment. Its one-step downgrade now
reached a newer empty migration instead of the membership audit safeguard. The
experiment must target the protected migration explicitly, verify retained audit
records, and restore the current schema before its fresh-process check. Browser and
copied-production steps did not execute. This failed result remains evidence; complete
required CI and a product release remain unverified.

At 8083885, planning passed. Forge job 113744018069 passed all 172 backend
checks, recovery/crash verification, the corrected populated upgrade/fresh-process
experiment and web checks. The operation suite passed 23 of 24 checks; export
inspection refused the installed `pg_restore` version. The unpinned PostgreSQL 18
APT client package had advanced to 18.6 while recovery requires exact 18.4 tools.
Preserve that failure rather than accepting an unverified version combination.

The revised workflow builds the official PostgreSQL 18.4 source archive after
checking its [publisher SHA-256](https://ftp.postgresql.org/pub/source/v18.4/postgresql-18.4.tar.gz.sha256).
It installs server and clients into the job's private workspace, initializes an
owned UTF8/libc/C.UTF-8 cluster with a synthetic password, binds only loopback and
checks actual server/tool versions. The server and verifier now use the same
Ubuntu 24.04 libc, as required by the native recovery locale profile. An independently
versioned distribution client or Debian service container cannot establish that
profile. All application, operation, interruption and full copied-production
checks remain required; always stop only the job's own native cluster. A fresh
credential-free native OCI probe built this exact installer, verified all three
18.4 version strings, initialized and authenticated the native cluster, observed
Ubuntu libc, and stopped it cleanly. Its owned container and private build log are
preserved. This proves environment preparation; actual required-job conclusions
must still pass before integration.

JIT settings enter the container through private stdin, then masked listener environment
input. Keep them out of arguments and ordinary evidence. Each fresh worker consumes
one job and deregisters. Use GitHub's actual job conclusion for success: zero listener
or container exit status only establishes worker termination. No persistent fleet is
installed by these experiments.

Dispatch is verified for the recorded probe below. Equivalent required checks remain under investigation. No application release, production Cloud deployment or automatic runner fleet is established by this work.

The measured guest boundary denied connections to a listening parent-host canary and both development database ports, with zero canary connections. Ordinary certificate-validated public GitHub HTTPS returned 200. The publisher's v2.338.0 Linux runner asset digest was verified before installation.

Legacy registration attempts timed out. Repository JIT registration subsequently succeeded, but the listener remained offline and stalled during startup before dispatch. Its version command and direct public HTTPS probes succeeded. Keeping SSH open, disabling diagnostic pipes and testing managed hardware-intrinsic/ReadyToRun settings did not establish a working listener. The startup cause remains unresolved; absence of migrated settings is a normal SDK fallback and is not evidence of a configuration failure.

Probe run 37875809681 at candidate 2bc8de87aac918b950679a7030d7a333a0ee2825 executed zero steps. After rechecking its exact queued job and offline/non-busy runner identity, the owned listener process group was stopped using its recorded creation identity. Twenty diagnostic files were copied into a private digest-checked guest archive, the owned registration was removed, and cancellation of the queued probe was requested. The guest filesystem and original diagnostics remain preserved. These observations establish neither equivalent CI nor a passing candidate.

A fresh overlay preserved the original disk and diagnostics while changing the emulated CPU from `max` to the narrower `Nehalem` feature profile. The old, already-deleted registration then progressed through session creation and received the expected deleted-registration response. This isolates a useful environment difference, but does not identify a runtime or emulator root cause.

The new guest again refused the listening parent canary and both database ports, with zero canary connections, while certificate-validated GitHub HTTPS returned 200. Fresh ephemeral runner 24 used the digest-verified v2.338.0 publisher package and accepted job 113676595234 in probe run 37881424975, attempt 2, at candidate beff5de0dc075070626de30587908525332d91d3. All three actual steps passed, the listener exited zero, and GitHub removed the registration. Private run/job/network receipts have digest readback. This is dispatch proof for that candidate, not passing planning/forge checks.

Planning and forge now target the same isolated runner labels with bounded job timeouts. The forge job explicitly enables the PostgreSQL locale check and full copied-production offline recovery. Its production harness enters a newly owned cgroup parent; native and maintenance children must be empty after verification. Fresh repository JIT workers are registered for individual jobs. Availability remains dependent on an active provisioner; no persistent runner fleet is claimed.

Recovery requires the PostgreSQL 18 client utilities alongside the existing 18.4 service container. The job installs the client package from the [official signed Ubuntu repository](https://www.postgresql.org/download/linux/ubuntu/) and records the actual dump-tool version. It does not install another database server or copy application runtime credentials into the guest.

At candidate bd172519f8e1c846247427739569346ab9c08f8d, actual planning job 113678211665 passed. Forge job 113678211980 initialized its PostgreSQL service and checked out the repository, then refused during `setup-beam`: self-hosted jobs do not supply the `ImageOS` value that the installer requires. No forge tests executed. Retain that failed result; it does not establish equivalent CI. The workflow now declares `ImageOS: ubuntu24` as required by the [pinned installer's self-hosted contract](https://github.com/erlef/setup-beam/blob/54075bcc5e249e4758d363f27d099f55d843f124/README.md#self-hosted-runners) and first verifies the actual Ubuntu 24.04 x86_64 platform. Actual required jobs on the repaired candidate still need to pass.

At candidate 9531c33295f6464ff39db7a5b21ab273f1b12e9a, planning passed again and forge job 113682284180 passed the platform check. Erlang installation advanced, but Elixir extraction refused because the minimal guest lacked `unzip`. The workflow installs `unzip` and `build-essential` from the guest's configured signed Ubuntu repositories before the installer and checks the actual compiler, make and extraction tools. Native dependencies require compilation; an installer success alone still cannot establish passing forge checks. The failed job and its diagnostics remain private evidence.

## Primary references

- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) currently lists self-hosted runner usage as free. Hosted artifact/cache charges and account restrictions are separate.
- [GitHub's postponed self-hosted pricing change](https://github.blog/changelog/2025-12-16-coming-soon-simpler-pricing-and-a-better-experience-for-github-actions/) clarifies the earlier pricing announcement.
- [Adding self-hosted runners](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners) documents repository registration and its one-hour token lifetime.
- [Runner reference](https://docs.github.com/en/actions/reference/runners/self-hosted-runners) documents Docker for Linux service containers, ephemeral single-job assignment and diagnostic preservation.
- [Runner command settings](https://github.com/actions/runner/blob/main/src/Runner.Listener/CommandSettings.cs) implements masked `ACTIONS_RUNNER_INPUT_TOKEN` environment input. Verify the installed runner's actual version and publisher digest before execution.
- [Repository JIT configuration](https://docs.github.com/en/rest/actions/self-hosted-runners#create-configuration-for-a-just-in-time-runner-for-a-repository) documents repository registration and its encoded configuration response.
- [Installed runner input handling](https://github.com/actions/runner/blob/v2.338.0/src/Runner.Listener/CommandSettings.cs) and [configuration decoding](https://github.com/actions/runner/blob/v2.338.0/src/Runner.Listener/Runner.cs) record the inspected v2.338.0 contract.
