# Single-host release operation

Accepted for the bounded first release, 8 October 2026.

Gitgood runs one supervised native forge OS process per installation. Distributed Erlang clustering and remote Erlang administration are outside this release contract. The packaged env.sh/env.bat templates explicitly set RELEASE_DISTRIBUTION=none for both platforms.

A real copied-production run exposed the default release node collision: concurrent owned Windows and WSL installations attempted the same gitgood@DESKTOP-IR7URDA registration, and the Linux release failed to start. Its clean migrations and 93 backend checks passed, but production readiness failed; that failed receipt is retained. Distinct HTTP, SSH, database and storage resources did not isolate the default Erlang node name.

The [pinned Elixir release contract](https://mix.hexdocs.pm/1.20.4/Mix.Tasks.Release.html#module-environment-variables) documents the default distribution mode and supported per-release environment templates. Setting none removes that automatic shared node registration and fits the actual single-host scope. No Erlang cookie or remote distribution endpoint is needed for ordinary HTTP/SSH operations.

Run lifecycle operations through the installation's OS service/process supervisor. Use release eval for offline migration/bootstrap commands. Release rpc, remote and RPC-based stop/restart are outside this operating profile; terminate and restart the owned supervised process instead. Cluster support needs a separate architecture, identity, network and recovery decision.

Revalidate clean copied Windows/Linux installations concurrently before accepting this packaging repair. Template presence alone is not runtime evidence.
