# Native generation record custody

The protocol-2 record store retains closed resource-generation records beneath
an independently observed private history directory. It acquires the existing
installation-wide `.upgrade-history-lock-v1`; the caller must independently
supply the exact original lock and directory identities. It never creates a
replacement lock. Changed identity, shared permissions, aliases, hard links,
foreign installations and malformed records refuse.

Records are content-addressed canonical bytes, written to a private temporary
file, synchronized and renamed with the existing Linux no-replace primitive.
The directory is synchronized before custody returns. Exact retries reobserve
the original bytes and synchronize again, retaining the same inode. Interrupted
temporary files remain separate and retained; they never establish completion.
The bounded store validates every admitted predecessor, one initial generation,
unchanged durable digest and unique generation IDs across retained history.

This component retains records; it does not publish an active-generation pointer.
It does not independently establish the actual service, persistent continuity,
database writer exclusion, previous-owner cleanup, unfinished lifecycle
responsibility or application readiness. Those remain required before generation
publication. Retaining two possible successors grants neither successor control.

Eleven ordinary-Linux filesystem checks cover exact retention/replay, a competing
process, replaced locks and directory identities, malformed files, reused
generation IDs, missing predecessors, interrupted rename and lost synchronization
acknowledgement. Four actual interruption checks then passed with two owned
writer kills and two competing-process refusals. Four independent custody checks
verified the original locks, record bytes/inodes, retained partial and empty
bounded process groups. Those records consumed the prior actual boot scopes with
an explicitly synthetic durable digest; they establish record custody only.

The Linux suite passed 236 checks with 12 expected foreign-platform skips; all
33 planning checks passed. Ten private source records bind these results, with
review SHA256 `7270368b9603e820d51d9248fdfca8973ae5a24944820ff87e6971bcceeaa686`
and index SHA256 `2c0fb342045a14b677915d3dd417daf396e680362e91bcfc9856942bd0db730d`.
Current required CI remains separate. No complete journey or release acceptance
is established here.
