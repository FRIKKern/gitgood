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

Dispatch is verified for the recorded probe below. Equivalent required checks remain under investigation. No application release, production Cloud deployment or automatic runner fleet is established by this work.

The measured guest boundary denied connections to a listening parent-host canary and both development database ports, with zero canary connections. Ordinary certificate-validated public GitHub HTTPS returned 200. The publisher's v2.338.0 Linux runner asset digest was verified before installation.

Legacy registration attempts timed out. Repository JIT registration subsequently succeeded, but the listener remained offline and stalled during startup before dispatch. Its version command and direct public HTTPS probes succeeded. Keeping SSH open, disabling diagnostic pipes and testing managed hardware-intrinsic/ReadyToRun settings did not establish a working listener. The startup cause remains unresolved; absence of migrated settings is a normal SDK fallback and is not evidence of a configuration failure.

Probe run 37875809681 at candidate 2bc8de87aac918b950679a7030d7a333a0ee2825 executed zero steps. After rechecking its exact queued job and offline/non-busy runner identity, the owned listener process group was stopped using its recorded creation identity. Twenty diagnostic files were copied into a private digest-checked guest archive, the owned registration was removed, and cancellation of the queued probe was requested. The guest filesystem and original diagnostics remain preserved. These observations establish neither equivalent CI nor a passing candidate.

A fresh overlay preserved the original disk and diagnostics while changing the emulated CPU from `max` to the narrower `Nehalem` feature profile. The old, already-deleted registration then progressed through session creation and received the expected deleted-registration response. This isolates a useful environment difference, but does not identify a runtime or emulator root cause.

The new guest again refused the listening parent canary and both database ports, with zero canary connections, while certificate-validated GitHub HTTPS returned 200. Fresh ephemeral runner 24 used the digest-verified v2.338.0 publisher package and accepted job 113676595234 in probe run 37881424975, attempt 2, at candidate beff5de0dc075070626de30587908525332d91d3. All three actual steps passed, the listener exited zero, and GitHub removed the registration. Private run/job/network receipts have digest readback. This is dispatch proof for that candidate, not passing planning/forge checks.

Planning and forge now target the same isolated runner labels with bounded job timeouts. The forge job explicitly enables the PostgreSQL locale check and full copied-production offline recovery. Its production harness enters a newly owned cgroup parent; native and maintenance children must be empty after verification. Fresh repository JIT workers are registered for individual jobs. Availability remains dependent on an active provisioner; no persistent runner fleet is claimed.

## Primary references

- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) currently lists self-hosted runner usage as free. Hosted artifact/cache charges and account restrictions are separate.
- [GitHub's postponed self-hosted pricing change](https://github.blog/changelog/2025-12-16-coming-soon-simpler-pricing-and-a-better-experience-for-github-actions/) clarifies the earlier pricing announcement.
- [Adding self-hosted runners](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners) documents repository registration and its one-hour token lifetime.
- [Runner reference](https://docs.github.com/en/actions/reference/runners/self-hosted-runners) documents Docker for Linux service containers, ephemeral single-job assignment and diagnostic preservation.
- [Runner command settings](https://github.com/actions/runner/blob/main/src/Runner.Listener/CommandSettings.cs) implements masked `ACTIONS_RUNNER_INPUT_TOKEN` environment input. Verify the installed runner's actual version and publisher digest before execution.
- [Repository JIT configuration](https://docs.github.com/en/rest/actions/self-hosted-runners#create-configuration-for-a-just-in-time-runner-for-a-repository) documents repository registration and its encoded configuration response.
- [Installed runner input handling](https://github.com/actions/runner/blob/v2.338.0/src/Runner.Listener/CommandSettings.cs) and [configuration decoding](https://github.com/actions/runner/blob/v2.338.0/src/Runner.Listener/Runner.cs) record the inspected v2.338.0 contract.
