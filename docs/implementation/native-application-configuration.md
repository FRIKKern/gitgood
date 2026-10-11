# Native application configuration

The native ownership startup now checks the actual application settings before
opening its SQL lease or publishing ownership. A correctly fenced lease for one
database cannot authorize a separately configured Repo, listener or credential.
This is required integration under decision 0018; `Gitgood.Application` still
refuses the native profile pending installed startup and functional verification.

## Protected source and actual settings

`NativeOwnershipInputs.read_application/2` reads the fixed Root ownership seal,
private installation configuration and fixed generation admission seal. The
generation file must match the exact raw digest and fixed path observed by the
original monitor. Its closed canonical protocol, installation, durable binding,
database and service-definition digest must agree. Its five distinct executable
paths supply the expected Git/Python runtime paths. Neither caller paths nor
environment variables supply that authority.

`NativeApplicationConfiguration.check/3` compares that protected configuration
with both the relevant process environment and actual application configuration.
It creates no directory, socket, database connection or worker. Invalid values
produce only a constant error. Configuration and credentials remain internal;
the startup owner's retained state contains neither them nor connection options.

The configuration checks require the complete bounded private-team profile:
storage and installation identity; native database URL; cookie/proxy keys;
HTTPS public/web origins; local API routing; SSH identity, key directory and
ports; optional Barkpark origin/encryption key/private CA; and all resolved
application values. Duplicate or extra consequential Repo/endpoint options
refuse. The Repo URL must equal the protected URL, its pool size is ten and
sensitive connection errors are disabled. Alternate sockets, callbacks,
credentials and transport overrides cannot enter through its configuration.

Native HTTP and SSH listeners use distinct unprivileged ports, and the HTTP
listener binds only loopback. The public SSH port may be 22; external routing
must be independently verified. Native runtime requires its actual listener to
be enabled; maintenance requires it disabled. The runtime configuration explicitly
records that boolean and the configured public HTTPS port. Git and Python paths
must match the observed Root seal. Recovery-only flags and unsupported process
controls refuse; the complete controller must supply fixed commands separately.

The established protocol-1 configuration format remains unchanged. This does
not convert any legacy operation or relax its resource checks. Root/private
file reads retain their existing ownership, mode, single-link, descriptor/path
and parent checks. Their Elixir timestamp precision remains seconds; the original
protected monitor still supplies full live filesystem custody. This startup
comparison alone does not establish live settings custody or effect authority.

## Verification and remaining integration

Verification covers mismatched environment and resolved settings, missing or
unknown fields, secret overrides, executable changes, callback/Repo options,
listener changes, maintenance/runtime separation, optional source settings,
canonical generation bytes, substituted generation identities and independently
rehashed invalid seals. It evaluates the actual production runtime configuration
without opening services, and separately reads actual Root/private files as an
ordinary installation account. Private canaries must remain absent from output.

The service observation and admitted database in boundary fixtures are explicit
stand-ins. These cases do not prove actual systemd admission, a protected
successful claim, database authentication/exclusion, complete BEAM shutdown,
installed artifact identity or functional readiness. Native application wiring,
controller dispatch/reconciliation, full required CI, owned-kernel verification,
allocator/Cloud deployment and all complete journeys remain required.
