# Default native release startup

The ordinary packaged `bin/gitgood start` command can select the native runtime
through the real `Gitgood.Application` callback. This connects normal production
boot to the same ownership and schema prerequisites used by the dedicated native
runtime entrypoint. It does not establish complete installation, activation or
recovery acceptance.

## Fixed startup and failure behavior

`InstallationProfile.resolve` still observes the original supported kernel/storage
context without granting authority. Development startup keeps its existing worker
order and legacy lease behavior. The native branch accepts only normal OTP startup
with the fixed empty application arguments. Takeover, failover and caller arguments
refuse; no worker, program, callback or environment override is accepted.

`NativeRuntime.start_pending_root` is the common fixed root factory. It requires
the selected native profile and lifecycle options, then starts original ownership
before a Repo pinned to `pg_catalog, public` and the pending runtime worker. Normal
application boot calls the actual one-use activation coordinator after root init;
the dedicated permanent runtime application uses the same pending factory.
Normal boot never loads or ensures a nested application or recurses into OTP's
application controller. Success returns the newly created root only after actual
internal readiness. The permanent native root still permits zero restarts.

Activation refusal, exception or exit returns a constant failure and stops only
the exact root created by that attempt. A failed start cannot adopt or stop an
existing named supervisor. Original ownership, protected migration inventory,
actual exact public schema and per-child current checks remain mandatory before
product mutation workers and listeners. Lifecycle stage and configuration changes
invalidate the original guard; they are not converted into replacement authority.

## Installed proof and limitations

`native-default-release` is configured to run actual migration/bootstrap first,
then launch the normal packaged release without the fixture runtime evaluator or
its proof environment flags. Root independently identifies the original monitor
from the bounded native group and fixed protected entry, captures original births
and the retained ownership/marker files, and performs five read-only observations
of original owner/helper identity, held SQL/kernel lease and current readiness.
These are independent samples, not fabricated private monitor heartbeats.

The same production web/edge launcher then undergoes real verified TLS, frontend
identity/assets, owner cookie/login, anonymous denial, HTTPS Git push/readback,
strict SSH readback and revocation checks. After original helper loss, fixture
scheduling observes the ordinary permanent native release exit before asking the
public runtime component to quiesce its original groups. The controller therefore
cannot kill the native process first and manufacture permanent-application abort
evidence. All captured SQL/kernel/web/edge identities must be absent and original
responsibility and marker inodes retained. No public requests are issued during
this bounded fault observation window; production guard logic is unchanged.

Local executable checks use the real OTP callback/factory with explicit ownership
and worker stand-ins. They exercise successful activation, refusal, unexpected
outcomes and exits, existing-root preservation and rejected callback arguments.
Only a current passing installed thirteen-case artifact establishes actual normal
release startup, public behavior and original failure. Existing fixture inspect/
stage/lifecycle receipts remain synthetic metadata; repeated handoff replay is
exercised by the other component cases and is not claimed for the normal release.

Complete inspection/staging effects, lifecycle dispatch and interrupted-effect
reconciliation, activation/enrollment, complete browser journeys and reboot/
replacement-host recovery remain required for full J14/J15 acceptance.
