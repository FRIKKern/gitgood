# Native web and TLS runtime

An installed team needs its actual frontend and Git routes behind verified TLS.
`NativePublicRuntime` adds fixed Node and Caddy services to the original native
controller boundary. This component does not grant installation, enrollment or
public activation acceptance. [Normal native release startup](native-default-startup.md)
uses the same original admission prerequisites and requires its own installed proof.

## Original authority and protected artifacts

The constructor accepts only an actual `NativeOwnershipController`. It borrows
its original MainPID, installation custody, completed runtime claim, generation,
operation, private configuration and held database/kernel lease. The original
running lifecycle window must be `verify`, `activate`, `enroll` or `public_verify`.
Changed authority, owner birth, lease, marker, lifecycle head, private inputs or
service scope refuses. Publication's transient peer and empty-sibling check are
not reused after web/edge launch; current runtime checks independently observe
the original owner and held backend and retain an original marker guard.

Root supplies `/etc/gitgood/installations/<installation>/public-runtime-v2.json`.
Its closed schema binds the same installation, operation, candidate and durable
binding to the complete protected web inventory and protected direct-edge template.
The web inventory streams at most 30,000 entries, 512 MiB total and 128 MiB per
file. Every ancestor/directory/file is Root-controlled; links, writable files,
unknown filesystem types and a dirty or different build identity refuse.
Subsequent checks require the same complete names and original metadata.

Only fixed Node/srvx arguments and fixed Caddy `run` arguments can launch. There
is no public program, environment, callback or path override. The web environment
comes from the original configuration. The edge receives only its private proxy
key and fixed locale/home/data settings. Rendered configuration and logs remain
inside a new private claim directory; they never enter ordinary artifacts.
The edge uses configured DNS/IPv4 HTTPS origins and original private TLS files,
fixed loopback upstreams, disabled admin/persistent configuration and the existing
internal-route denial and client-header handling. IPv6 origin rendering is not
implemented by this component.

## Current checks and quiescence

The controller must call `check` while services run. It checks original authority,
artifacts, configuration and exact web/edge births, credentials, namespaces and
leaves. A refusal stops the original native, web and edge leaves. Cleanup requires
the still-held original controller/unit/kernel scope, and deliberately does not
require a working database or surviving BEAM. All three original directory
descriptors are captured before the first effect. Descriptor-relative cgroup
writes cannot be redirected to a replacement path. Nested groups refuse; member
counts and the ten-second cleanup interval are bounded. Private directories,
source, configuration, journal, ownership records and marker inodes remain retained.

If the controller itself exits, the independently verified systemd service's
whole-cgroup failure policy applies. This component does not implement a detached
watcher, automatic restart, interrupted-effect reconciliation or successor adoption.

## Hosted evidence and remaining gates

`native-public-runtime` is configured to exercise actual migration/bootstrap and
native runtime first, then the production launcher. Root independently captures
the web/edge births and verifies CA and hostname validation, rejection of an
untrusted issuer and wrong hostname, frontend HTML and exact packaged JavaScript,
clean web/forge identities, internal-route denial, signed owner login through
forged caller headers, secure cookie access, anonymous denial, real HTTPS Git
push/readback, strict SSH readback and session revocation. Original helper loss
must leave all captured BEAM, SQL/kernel, web/edge births and listeners absent.
The wrong-hostname probe records whether client certificate verification or a
closed server-name TLS alert refused it; Caddy can reject an unmatched SNI before
delivering a certificate. Positive CA/hostname verification always runs first,
all client validation stays enabled, and an untrusted issuer must fail client
certificate verification. Successful handshakes, connection failures and
unrelated TLS errors cannot count as negative evidence.
The production component must empty all three original leaves before fixture
cleanup, while responsibility records and marker inodes remain unchanged.

Only a current passing installed artifact establishes those outcomes. Local tests
use explicit service/database stand-ins and prove refusal/control behavior only.
The normal-release case brings the suite to thirteen cases; the nested migration fault remains last. Existing
inspection/staging/lifecycle receipts are still explicitly synthetic metadata.
Complete browser journeys, lifecycle dispatch and effect reconciliation,
public activation/enrollment and reboot/replacement-host recovery
remain required for full J14/J15 acceptance.
