# Protected native operation inputs

Implementation under [decision 0018](../decisions/0018-native-supervision-generations.md).
This reader binds a fixed command to independently protected original inputs.
It does not dispatch stages, acquire lifecycle or database exclusion, validate
durable continuity, publish a generation, reconcile responsibility or establish
readiness. The native application and controller dispatch remain unwired.

`NativeOperationInputs` takes only an installation UUID and the canonical bounded
command bytes. It independently constructs `NativeControllerScope`; the caller
must be the allocated systemd service's original ordinary MainPID. No caller
paths, account IDs, authority maps, programs or callbacks enter the public API.
This reader does not prove an incoming socket peer; the owned endpoint must still
observe actual peer credentials before a controller selects a command.

The fixed Root seal is
`/etc/gitgood/installations/INSTALLATION/operations/OPERATION.json`. Its canonical
JSON is bounded to 8192 bytes, has unique keys, and contains exactly `protocol`,
`kind`, `installation`, `operation`, `purpose`, `durable_binding_sha256`, `uid`,
`gid`, `directory_identity` and `files`. Protocol is 2 and kind is
`native_operation_inputs_seal`. Account IDs must equal the admitted controller;
the operation, installation and request digest must equal the decoded command.
The binding digest is an immutable reference, not an observation of current
persistent resources. Complete continuity remains a separate engine requirement.

Files have fixed names and bounds, selected by sealed purpose:

| Purpose | Fixed actions | Private files |
|---|---|---|
| `native_initial_enrollment` | `enroll`, `enroll-resume` | `request.json` (16 KiB), `allocation.json` (128 KiB), `inputs.json` (16 KiB) |
| `native_upgrade_execution` | `upgrade`, `upgrade-recover`, `upgrade-resume` | `request.json` (16 KiB), `intent.json` (16 KiB), `inventory.json` (128 KiB), `plan.json` (16 KiB) |

Status, backup, restore, export and retirement refuse before opening scope or
inputs. Their protocol-2 dispatch and input formats remain required work.
Recovery actions retain the original operation and request; changing action
within the sealed purpose cannot replace its inputs. Cross-purpose commands
refuse. These are fresh protocol-2 formats; existing protocol-1 commands and
journals are not adopted or converted by this reader.

The fixed private directory is
`/var/lib/gitgood/operation-inputs/INSTALLATION/OPERATION`, outside the installation
resources. Protected Root parents and the sealed original directory device,
inode and UID are required. The directory belongs to the admitted UID/GID with
mode 0700. Exactly the purpose's fixed files may be present. Each seal entry
contains `device`, `inode`, `bytes`, `uid`, `gid`, `mode`, `links`, `mtime_ns`,
`ctime_ns` and `sha256`. Files must be original regular files with mode 0600,
one link and the exact admitted account, size, metadata and digest. A fresh
reader cannot adopt replacement files or same-inode rewrites under an unchanged
seal, even when their bytes match. The Root allocator must seal files only after
their final preparation; that allocator is not implemented by this component.

The reader holds the directory and all original file descriptors, uses
`O_NOFOLLOW`, `O_CLOEXEC` and nonblocking opens, and brackets bounded reads with
descriptor and pathname identity checks. It retains nanosecond file metadata
and the private directory's mutation timestamps. Checks bracket these with
original Root seal, parent and current service observation. Identity or custody
loss permanently closes the instance. Restoring names, permissions or bytes
does not revive it. Close retains every input and seal, including partial failure.
No replacement is signaled, modified, adopted or removed.

`request.json` has exactly `protocol`, `kind`, `installation`, `operation`,
`purpose`, `durable_binding_sha256` and `files`. Kind is `native_lifecycle_request`;
protocol is 2. Its `files` map records the exact byte counts and SHA-256 digests
of the remaining fixed inputs. Their JSON must be canonical, contain unique
keys and carry an integer protocol 2. Their complete stage-specific schemas,
artifact/resource observations and semantics must be validated by the future
generation-aware engines; this reader does not execute or approve their content.

`check()` returns a detached private projection for engine use, including
`sealed_inputs_observed: true` and false operation-admission, lifecycle-exclusion,
generation-publication and readiness flags. The projection may contain private
bootstrap material. It is not a status response or public evidence artifact and
must not be logged or sent to a caller. Diagnostics use constant refusal text.

Current focused verification exercises actual ordinary Linux descriptors,
replacement files/directories, same-byte rewrites, permission restoration, forks,
symlinks, hardlinks, FIFOs, closed formats and cross-purpose refusal. A separate
fixed-path Root/private fixture checks constructor refusals and live seal/input
loss, including new-reader refusal after replacement. Its systemd service
observation and cache freeze are explicit stand-ins; the files, ownership,
permissions and descriptors are actual. It observes no credential output and
executes no lifecycle stage. These checks do not verify installed service
admission, Root allocation, recovery, dispatch or complete J14/J15 acceptance.
