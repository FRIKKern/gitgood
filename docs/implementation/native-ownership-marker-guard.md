# Original ownership marker custody

`NativeOwnershipMarkerGuard` observes the original storage and ownership-directory
descriptors, all retained record bytes and eight-field filesystem fingerprints,
and the original mode-specific marker. It performs no creation, repair, publication,
database connection, lease acquisition, process signal or owner adoption.

Capture requires the expected closed ownership record and its canonical marker to
already exist. Every observation brackets record and marker reads with unchanged
directory identities, layouts and fingerprints. A nonblocking shared lock on the
original ownership-directory inode excludes the normal marker publisher during an
observation. The guard releases this lock between observations; an identical live
publication retry preserves its capture. A competing writer during observation
refuses instead of waiting or accepting a changed capture.

Original descriptors remain open for the guard lifetime. Changes to record or
marker bytes, metadata, inode, links, permissions, directory identity or layout,
or the appearance of an opposite-mode marker refuse. The guard closes its own
descriptors and poisons itself after one refusal. Restoring the original file does
not resume it. Explicit close is also terminal and idempotent. Uncertain files stay
untouched; no absence or replacement authority follows from a filesystem record.

Ten focused tests execute against real ordinary-user Linux files and directory
locks. They cover repeated read-only checks, identical publication retry, same-byte
inode replacement, in-place same-byte rewrite, permission loss followed by repair,
preserved unknown/other-mode files, storage and ownership-directory replacement,
actual exclusive-lock contention, replacement during observation and missing-marker
capture without repair. These are filesystem custody checks. Fixed protected helper
attachment, independently admitted live service/backend checks and whole-BEAM loss
behavior are required before this can be wired into native startup.

The installation profile remains unavailable. Prior-owner reconciliation, controller
admission and lifecycle interruption proofs remain required as described in
[native ownership publication](native-ownership-publication.md).
