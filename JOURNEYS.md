# Product journeys

A journey is a task a person must be able to complete from beginning to end, such as pushing code, reviewing a change, or restoring a lost host. These 17 specifications define the product we are building.

[Product scope](PRODUCT.md) · [Delivery roadmap](docs/ROADMAP.md) · [Progress snapshot](docs/STATUS.md) · [Documentation guide](docs/README.md)

Open a journey to see its scenarios and acceptance criteria. The first milestone tells you when work begins; it does not claim that the journey is complete. Code browsing (J04) begins at M2 and continues through M4.

| What you can do | ID | First milestone | Required for release |
|---|---|---|---|
| [Create a private repository](docs/journeys/J01.md) | J01 | M2 | Yes |
| [Clone and push over HTTPS](docs/journeys/J02.md) | J02 | M2 | Yes |
| [Use and revoke SSH credentials](docs/journeys/J03.md) | J03 | M4 | Yes |
| [Browse code and commit history](docs/journeys/J04.md) | J04 | M2 | Yes |
| [Import a supported repository](docs/journeys/J05.md) | J05 | M4 | Yes |
| [Review and update a pull request](docs/journeys/J06.md) | J06 | M3 | Yes |
| [Receive external check results](docs/journeys/J07.md) | J07 | M3 | Yes |
| [Merge under current policy](docs/journeys/J08.md) | J08 | M3 | Yes |
| [Recover an interrupted merge](docs/journeys/J09.md) | J09 | M3 | Yes |
| [Connect tasks and specifications](docs/journeys/J10.md) | J10 | M5 | Yes |
| [Attach and reassess evidence](docs/journeys/J11.md) | J11 | M5 | Yes |
| [Publish a basic release](docs/journeys/J12.md) | J12 | M4 | Yes |
| [Search and follow activity](docs/journeys/J13.md) | J13 | M4 | Yes |
| [Install through Barkpark Cloud](docs/journeys/J14.md) | J14 | M6 | Yes |
| [Upgrade and reject unhealthy releases](docs/journeys/J15.md) | J15 | M6 | Yes |
| [Restore onto a replacement host](docs/journeys/J16.md) | J16 | M6 | Yes |
| [Export archive and remove](docs/journeys/J17.md) | J17 | M6 | Yes |

Implementation, verification and release are separate. Consult the [progress snapshot](docs/STATUS.md) for their recorded states and [quality rules](QUALITY.md) for the evidence required to advance. Live work is tracked in the ledger described by the [tracking contract](docs/TRACKING.md).

Generated from [the journey catalog](docs/journeys/catalog.json). Each linked specification owns its acceptance criteria.
