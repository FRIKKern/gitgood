# Isolated development CI

## Purpose and acceptance

GitHub-hosted jobs currently stop before executing any steps because of account billing. Required checks remain required. Investigate a disposable self-hosted Ubuntu 24.04 guest without changing billing, purchasing infrastructure, or weakening a check. This is infrastructure for developing the private repository; it does not add hosted CI execution to Gitgood's product scope.

The initial branch-only dispatch probe must execute as a real GitHub job. Its job ID, candidate, actual environment and conclusion belong in private evidence. A successful probe establishes dispatch only; it does not establish the planning or forge checks. Keep the current required workflows until their actual equivalent jobs have executed successfully.

## Isolation

Use a fresh overlay over the verified Ubuntu image, separate SSH keys, separate networking and a new instance identity. The guest has four virtual CPUs, 8 GiB memory and a 48 GiB disk. It shares the physical Windows host and a WSL parent with development infrastructure. Emulation and those shared resources are explicit limits; this is not an independently operated cloud runner.

Do not mount host directories or transfer native application credentials, Source credentials, production databases, Git stores or recovery keys into the guest. Run the GitHub worker as the non-root `ci` account. Administrative access inside this disposable guest is limited to installing development dependencies; it is not access to the application's host. Keep runner diagnostic files private. Do not upload runner configuration, credentials or raw diagnostics as ordinary verification artifacts.

Register with a short-lived repository registration token supplied through `ACTIONS_RUNNER_INPUT_TOKEN`, never a command-line argument or tracked configuration. Use an ephemeral runner that accepts one job and automatically deregisters. Before reusing a name or stopping a process, check the exact owned runner ID or process creation identity. Preserve evidence and recovery resources. A stopped or occupied runner must not be reported as available capacity.

## Current status

The dispatch probe and guest procedure are an investigation. Neither GitHub dispatch nor equivalent required checks are verified yet. No application release, production Cloud deployment or automatic runner fleet is established by this work.

## Primary references

- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) currently lists self-hosted runner usage as free. Hosted artifact/cache charges and account restrictions are separate.
- [GitHub's postponed self-hosted pricing change](https://github.blog/changelog/2025-12-16-coming-soon-simpler-pricing-and-a-better-experience-for-github-actions/) clarifies the earlier pricing announcement.
- [Adding self-hosted runners](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners) documents repository registration and its one-hour token lifetime.
- [Runner reference](https://docs.github.com/en/actions/reference/runners/self-hosted-runners) documents Docker for Linux service containers, ephemeral single-job assignment and diagnostic preservation.
- [Runner command settings](https://github.com/actions/runner/blob/main/src/Runner.Listener/CommandSettings.cs) implements masked `ACTIONS_RUNNER_INPUT_TOKEN` environment input. Verify the installed runner's actual version and publisher digest before execution.
