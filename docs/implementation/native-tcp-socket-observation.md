# Targeted original TCP socket observation

Full production staging must retain its original database client and socket
checks within the existing response deadline. The shared socket observer now
asks the kernel for the fixed loopback TCP connection instead of reading every
TCP row in the network namespace. Installed timing and complete staging remain
unverified until exact hosted evidence passes.

`native_ownership_database.py` sends a fresh individual `SOCK_DIAG_BY_FAMILY`
request through a new, owned `NETLINK_SOCK_DIAG` socket. The request selects only
IPv4 TCP and the already admitted loopback client/server ports. It requests no
dump, multicast, optional extension or destructive command. This transport owns
no SQL session or writer lease and does not replace the original database client.

The reply must come from kernel netlink address zero and match the fresh request
sequence and original local netlink port. A single complete message of at most
4096 bytes must report an established IPv4 socket, both exact loopback addresses
and ports, the expected UID, no bound device and a nonzero inode. Error,
multipart, truncated, concatenated, foreign-sender and ancillary replies refuse.
Additional kernel attributes are fully framed within a 64-attribute bound;
duplicates and malformed lengths/padding refuse. Their values grant no authority.
The observation transport has a two-second bound and always closes; failure does
not fall back to a table scan or cached identity.

Both before the query and after process descriptor verification, the original
process network namespace must equal the caller's current namespace. The returned
inode must appear in exactly one of the original process's at most 4096
descriptors; that descriptor's target is checked again. Existing ordinary and
Root admission, original PID/birth checks, SQL nonce/backend checks, advisory
exclusion, protected configuration and permanent observer poisoning remain in
their callers. Socket identity is freshly queried on every call and the returned
five-field identity shape is unchanged.

Nine parser/transport tests pass with explicit transport stand-ins. Five Linux
tests require actual kernel queries, original descriptor identity, closure,
duplicate descriptors, foreign UID/endpoint refusal and namespace refusal. The
positive case repeats twenty fresh queries and records only their count and wall
time. These portable tests do not establish the real kernel ABI, installed
performance, Root writer custody or complete staging; the hosted Root test step
and full systemd/PostgreSQL proof must establish those on the current candidate.

The interface follows the [Linux socket diagnostics ABI](https://man7.org/linux/man-pages/man7/sock_diag.7.html)
and its [kernel structure definitions](https://github.com/torvalds/linux/blob/master/include/uapi/linux/inet_diag.h).
The [kernel TCP procfs documentation](https://docs.kernel.org/networking/proc_net_tcp.html)
identifies TCP diagnostics as the replacement for full TCP table observations.
