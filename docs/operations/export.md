# Native installation export

The supported Linux x64 export uses the coordinated encrypted recovery format. Stop the
complete runtime and retain its owned cgroup before calling `Gitgood.Release.export()` with
the same private configuration, archive destination and external key settings as
[offline recovery](../implementation/offline-backup.md). The command uses the existing backup lease and
refuses a running installation or another database writer. It does not remove resources.

The archive contains standard bare SHA-1 Git repositories, a PostgreSQL 18.4 custom-format
dump, SSH host material and private installation configuration. Collaboration records,
assets, operation responsibility and encrypted account/evidence custody are retained.
Barkpark owns its upstream records; the archive preserves native links and copied
provenance, not a complete export of Barkpark.

Retain the matching clean forge/web artifacts and their checksums separately. Keep the
32-byte archive decryption key under an independent access policy: losing it makes the
archive unusable. The archive itself contains application credentials and private code
and must stay outside ordinary evidence uploads. Retaining an archive also retains that
private data; deleting a running installation does not delete retained copies.

Inspect an archive without starting Gitgood or connecting to PostgreSQL:

```sh
node forge/lib/gitgood-*/priv/operations/installation-export.mjs \
  /private/export.ggbackup /private/archive-key.bin /private/inspection-scratch \
  <exact-40-character-candidate> <expected-installation-uuid>
```

Use Node 22.23.3, Git and PostgreSQL 18.4 `pg_restore` on Linux x64. The scratch parent must
be owned by the invoking identity, mode 0700 and free of symlink aliases. Inspection
authenticates the entire archive, verifies every file hash, validates configuration,
checks Git objects and exact recorded refs, and compares the dump table inventory with
its recorded database fingerprint. The receipt binds the expected installation UUID
and reports comparable file inventories plus the authenticated database descriptor
hash; a live fingerprint comparison requires writer exclusion. It emits counts and checksums without private bodies
or credentials. Its new temporary directory is removed on success or failure. The
archive, original stores and unrelated scratch entries remain intact.

Inspection is not a restoration proof: it does not execute SQL, validate restored
application behavior or measure recovery time. Follow the full restore procedure before
calling an archive usable for recovery. The bounded profile does not promise migration
to an unrelated forge or lossless restoration on a different database/locale profile.

The Linux copied-production recovery verifier executes the packaged release export
entry point, checks the packaged inspector with no database connection settings, and
then restores that same archive through the full existing functional recovery flow.
The operation test additionally uses a real bare Git repository and PostgreSQL dump,
retains unrelated scratch entries and compares live database fingerprints before/after
successful and refused inspections. These are supporting checks for J17; archive/removal
still needs the broader criteria below.

Archive/removal needs an exact resource ownership inventory, retained archive/key
custody, service exclusion, credential cleanup and repeated-operation checks against
disposable fixtures. Those removal and managed Cloud operations remain unfinished;
this export command must not be interpreted as removal authorization or completion.

Before retirement, compare the stopped installation with an existing export:

```sh
GITGOOD_RETIREMENT_INSTALLATION=<expected-installation-uuid> \
GITGOOD_RETIREMENT_CIPHERTEXT_SHA256=<independently-retained-archive-sha256> \
  forge/bin/gitgood eval 'Gitgood.Release.retirement_checkpoint()'
```

Use the same private configuration, external key and bundle settings as export.
The command takes the existing backup lease, refuses live writers, authenticates
the export and compares actual file/database fingerprints. The archive and its
key must be outside the Git, SSH and configuration roots. A wrong UUID/digest or
changed snapshot refuses without removing resources. The returned receipt is a
point-in-time comparison: the lease ends on return. Usable restoration and a
continuously owned, identity-bound removal procedure remain required.
