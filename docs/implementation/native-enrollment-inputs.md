# Private first-install input custody

`NativeEnrollmentInputs` reads three private files without executing commands,
creating a journal or changing installation data. This is a dependency for the
fixed coordinator. It does not establish fresh resource capability or installation
acceptance.

`request.json` contains exactly `protocol: 1`, `purpose:
"native_initial_enrollment"`, canonical operation UUID and the journal's closed
`intent`. The independently expected digest is SHA256 of canonical compact
sorted-key UTF-8 JSON for that request. `intent.allocation_sha256` seals the
allocation object in `allocation.json`; `intent.inputs_sha256` seals the private
object in `inputs.json`. Ordinary status must not expose private inputs or their
password-containing checksums.

The allocation object follows [fresh allocation admission](initial-allocation-admission.md).
Its resource shape, profile, database metadata, scope identities and recorded
empty-directory/database state are closed. Installation, configuration, storage,
SSH, history and staging directory identities are matched to the actual private
filesystem. Historical metadata is not a fresh database, executable or kernel
observation. The coordinator must independently re-observe those resources and
the exact current boot/namespaces before actions; it cannot adopt a namesake path.

`inputs.json` contains exactly `protocol: 1`, `bootstrap` and `plan`. Bootstrap
has the first-owner entry's five string fields: installation/request UUIDs,
username, team and password. The installation must match the intent; names and
UTF-8 password lengths follow the entry contract, with NUL excluded because
environment custody cannot carry it. Plan has exactly the retained private
archive identity and the independently sealed `bootstrap_request_sha256`, using
the entry's ordered JSON-array digest. No command strings, callbacks or role
choices are accepted.

The input directory and archive are outside the installation root. File ownership,
private modes, single links, stable bytes and exact device/inode identities are
checked. Replacing a private record or archive with identical bytes refuses an
existing reader. Directory replacement also refuses. Actual original-file
restoration can retain the same custody; failed/replaced materials are preserved.
The parser checks supported OS/architecture before private-file and archive
hashing. Artifact structure and candidate compatibility still belong to the
separate native artifact inspector.

Seven component checks passed. They cover read-only behavior with no subprocess,
wrong seals, independently resealed unknown commands/roles/nested fields,
same-byte record/archive replacement, changed resources, symlink/hardlink/shared
permissions and conflicting private bootstrap inputs. Inert resource metadata
and an intentionally invalid archive exercise custody only. The complete isolated
operator suite passed 183 tests: 171 Linux checks and 12 expected platform skips,
including the real PostgreSQL18.4 boundary checks.

Five additional checks passed in the actual previously allocated delegated
fixture. They preserved installation bytes, refused a wrong independent seal,
refused replaced private/retained archive inodes, retained the exact original
files, and separately confirmed the native inspector refused the inert archive.
No journal, staged code, actor or runtime marker was created. All five process
groups were empty after the controller exited.

Required integration CI, actual initial stage actions, first activation/history
handoff, allocator/cancellation, reboot/supervision, managed Cloud and complete
J14 acceptance remain unfinished. These custody checks do not count as native
artifact readiness or an installed product workflow.
