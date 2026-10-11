# Architecture decisions

[Documentation home](../README.md) · [Architecture overview](../architecture.md) · [Implementation reference](../implementation/README.md)

Read these records for the reasons behind a design and its boundaries. The **D01–D09 records** frame the original questions and experiments; the **numbered design records** capture specific choices. Each record owns its status and scope. An accepted design still needs implementation and current acceptance evidence.

## Original questions and experiments

| Record | Question or responsibility |
|---|---|
| [D01 — Governance](D01.md) | Private ownership, first-release scope and delegated agent authority |
| [D02 — Identity](D02.md) | Local accounts, bootstrap and identity across Gitgood, Cloud and Barkpark |
| [D03 — Barkpark reuse](D03.md) | Which supported capabilities Gitgood can adopt |
| [D04 — Git transport](D04.md) | Native Git hosting and its compatibility boundary |
| [D05 — Recovery](D05.md) | Reconciling Git and database changes after interruption |
| [D06 — Packaging](D06.md) | Reproducible artifacts and the Cloud runtime contract |
| [D07 — Backup](D07.md) | Coordinated backup and replacement-host restoration |
| [D08 — Review and merge](D08.md) | Review, check and merge rules |
| [D09 — Capacity and quality](D09.md) | Measured pilot workload and operational targets |

These are enduring questions, not a live task board. D01 records resolved authority; other experiments can retain open cross-system or acceptance work after a narrower design has been chosen. Follow each record's linked decision and evidence, and use the [progress snapshot](../STATUS.md) for reporting context.

## Product and collaboration design

| Record | Design |
|---|---|
| [0001 — Native forge](0001-native-forge.md) | Own the Elixir backend and use standard Git |
| [0002 — Local identity](0002-local-identity.md) | Standalone accounts, sessions and team membership |
| [0003 — Smart HTTP](0003-native-http-transport.md) | Bounded native HTTPS Git transport |
| [0004 — Review, checks and merge](0004-review-check-merge-semantics.md) | Current-policy review and merge semantics |
| [0005 — SSH](0005-native-ssh.md) | SSH identity and transport |
| [0006 — Import](0006-offline-bundle-import.md) | Supported full-bundle repository import |
| [0007 — Private releases](0007-basic-private-releases.md) | Release records and transactional assets |
| [0008 — Discovery](0008-private-discovery.md) | Search, activity and access boundaries |
| [0009 — Barkpark links](0009-supported-barkpark-links.md) | Independent permissions and linked source records |
| [0010 — Paper return links](0010-journaled-paper-return-links.md) | Durable reverse-link publication and retry |

## Installation and lifecycle design

| Record | Design |
|---|---|
| [0010 — Single-host operation](0010-single-host-releases.md) | Release operation on one host |
| [0011 — Isolated retirement verification](0011-isolated-retirement-verification.md) | Check an independent restored copy before removal |
| [0012 — Retained usability](0012-post-removal-retained-usability.md) | Verify retained material after original resources are removed |
| [0013 — Retirement execution](0013-fixed-native-retirement-executor.md) | Fixed removal stages and recovery |
| [0014 — Upgrade commands](0014-fixed-native-upgrade-commands.md) | Upgrade, compatible recovery and forward repair |
| [0015 — Owner bootstrap](0015-installation-owner-bootstrap.md) | Durable first-owner creation without resetting later access |
| [0016 — Initial enrollment](0016-native-initial-enrollment.md) | Responsibility for the first installation |
| [0017 — Initial lifecycle](0017-native-initial-lifecycle.md) | Installation stages and the first working baseline |
| [0018 — Service supervision](0018-native-supervision-generations.md) | Host supervision and changing resource generations |

The two historical `0010` filenames identify different decisions; both paths remain stable. Link the full filename when referring to either record.

## Recording another decision

Use the [decision template](TEMPLATE.md). Explain the problem, alternatives, selected boundary, supporting evidence and remaining uncertainty. Keep reproduction details in the linked [implementation reference](../implementation/README.md), and add the new record to this index.

Agents resolve decisions and evaluate evidence under [AUTONOMY.md](../../AUTONOMY.md); these records do not create a human approval queue.
