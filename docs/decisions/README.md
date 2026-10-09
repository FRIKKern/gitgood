# Architecture decisions

Accepted direction: [Native forge](0001-native-forge.md) and [autonomous progression](../../AUTONOMY.md). D01 records resolved governance; technical decisions remain open until agents complete their experiments and record evidence.

| ID | Decision | Gate |
|---|---|---|
| D01 | [Repository governance and first release](D01.md) | Owner/private visibility and agent authority resolved; licensing does not block private development. |
| D02 | [Identity and bootstrap](D02.md), [standalone identity](0002-local-identity.md) | Local boundary implemented; Cloud/Barkpark experiment remains open. |
| D03 | [Barkpark reuse](D03.md) | Before adopting each capability. |
| D04 | [Native Git transport](D04.md) | Before real repository hosting. |
| D05 | [Git and database recovery](D05.md) | Before protected merge acceptance. |
| D06 | [Application packaging](D06.md) | Before accepting Cloud runtime contract; begin during M3. |
| D07 | [Consistent backup](D07.md) | Before backup/restore is called supported. |
| D08 | [Review and merge semantics](D08.md) | Before freezing J06/J08 behavior. |
| D09 | [Capacity and quality targets](D09.md) | Before M4 performance acceptance and M6 recovery acceptance; no pricing claims earlier. |

Use [the decision template](TEMPLATE.md). Agents own decision resolution and engineering, verification, and operations progression. Record the acting agent and evidence; no human assignment or sign-off is required.

[Isolated retirement verification](0011-isolated-retirement-verification.md) defines
the temporary restored copy and continuous original custody boundary. Its design
is accepted; implementation and installed verification remain open.
