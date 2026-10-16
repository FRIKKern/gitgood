# Ordinary controller artifact inspection

`NativeArtifactInspectionController` executes archive inspection while the
original ordinary systemd controller retains its installation history lock and
database writer session. It records the actual inspection receipt before
beginning `stage`. The fixed Root socket path now connects that request to
serialized policy allocation and protected extraction. The controller validates
actual published code before recording durable stage completion. This source
path remains unverified on a live systemd controller until hosted evidence passes;
production provisioning and the long-lived Root listener remain unfinished.

## Original controller custody

The constructor accepts an installation UUID and exact existing
`GenerationRecordCustody`, `NativeCommandEndpoint` and
`NativeLifecycleResponsibility` objects. They must belong to the original
ordinary MainPID, installation and journal. The caller must have matching ordinary
UID/GID; Root and caller authority maps refuse before resource reads.

The fixed protected generation and operation policies supply original runtime,
inputs, candidate, request, publication, directory/lock identities and limits.
Actual persistent binding, private configuration, controller endpoint and history
remain checked. The controller borrows the original OS custody/endpoint/journal
and owns only its inspection reader, archive descriptor and `psql` writer session.
Application worker groups must remain stopped.

## Controller windows and real inspection

A separate private reader reuses the complete generation/lifecycle validators.
It accepts only running `inspect`, pending inspection completion, running `stage`
and pending stage completion for this original operation. It supplies no worker admission and does not
expand the maintenance/runtime worker stage lists. Other incomplete operations,
changed inputs, generation/publication or journal state refuse.

The original sealed artifact declaration selects the fixed Root-controlled
`/var/lib/gitgood/artifact-inputs/INSTALLATION/OPERATION/archive.tar.gz` by
candidate, SHA-256 and bounded bytes. The ordinary controller needs read access;
the archive and every parent must remain Root-owned and unwritable by ordinary
accounts. Original parent identities and archive descriptor/named metadata remain
checked. There are no caller paths, programs, environments or callbacks.

While holding the original writer exclusion, inspection bounds gzip/tar headers
and inventory before the shared native inspector validates digest, build identity
and candidate. The canonical actual inspection receipt is published through the
owned journal's `succeed('inspect', ...)`. Inspection executes no application code
and establishes no readiness or stage extraction.

Reader refresh admits only the journal's one newly published event and head. All
generation/publication/input metadata, prior lifecycle record identities and
directory inodes must remain unchanged. This permits the controller's actual
transition without adopting a replacement generation, input or old record.

## Serialized staging and completion

`begin_stage()` requires successful actual inspection, begins the durable stage
and retains the same writer session/history custody. It returns the existing
bounded canonical Root controller request with installation/operation and the
original history descriptor. Returning that frame neither sends it nor admits a
Root effect. `stage()` connects only to the independently provisioned
`/run/gitgood/root-artifacts/INSTALLATION.sock`, whose original Root owner, ordinary
group, `0620` mode, inode and protected parents must match. The actual socket peer
must have Root UID/GID. Its bounded canonical response binds this installation,
operation, candidate and stage receipt hash. A refusal or changed peer/path
retains the running stage and every effect.

[The Root dispatcher](native-root-artifact-dispatch.md) authenticates the actual
ordinary MainPID and its original history descriptor, observes its original SQL
writer exclusion, allocates the fixed policy under an actual Root flock, and
brackets every extraction check with that retained original custody. Root SQL
observers close before success is acknowledged; the ordinary controller then
checks its same original writer session again.

The ordinary controller reads only the fixed published Root output. It checks
the response hash against the actual read-only receipt, original request/scope
and running-stage snapshot, archive digest and byte count, inspection-derived
allocation budget, original directory/file identities, exact entry sets, every
regular file's content hash, confined Forge symlinks and the full inventory hash.
Only after those checks and another original-custody check does its owned journal
record `succeed('stage', ...)`. An immutable record and controlled head refresh
then expose pending stage completion. No response alone supplies completion.

Closing or observed loss permanently invalidates the controller and releases only
its owned reader/archive/writer session. Original endpoint, OS lock, journal,
inputs, archive and every retained record remain. Interrupted running stages
still require explicit actual-effect reconciliation.

Thirteen portable admission/window/refresh/transition checks include a real archive
read with explicit controller and journal stand-ins. Four Linux Root output tests
use actual extraction, read-only files, content hashes and original identities,
with explicit controller and fixed-path stand-ins. Ten dispatch boundary/socket
tests keep their authority stand-ins explicit. These checks do not prove live
ordinary systemd custody or complete controller-to-Root dispatch.

The hosted default-release case now selects the complete actual production Forge
and web archive, performs this controller/Root path, records actual inspection and
stage receipts, and launches migration, bootstrap and normal packaged runtime
from the staged code directory. Its public web policy binds the staged web tree.
That expanded case is unverified until its exact source, log and artifact are
reviewed. Production provisioning/listener, interrupted-effect reconciliation,
activation/enrollment and full reboot/replacement recovery remain required before
J14/J15 acceptance or original VM retirement.

The hosted fixture can diagnose a stalled full stage with seventeen fixed method
counters. They record only invocation counts and overlapping cumulative elapsed
milliseconds for the guard, file, SQL, manager and extraction paths. Wrappers
forward the original arguments, return value and exception and restore every
original method on exit, including interruption or partial setup failure. These
counters emit no stacks, paths, arguments, SQL or return values.
The fixed `_code_parent` and `_code_directory` counters distinguish archive entry
traversal from later directory sealing using counts alone. They use the same
forwarding wrapper and inspect no traversal names, descriptors or results.
The installed production modules, payload, guards and deadlines are unchanged.
The fixture additionally profiles only invocation ten of the read-only staging
guard. Every other guard and every effect runs outside that sample. An existing
profiler is preserved without starting another; both legacy profiling and the
CPython monitoring profiler slot are checked. Original arguments, results and
exceptions are forwarded, and profiler state is restored even on interruption.
Only a fixed installed file/function set, source line, call count and self or
cumulative milliseconds can appear in at most 64 deterministic selected rows. No
stack, caller, private path, argument, SQL, environment or return value is emitted.
The same rows also retain bounded microseconds, and the hot subset uses that
precision to avoid millisecond rounding ties. Fixed canonical serialization and
observation-wrapper counters are included. Four fixed `copy` functions are
accepted only from the exact loaded standard-library module, with its path
replaced by the constant `copy.py` label; matching basenames elsewhere refuse.
Six fixed standard-library Path methods additionally require the exact loaded
code filename, first line and function name, and emit only the constant
`pathlib.py` label. This separates path construction and metadata-call cost
without recording filesystem names. Installed-module basename matching cannot
admit either standard-library label. The same single guard and 64-row bound apply.
Nine POSIX file primitives and four socket methods additionally require their
exact closed CPython builtin profiler key. They emit constant `posix.py` or
`socket.py` labels and source line zero; ordinary Python rows still require a
positive bounded source line. Private filenames, builtin representations and
callers are never emitted. Basename matching cannot admit these labels. The
four artifact ancestor helpers, six Path methods, thirteen primitives and seven
fixed validation/copy helpers have priority when present, followed by the
hottest remaining rows within the same 64-row cap. This prevents a low-cost required helper from disappearing and
separates filesystem/socket time from its overlapping Python wrappers.
Portable regressions cover exact builtin keys, spoofed labels, numeric bounds,
required low-cost rows under cap pressure and actual owned socket calls. A
hosted Linux regression profiles reads of its own tiny fixture file; none of
these component probes proves full staging or production performance.
When the sample contains the installed staging guard, eight additional fixed
`guard-self-costs.py` tags partition every profiler entry's self time into
installed Python, pathlib, copy, JSON, regular expressions, UUID, builtin and
unnamed other Python categories. Only counts and summed self time are emitted;
unknown filenames, function names and callers remain unnamed. The categories
use line zero and equal self/cumulative fields because they sum disjoint self
costs, rather than adding overlapping stack costs. They share the same 64-row
cap and priority with required function rows and the guard itself. Category
totals form one partition; function rows are a separate overlapping view and
must not be added to that partition. Invalid counts or self times refuse
postprocessing rather than silently discard cost. Portable regressions check
complete partitioning, privacy, numeric refusal, cap pressure and an actual
cProfile run of an explicitly synthetic guard. No further guard invocation is
profiled, and the production guard and aggregate timer wrappers are unchanged.
Within the same cap, optional self-cost rows identify at most eight known public
production modules, eight closed builtin keys and nine additional exact loaded
pathlib helper code objects. Module rows use the fixed `module_self` tag and line
zero; unknown module basenames and function names are never emitted. Builtin
rows use `builtin-self.py`, fixed tags and line zero. Path helpers use
`pathlib-self.py` and require the loaded filename, first line and function name;
the original six Path code objects remain separate. These optional groups rank
by self time, rather than overlapping cumulative time, after all required rows.
Their equal self/cumulative fields describe self costs only. They overlap the
eight-category partition and must not be added to it. The module allowlist must
match the exact public production closure. Regressions cover that closure,
spoofed keys/labels, numeric bounds, row quotas, actual tiny file reads and
pathlib calls in an explicitly synthetic profile. Original guard forwarding,
profiler ownership, payload, production checks and deadlines remain unchanged.
These instrumented runs are diagnostic; production deadline acceptance still
requires an uninstrumented complete stage and subsequent staged runtime. Private
acceptance rejects either aggregate timers or the guard sample.

An earlier hosted diagnostic compiles a small CPython extension outside the
production module closure. Actual Root-owned Linux file tests compare its
fresh ordered ancestor/leaf metadata observations with the original fingerprint,
including refusal, ownership, links, size, executable mode, encoding and
timestamps. Unsupported prototype inputs fall back to the original method.
No filesystem observation is retained. Public C, adapter and compiled ELF hashes
identify the owned diagnostic files without emitting their runtime paths.

Before the first ready stage guard, that diagnostic runs twenty alternating pairs
of the complete original guard on the same original actors and resources. Each
pair selects either the original fingerprint or the diagnostic adapter; results
must agree, and every check still uses both fresh Root observation passes.
The original fingerprint descriptor is restored after each check and on every
exception. A refusal or mismatch poisons the original views; restoration cannot
revive them. Existing timers and the single guard-ten profile start only after
the comparison. The extra forty read-only checks and their paired elapsed times
are recorded separately, with no arguments, returned values, paths or SQL.

The original fingerprint runs for every subsequent staging effect. These pairs
measure a possible repair; they do not adopt it or prove production performance.
All production source bytes, the complete payload, freshness/effect guards and
the 240-second deadline remain unchanged. A complete uninstrumented stage,
staged runtime and the original installation/recovery gates are still required.

The Root reader prepares the two fixed read-only SELECT envelopes within its
original session. The nonce is a fresh text parameter for each execution, and
all original framing, read-only/session identity, before/after process, pipe,
kernel and socket checks and the poison path remain. Only a bounded set of two
statement kinds is retained; no returned observation or validation is cached.
Each execution reads current data. Closing the original owned client ends its
session and its plans; a failed reader never reconnects. See PostgreSQL's
[prepared-statement contract](https://www.postgresql.org/docs/18/sql-prepare.html).

A prior disposable comparison changed only statement construction in a fixture
copy of the original exchange AST, requiring an inverse transformation to recover
every original node. Twenty alternating whole-guard pairs used the same retained
Root reader and custody checks before any effects. Original methods and session
state were restored before staging. That measured experiment justified selecting
preparation for a production candidate; it did not prove full staging, recovery
or release readiness. The historical helper is retained but is no longer active
in the Root proof. The compiled fingerprint is also inactive there; its separate
standalone equivalence tests remain a diagnostic regression.

Production framing and refusal tests cover fixed statement kinds, nonce
injection, exact query bodies, corrupt plan state and failed preparation without
reconnection. Hosted PostgreSQL tests call production reader methods against a
newly owned database and role, checking repeated replies, changed client counts,
role changes and original client/backend loss. Those SQL tests explicitly
substitute process/base observers; the complete installed Root proof must verify
actual custody. The complete payload, freshness/effect guards, two separate Root
passes and 240-second deadline remain unchanged. Existing aggregate timers and
the single guard-ten sample remain diagnostic only. Complete uninstrumented
staging/runtime plus the original installation and recovery gates still apply.

The hosted fixture also measures process CPU, calling-thread CPU and wall time
around the existing read-only guard calls. A fixed numeric receipt identifies
the number of calls and aggregate milliseconds. Child psql/PostgreSQL processes
and ordinary actors are excluded from these CPU clocks; a wall/CPU difference
can include waiting and descheduling and does not identify their cause.
The wrapper forwards original arguments, results and exceptions, starts no
profile and invokes no additional guard. The original seventeen method timers,
single guard-ten profile and method restoration remain. Numeric/type bounds
refuse invalid counters, and no arguments, paths, returned values or private
attributes are emitted. These clocks guide the next performance repair; they
do not establish an uninstrumented deadline or full journey acceptance.

An earlier hosted trial used a pinned PyPy 3.11 v8.0.1 interpreter for
the Root helper only. The ordinary manager/workers retained their original
Python 3.12 executable. The complete payload, original actors within each
allocated trial, checks and deadlines are unchanged. A lock-parser compatibility
repair expresses the same Linux access mask through `O_WRONLY | O_RDWR` because
the experimental interpreter does not export `O_ACCMODE`; original descriptor,
flock and actor checks remain. Its complete component scope passed under PyPy,
with the original CPython checks retained. The trial tested a larger
execution-cost change after measured Root CPU dominated guard wall time.
It passed 372 Root component cases, actual pidfd/SQL cases and installed source
identity checks, but the full archive still reached the original 240-second
deadline before output verification. PyPy adoption was rejected; the active
proof again uses CPython. This is no same-actor interpreter speed comparison.

The fixture installer verifies the publisher's
[archive checksum](https://pypy.org/checksums.html), bounded paths, link targets,
entry/byte limits and available space before extracting a new Root-owned runtime
namespace. It retains at least 20 GiB free after estimated archive, extraction
and metadata allocations. An immutable package-tree hash, executable hash,
archive hash and closed implementation/version fields identify the actual
interpreter. Runtime downloads and execution happen only on the disposable
hosted runner. No local runtime, dependency payload or VM is created.

All original selected Root component scopes and the production PostgreSQL cases
ran under PyPy before the full installed ownership/stage/runtime proof.
The CPython-specific single-guard profiler was explicitly unsupported in that
trial; original method counts and process/thread CPU clocks remained.
The active CPython proof retains its original profiler path.
The receipt labels the runtime diagnostic only and production adoption false.
A complete result must still preserve every security and recovery gate, and any
runtime adoption requires installation, packaging, cold-start and recovery work
plus uninstrumented acceptance. A component or experimental pass alone cannot
authorize VM retirement or establish release readiness.

For a failed PyPy component scope, the historical trial reran that fixed
synthetic scope with failure-only exception-site tracing. At most 64 source
locations and closed exception type labels from the first failing case are
reported, with an explicit omission count. Only exact repository production
source paths are traced; paths, exception messages, arguments and locals are
absent from the receipt. An existing trace is never displaced, and trace state
is restored on exit. The repeated diagnostic cannot pass the failed gate or
run the dependent full staging proof, even if the repeated scope passes.

The diagnostic's helper-loss injection retains its original pidfd custody and
PID/birth/UID/parent/cgroup and live-state checks before signalling. If the
interpreter omits Python's pidfd functions, a hosted-only bridge invokes the
same libc `pidfd_open` and `pidfd_send_signal` operations with fixed zero flags
and `SIGKILL`; it never substitutes a PID-based signal. Native API failures
propagate without retry through libc, and the original descriptor always closes.
Both interpreters verified actual owned child identities, close-on-exec, unrelated
child survival, dead targets and closed descriptors, including the forced libc
path. This is a fixture compatibility bridge and changes no production module,
stage guard, operation deadline or recovery acceptance requirement.

The active CPython sample attributes direct calls into its exact loaded pathlib
code to fixed installed module/function pairs and their public source lines.
At most eight callers, ranked by cumulative edge time, share the original
combined 64-row cap with the required counters. These overlapping edge costs
have zero attributed self time and are not a disjoint CPU partition. Unknown
source labels, private paths, arguments and stack contents are excluded;
counter/type/time bounds and aggregate overflow are checked. This postprocesses
the same guard-ten profile, invokes no additional guard or filesystem read, and
guides the scope of the next repair while retaining complete staging and
recovery requirements.

The retained fixture-only path comparison tests immutable construction in the three
modules identified by those costs: service scope, durable binding and the Root
database reader. Exact concrete path inputs are reused; at most 64 bounded
exact-string constructor results are retained. Other input types and keyword
arguments use the original constructor. The cache contains only lexical paths,
with no filesystem, process, database, socket or validation observations.

Twenty baseline/prototype pairs alternate order on the same original stage and
actors before any effect and before the original timers and guard-ten profile.
Every module symbol is restored after each invocation and on interruption;
observations must match. Original Root file, binding and reader refusal scopes
also run with the factory active. The original guard and symbols are restored
before staging. Numeric receipts contain only paired times and bounded reuse
counts. This trial adopts no production behavior and does not establish the
full staging deadline, staged runtime or recovery requirements.

That path trial's median ratio was 0.9586 (about 4.1% faster), below its
predeclared 0.80 adoption threshold. It is no longer the active stage experiment.
The tests remain to preserve its refusal and restoration evidence.

The retained selected-query diagnostic compiles the existing systemd `Get` queue and
typed reply loop into a small hosted CPython extension. It binds the original
Root owner, library handle and bus pointer, creates no connection and retains no
observation results. The original `_get_many` still validates arguments and
checks library custody before and after the whole batch. Current Root PID/thread,
owner usability, library/bus object and pointer identity are checked during the
native loop. Selected query order, the five-second deadline, 4096-pump cap,
current-slot ownership, reverse cancellation, ASCII and typed/container bounds
remain mandatory. Callback replies stay borrowed; original slots cancel before
the callback context is released. Interruptions retain the original exception
and outer permanent-close behavior.

The hosted workflow first builds the two small diagnostic/test DSOs with warnings
as errors, exercises deterministic hostile protocol replies and interruption,
runs all 33 original systemd cases under the adapter, and compares 20 fresh batches
on one actual original bus. The stage experiment then runs 20 alternating whole-
guard pairs on the same original actors before timers, profiling or effects.
The original Python method is restored after every invocation and before staging.
At most eight connection bindings retain only original owner/handle lifetime,
and all bindings are released after the comparison without closing their buses.
This trial requires median ratio at most 0.90 with at least 18 of 20 pairs faster
before proposing adoption. Neither that threshold nor protocol tests substitute
for complete uninstrumented staging, staged runtime, installation or recovery.

That selected-query trial passed its 19 protocol cases, all 33 original systemd
cases under the adapter and 20 actual same-connection pairs. Its whole-guard
median ratio was 0.990991, with 15 of 20 pairs faster, below both adoption
criteria. Production adoption is rejected; it is no longer the active stage
comparison. Complete staging still failed at about 240 seconds before output
verification, with every production module unchanged.

The retained hosted diagnostic compiles 20 measured path helper bodies from the exact
installed CPython 3.12 standard-library source using pinned Cython 3.1.8. An inverse
AST check reconstructs every selected body after redirecting global loads to live
original globals and builtins dictionaries. Conservative f-string quoting also
preserves the parsed tree while avoiding Python 3.12 quote-reuse syntax in the
pinned compiler. Original classes, instances and raw
descriptors remain authoritative. Class closure dependencies, unsupported source
shapes and unsafe compiler options refuse. The hosted builder authenticates the
compiler wheel, bounds extraction and temporary storage, and records source,
options, generated-code and ELF identities; it never runs locally.

The loader checks Root-owned source/ELF custody and original runtime function
code before installing function, classmethod and property bodies on the original
classes. Semantic checks cover lexical values/types, PathLike and subclass
behavior, live global replacement/deletion, exception identity, and fresh
stat/lstat/resolve results after filesystem mutation. All 372 original Root
mutation/refusal cases must also pass with the adapter active. Compiled function
and frame metadata have compiler-specific limits; no general interpreter or
production equivalence is claimed by these component results.

Twenty whole-guard pairs then alternate on the original actors, with no active
profiler. Every descriptor restores after each prototype invocation, including
interruption and partial installation, and before original timers, profiling or
staging effects. Code custody is read again after comparison. Receipts retain
only fixed public code identities, selected body labels, counts and paired times.
The adoption threshold is median ratio at most 0.80 with at least 18 of 20 pairs
faster. All filesystem/kernel/SQL observations, complete archive, effect guards
and production deadlines remain unchanged. Production adoption and complete
staging/runtime, installation and recovery acceptance remain unproven.

That compiled path trial passed 13 source checks, 11 adapter/runtime cases and
all 372 original Root cases under the adapter. Its 20 whole-guard pairs had
median ratio 1.047818 with zero pairs faster, failing the unchanged 0.80 and
18-of-20 criteria. Production adoption is rejected. The original full stage
still reached approximately 240 seconds before output verification. The active
full proof no longer loads or copies that experimental runtime; all compiler,
semantic, descriptor-restoration and original Root regression tests remain.

The existing guard-ten diagnostic now ranks at most eight individual installed
function self costs from a closed public function inventory in the measured hot
service, systemd, kernel, binding, reader, lifecycle and generation modules. These
refine the former eight coarse module-total slots. The installed-code category
aggregate, primitive/path quotas and caller attribution remain within the same
combined 64-row limit. Self costs overlap those category totals; they must not
be added as separate work. Labels and source lines identify public functions;
arguments, locals, caller mappings, private paths and observation values are
absent. Unknown source/function keys are excluded and invalid numeric data
refuses. This postprocesses the same existing guard-ten profile and invokes no
additional guard, profile or observation. It selects the next repair and cannot
establish uninstrumented performance, staging, runtime or recovery acceptance.

The broader lexical-path experiment adds derived-path construction to the retained
three-module constructor prototype. It changes only the original PurePath
`with_segments` descriptor during private read-only comparisons. Exact standard
path classes and exact strings can reuse at most 256 join plans, alongside the
existing 64 constructor plans. Keys retain raw lexical strings and classes, with
at most 64 raw components and 1,024 characters in total; resulting paths remain
bounded to 64 parts and 1,024 characters. Oversized or unsupported inputs,
PathLike objects, subclasses, keyword arguments and failures use the original
constructor behavior without caching errors. A conservative 16 MiB memory
estimate covers these small bounded plans.

The actual Root-controlled CPython 3.12 source authenticates the original pure
constructor body and the construction-role code objects. Diagnostic source
identities, namespace/builtin bindings, original classes, construction methods,
Root PID/thread and all-Root UID/GID state are checked. All original metadata
methods remain live; no filesystem, ancestor, process, SQL, socket, validation
or guard observation is retained. Plan objects reuse lexical object identity;
this diagnostic does not claim general standard-library API equivalence.

Twenty-four component cases include portable lexical values, side effects,
exception identity, input bounds, namespace/owner refusal, interruption and
partial-installation cleanup, fresh file/replacement observations and SDK source
shape checks. Three actual Linux cases verify source custody, fresh symlink
changes and all 372 original Root mutation/refusal cases with the combined
adapter active. These cases require current hosted evidence.

The first combined trial passed SDK custody and symlink freshness but failed the
original process-status fixtures because the constructor callable did not expose
the original Path.stat class attribute used for metadata mutation injection.
The diagnostic factory now forwards that narrow interface to the same original
class. Reads stay live, nested test-directed mutations unwind in order, and all
pending mutations restore during adapter cleanup even after interruption. Normal
adapter installation does not change any metadata method. The original tests
and their read-order/refusal assertions remain unchanged; no metadata result is
cached by this interface.

Twenty whole-guard baseline/prototype pairs alternate on the same original stage
and actors before the original timers and guard-ten profiler. The original
method descriptor and all three module symbols restore after every prototype
invocation and before any staging effect, including failures and interruptions.
All plans clear after comparison. Only numeric counts/times and fixed public
code hashes appear in the receipt. The proposal threshold remains median ratio
at most 0.80 and at least 18 of 20 pairs faster. Production adoption, complete
uninstrumented staging and staged runtime, installation and recovery remain
separate unproven requirements. Neither earlier rejected path experiment is
rerun unchanged or treated as accepted behavior.

The combined lexical trial subsequently passed all 24 cases and all 372 original
Root cases under the adapter. All 20 whole-guard pairs were faster, but their
median ratio was 0.945437, failing the unchanged 0.80 gate. Adoption is rejected.
The original full stage still failed at approximately 240 seconds before output
verification. That runtime is no longer copied or loaded by the full proof; its
component regression gate remains.

The next hosted diagnostic selects 116 bodies across the seven installed hot
modules identified by the existing self-cost profile. The original production
files and classes remain authoritative. Only function bodies and direct module
aliases in the admitted deployment directory are replaced during read-only
comparison. Arbitrary decorators, the selected-bus callback closure, Root pass
wrappers and unsupported class-closure dependencies stay on the interpreter.
Global loads use each original function's live module and builtins dictionaries;
an inverse AST check reconstructs every selected body. Bounded literal default
arithmetic is checked without executing supplied source and stays unchanged.

The builder uses the existing authenticated Cython 3.1.8 wheel and conservative
options on the disposable hosted runner, with a 512 MiB temporary allocation
estimate and the 20 GiB volume reserve. It copies only the bounded source,
manifest and extension closure to Root-owned storage. The loader checks exact
installed source/code identities, ELF identity and file custody again after the
comparison. Original classes, exception types and all metadata/kernel/SQL reads
remain live. This is a compiler experiment, with compiler-specific frame and
function metadata limits, not general Python equivalence or product adoption;
see the [compiler's documented limitations](https://cython.readthedocs.io/en/3.1.x/src/userguide/limitations.html).

Seventeen cases cover source admission, lexical scope/global mutation, direct
aliases, static/class methods, original exceptions, owner refusal, partial
installation and complete restoration after interruption. Three require actual
Linux Root: exact code custody, fresh file mutation and all 372 unchanged
original Root cases with the compiled bodies active. Hosted results remain
pending. Twenty alternating whole-guard pairs on the original actors must have
median ratio at most 0.80 and at least 18 pairs faster before proposing adoption.
Every body and alias restores before each baseline and before the unchanged
timers, guard-ten profile and staging effects. No observation result is retained;
receipts contain fixed public code hashes/labels and bounded counters/times.
Complete uninstrumented staging/output, staged normal runtime, production
listener/provisioning, interruption reconciliation, installation and actual
replacement-host restore remain required before original VM retirement.

The first installed-body trial compiled successfully and passed actual Root code
and ELF custody, but adapter initialization exposed repeated top-level donor
class definitions. Later definitions had overwritten earlier module functions;
the wrapped Root suite and whole-guard timings never executed. The selector now
groups all top-level functions into one donor per module and requires each
selected donor/method pair exactly once before and after global-load rewriting.
Regressions cover the actual multi-function modules plus duplicate classes,
duplicate methods and missing bodies. The same 116 body AST identities, seven
global-load counts, compiler/header/options, runtime adapter, original tests and
full proof remain unchanged. New hosted semantic and performance evidence is
still required.

The repaired selector then passed all 372 original Root cases under the compiled
adapter and actual code/ELF custody. A separate fault-injection stand-in omitted
the original file-open flags, so argument evaluation failed before its intended
open exception. That fixture now retains those flags; a portable execution of
the exact original read helper verifies both flag arguments and original
exception identity. The actual compiled mutation/error case retains every
assertion. No compiler, runtime adapter, production code or operation guard is
changed by this fixture repair; paired performance and full staging still need
hosted evidence.

The installed-body experiment subsequently passed all 17 cases and all 372
original Root cases with the adapter active. Exact hosted review also verified
all 59 installed production hashes and 82 ownership fixtures. Its 20 whole-guard
pairs had median ratio 1.049163, with only one pair faster: approximately 4.9%
slower overall, failing the unchanged benefit gate. Adoption is rejected. The
original full stage again reached about 240 seconds before output verification.
The full proof no longer loads or copies this experimental runtime; its source,
compiler, restoration and original Root regression gates remain. The replacement
investigation targets direct fresh metadata observation and must preserve every
original guard, observation-pass boundary, actor, complete archive and deadline.

The replacement diagnostic uses a finite C extension for four related metadata
paths: Root files, executables, persistent paths and held history custody. It
performs each original fresh observation in the original order, returning the
same tuple/dictionary fields or the original typed refusal. Executable resolution
and history directory enumeration retain their original Python implementations.
Held and named descriptors remain distinct observations, including the second
directory `fstat`. The original custody observation-pass decorator remains in
place; no new filesystem result cache or comparison baseline is introduced.

The loader authenticates Root-owned C/ELF/helper files, compiler flags and the
actual original Python source/code objects before use, then re-reads their
custody after comparison. Unsupported argument shapes and deliberately replaced
metadata hooks use the original implementation before native observation.
A native error or failed predicate refuses without a Python retry. The adapter
retains all four original classes and restores all four method descriptors after
each prototype pair, interruption or partial installation.

The follow-up suite has thirty-seven cases for admission, refusal, interruption,
alternation, profile redaction and restoration. Fifteen require actual Linux Root, including all 372
unchanged original Root cases and dedicated ordinary-owned history resources
with real held descriptors, rebinding/loss, metadata/entry mutation, restored
mtime and separate observation passes. These hosted cases remain pending.
The full proof compares twenty alternating whole-guard pairs on its original
actors at the first guard, restores the original methods before entering the
unchanged stage measurements, and then attempts the complete archive. Median
ratio at most 0.80 and at least 18 faster pairs remain required for a benefit;
the diagnostic is not production adoption or journey acceptance. Hosted copies
and staging reserve at least 20 GiB after estimated allocations on each volume.
Complete uninstrumented staging, staged normal runtime, production listener,
interrupted-effect reconciliation, installation and replacement-host restoration
remain required before VM retirement.

Admission also checks each original Python metadata hook's code object: replacing
`__code__` in place cannot retain native admission merely by keeping the same
function object. Final code custody is checked before invoking metadata hooks.
A present retained-history entry with a `None` descriptor is unsupported and
uses the original body before native observation; it cannot be treated as an
absent retained entry. Regressions cover both portable admission and actual Linux
Root error/custody behavior. Both repairs subsequently passed hosted verification
with the 35-case sampling candidate and all 372 original Root cases.

The first metadata candidate passed all 21 cases and all 372 original Root cases
with the adapter active. Exact review verified all 59 installed production hashes,
82 ownership fixtures and retained regression scopes. All four families executed
with zero fallback, but twenty whole-guard pairs had median ratio 0.999987 and
only ten pairs faster. The unchanged 0.80/18 benefit gate failed; adoption is
rejected. Full original staging again timed out at 240162 ms with output checks
still zero. The complete archive and production deadlines remain unchanged.
The admission repair above has only local evidence. The next investigation must
attribute native-path overhead within the existing read-only guard-ten sample,
without adding guard calls, profiling effects or repeating an unchanged rejected
timing comparison. A fresh benefit comparison and complete uninstrumented
staging/runtime remain required for any later adoption proposal.

The guard-ten diagnostic enables the metadata adapter only within the existing
read-only guard-ten profile. It starts the original measurements at the first
guard, makes no extra guard call and restores the four original descriptors
before the next effect or guard. It does not repeat the rejected paired timing
comparison. Native profiler labels come from the actual authenticated extension
functions using no-argument preflight; metadata counters must remain unchanged
during that label discovery. The sample then requires all four families, positive
native metadata activity and zero fallback, followed by fresh code custody.

An additional receipt retains at most sixteen rows with fixed public helper/API
labels and bounded numeric costs. It excludes unknown rows without inspecting
their values. The original guard-ten profile, seventeen method timers, CPU
scope, production reads, archive and deadlines remain intact. Nine portable
regressions and one actual Linux Root sample case cover exact guard count,
interruption/error identity, complete restoration, profiler-label admission,
private-data exclusion and deterministic bounds. Exact hosted review of candidate
1946ce1 verified all 35 cases, all 372 original Root cases, 59 installed source
hashes, 82 ownership fixtures and retained regression scopes. The sample ran once
with no extra guard, all four families active, zero fallback and complete
restoration. Its native admission scan used 935 microseconds, custody argument
construction 927 microseconds, and the profiled guard 41922 microseconds. These
costs overlap and do not establish uninstrumented timing. Full staging failed at
240088 ms with no output checks; the full archive and deadlines are unchanged.

Portable characterization then exposed SDK admission gaps for rebinding
`pathlib.os` and overriding the concrete path class's metadata methods. The local
repair checks those globals and effective concrete-class attributes, normalizing
bound class methods by their original function and owner. Its 37-case suite has
22 portable passes and fifteen Linux Root cases pending. This repair is not
covered by the earlier hosted result. The next experiment must cover complete
fresh file reads and argument preparation across the filesystem path; reducing
admission checks alone is insufficient evidence for the unchanged whole-guard
benefit gate. The earlier hosted result does not verify the following extension.

The diagnostic now includes the four distinct complete-read roles in
`native_service_scope.root_file`, `native_durable_binding.private_file`,
`native_service_scope.read_bytes` and `native_kernel_backend._read`, alongside
the four metadata roles. The C reader retains each role's original ancestor,
leaf, open flags, buffered maximum-plus-one read, before/after metadata and close
boundary. Hashing, returned records, size predicates and kernel ASCII conversion
remain after that boundary. A borrowed buffered wrapper leaves the C backend
responsible for closing its one opened descriptor even if construction or an
audit hook fails. It does not merge fingerprint and content observations.

Finite C preparation converts the original persistent and custody instances into
ephemeral lexical argument tables. It refuses unsupported shapes, custom
attribute readers and class data descriptors before filesystem observations.
No observed metadata or validation result is cached. Per-role admission checks
the relevant live SDK globals, concrete path attributes, helper identities and
Python code objects on every call. Unsupported inputs fall back before native
observations; native errors and refusals never retry. Every original class stays
in place, and direct aliases in installed modules are restored after each sample,
including aliases first imported during a check. A restoration failure poisons
the adapter while preserving an already pending exception.

The existing hosted workflow retains the 37 metadata regressions and adds the
complete-read suite. Its portable cases cover return shapes, post-close size and
ASCII predicates, fallback boundaries, error identity, native preparation,
partial installation, alias restoration, poisoning and exact alternating pairs.
Linux Root cases require actual C execution for file/link/owner/mode/size
refusals, replacement and restored timestamps, descriptor construction and audit
errors, source/hook mutation, table equivalence and all 372 original Root cases.
The portable post-close metadata-mismatch fixture supplies a changed after-record;
it is not evidence of a concurrent kernel mutation. Native API replacement must
fall back before observations and fail the final code-custody check.

Before existing timers, CPU measurements, guard-ten profiling and effects, the
new backend compares 20 alternating unprofiled whole-guard pairs with the same
original actors. All eight roles and all five native counters must be positive,
with zero fallback and complete restoration between baselines and before the
original stage. The benefit gate remains a median ratio at most 0.80 and at least
18 of 20 faster pairs. Compilation, actual Linux semantics and benefit are still
pending; no adoption or staging success is claimed. Full uninstrumented output,
the staged normal runtime, listener provisioning, interruption reconciliation,
installation and actual replacement restoration remain required.

The first complete-read candidate, 97b0112, compiled successfully and passed all
37 metadata cases with their 372 original Root cases. Its read-suite process then
segfaulted at the aggregate Root case, before complete-read acceptance, guard
pairs or full staging. The backend remains rejected for use. The follow-up test
harness enables fatal-signal Python traces, runs focused read cases before the
aggregate case, and emits only fixed public Root test symbols before native
entry. Every original case remains required; these traces are diagnosis and
establish no behavior, timing or journey acceptance.

The 7f37966 trace narrowed the fault to the direct
`prepare_tables(0, object(), object, Path)` unsupported-input check, before file
I/O. This minimal built-in ancestor case reaches the same namespace scan used
by ordinary heap instances. The trace does not establish complete-read or
staging acceptance.

Source review identified a CPython 3.12 namespace-access defect in finite table
preparation: a ready built-in ancestor can have a null `tp_dict`, with its actual
namespace held in interpreter state. The MRO scan now uses the supported
`PyType_GetDict` API, pins the MRO during lookup, and releases owned references
after each check. It keeps the
same class-data-descriptor refusal and adds a focused built-in `object` ancestor
case that prepares lexical tables without any filesystem observation. The API
was checked locally on five built-in and heap namespaces without compiling the
extension. The namespace candidate has 26 cases, with its hosted outcome below.
It does not establish complete staging, runtime, recovery or production adoption.

A further portable fixture demonstrated that the additional I/O helper code and
native API identities were checked after the base loader began rereading files.
Validation now rejects those changes before invoking filesystem validation, then
performs the original owner, source-code and fresh file-custody checks. The
fixture verifies both changed I/O code and a replaced native API without calling
the filesystem validation callback. The read suite now has 27 cases: sixteen
portable passes and eleven Linux Root cases pending. These local checks do not
verify the native backend or whole-guard benefit.

Exact hosted output for 4fbe9ae verifies nine focused Linux Root read/descriptor
cases, including unsupported-object and built-in ancestor checks. All 37
metadata cases and their 372 original Root cases passed.
The read suite then aborted in the deliberate I/O-code mutation case: base file
validation invoked the altered helper before checking its code. The portable
ordering regression reproduces this failure and passes with the admission-first
validation above. The read aggregate Root suite, guard pairs and full staging
were not reached. Hosted verification of the ordering repair remains required.

Exact review of 0304c00 subsequently verified all 37 metadata cases, all 27 read
cases, both original 372-case Root suites, 82 ownership fixtures, 59 installed
production hashes and retained regression scopes. Its 20 alternating same-actor
pairs exercised all eight roles and all five native counters, with zero fallback,
equal observations and all original classes, descriptors and direct aliases
restored. The median ratio was 1.156727 with zero faster pairs: the native backend
is rejected for adoption under the unchanged 0.80 and 18-of-20 gate.

Original full staging still timed out at 240160 ms with no output checks. The
9409-member, 159520534-byte archive and deadlines were unchanged. The original
guard-ten sample remains diagnostic: its overlapping cost categories cannot be
used as uninstrumented timing or added together. The next investigation must
attribute the eight-role adapter's added cost before another benefit comparison;
an unchanged paired or baseline-only rerun would add no evidence. Complete
uninstrumented output/runtime, listener provisioning, interruption reconciliation,
installation and actual replacement recovery remain required.

The next diagnostic attributes this rejected eight-role backend within the same
existing read-only tenth-guard profile. The complete adapter is active only for
that one guard. It restores all four class descriptors, complete-read helpers
and direct or late import aliases, then revalidates exact helper, SDK and
production source custody before returning to staging. All eight roles and five
native counter groups must be positive, with zero fallback. This adds no guard,
observation pass, effect or production result cache; the original seventeen
timers, CPU windows, archive and deadlines remain unchanged.

The bounded report reserves eight native API rows and selects at most eight
Python self-cost rows from the authenticated metadata and read adapter sources.
Native labels are discovered from genuine extension builtins using no-argument
preflight with all observation and preparation counters unchanged. Unknown
profiler names and values are ignored; exported labels are fixed public names.
The count APIs retain zero-filled slots when absent from the sampled guard.
Existing metadata wrappers also call `counts()` within the guard: once for the
persistent plan and twice for custody. The focused eight-role sample therefore
expects three such calls; it must not exclude their cost from the native rows.
Portable tests cover privacy, numeric limits, deterministic selection, original
measurement start, interruption, alias restoration and source-custody failure
before effects. A new actual Linux Root case must verify the genuine labels,
all eight roles and original observations in this sample; both original Root
suites and all earlier cases remain required. These profiling changes require
fresh hosted verification and make no production benefit or adoption claim.
The rejected twenty-pair and baseline-only runs are not repeated.

Exact review of 5e16122 subsequently verified all 37 metadata cases, all 39 read
cases, both original 372-case Root suites, 82 ownership fixtures, 59 installed
production hashes and retained regression scopes. The single tenth guard
exercised all eight roles and five native counter groups with zero fallback,
all original actors and classes, complete descriptor and alias restoration,
and fresh source custody before effects. Its eight native API rows and eight
Python rows met the closed schema. All API call counts matched the independent
operation counters, including eight counter-reporting calls and 536 separate
before/after admission calls. No paired benefit comparison was repeated.

This profiled guard spent 3559 microseconds in the admission API and 4522 in
complete native reads. The unchanged coarse partition still attributed 11335
microseconds of self time to pathlib. These values identify remaining work;
overlapping cumulative rows must not be added, and different hosted samples
must not be compared as a production speedup. The earlier failed benefit gate
still rejects this backend. Full original staging timed out at 240205 ms with
zero output checks on the same complete archive. Complete uninstrumented
staging/runtime and the remaining installation and recovery gates stay open.

The next candidate's SDK adapter boundary is implemented in
`tools/ci/native_path_probe.py`. It retains the original Path classes and scopes
four descriptor changes to construction, lazy parts, rendering and derived
paths. It authenticates a closed set of actual CPython 3.12 method bodies and
pins live code-object identities, globals and class cells separately. Its C
entry points retain only bounded immutable lexical strings and tuples;
every Path object and mutable list must remain fresh. Mutable SDK hooks must
be admitted on every call, and no filesystem or validation result is retained.

The candidate adds `path_plan` and `path_call` to the existing authenticated C
extension. Every supported call checks the actual Root PID/thread and current
raw MRO descriptors, function code, cells and namespace bindings before and
after computation. Unsupported input executes the original SDK before any
mutation; native errors are not retried. Filesystem methods remain original.
The 256-entry cache contains only immutable parsed lexical strings/tuples;
new paths and mutable lists are fresh, and closing clears the cache and drops
the native capsule, including after interruption.

Thirty-two portable checks cover this boundary, including SDK/POSIX source
authentication, lazy slots, mutable isolation, metadata hooks, live code and
class cells, partial installation, restoration and pending-error precedence.
The comparison cases also verify twenty alternating pairs, equal observations,
positive counts for every role, zero fallback, and source custody before effects.
They use a test double and deterministic fixture clocks, so establish no C
execution or speedup. Eleven actual Linux Root cases add SDK value/error/cache and
mutation checks plus a third complete original 372-case Root suite.

The existing hosted workflow builds the candidate, runs all retained metadata
and read cases, then the new Root cases. Full proof now records
`native_path_comparison` from twenty same-actor whole-guard pairs before the
original stage measurements. Descriptors and source custody are restored and
lexical plans cleared before effects; all seventeen timers, CPU windows,
existing guard-ten sample, actors, complete archive and deadlines are retained.
The unchanged benefit gate requires median ratio at most 0.80 and at least
18 of 20 faster prototype samples. Exact review of candidate `06f6c5f` verified
all 37 metadata, 39 read and 43 Path cases, three original 372-case Root suites,
82 ownership fixtures and 59 installed production source hashes. The twenty
alternating whole-guard pairs rejected the lexical candidate: median ratio
1.766213, zero of twenty faster, baseline median 24.648 ms and prototype median
43.732 ms. Every role was exercised with zero fallback and equal observations;
original classes/descriptors were retained/restored and the immutable cache
cleared before effects. Full staging still timed out at 240157 ms in Root and
240295 ms in the ordinary controller, with zero output checks on the complete
9409-member, 159520534-byte archive. The subsequent exclusion-client refusal
does not independently establish the primary timeout cause. This backend is
rejected; do not repeat its unchanged pairs, baseline-only stage or profile.

Ubuntu's `ntpath-import.diff` changes the original constructor: it imports
`ntpath` locally and omits that global from `pathlib`. The closed SDK contract
admits that exact additional body. For this variant only, native construction
and derived paths perform the same absolute import with the original SDK
globals; the module result is not cached. The import hook and current
`sys.modules` binding are admitted afresh. Changed hooks or a missing module
execute the original SDK before any import or slot mutation in the C lane.
Portable checks cover the absent global, exact source body and late hook error;
the additional Root case requires a supported native call and original import
observations, exceptions and argument mutation when import metadata changes.
The native lane admits the original module/spec identity, generic metadata
lookup and a plain false initialization flag afresh. Changed metadata executes
the whole original SDK before any C import or slot mutation; this preserves
callbacks that change path arguments before the SDK copies them.

The next diagnostic uses C-bound instance methods for all four lexical roles,
removing the Python wrapper and `path_call` round trip. `DescriptorAdapter` in
`tools/ci/native_path_probe.py` authenticates the same closed SDK bodies and
prepares finite code inputs. The C `descriptor_plan`, `descriptor_entries` and
one-shot `descriptor_bind` APIs create opaque contexts and four SDK descriptors.
Actual SDK classes and every filesystem method stay original. The existing
lexical implementation and 43-case suite remain as regression coverage.

Each installed scope registers CPython 3.12 dictionary notifications before
fresh full namespace/MRO admission. Notifications only set a negative
invalidation flag: no Python, allocation, exception changes or I/O. Relevant
module/class keys include absent inherited shadows and import metadata;
unrelated dictionary writes do not disable the lane. Clearing/cloning a watched
dictionary conservatively invalidates it. A changed input disables native
handling for the rest of that scope, including after the binding is restored.
Every operation still checks original Root credentials, PID, thread and
interpreter, current function code/globals/builtins/defaults/closure/vectorcall,
class cells, type/MRO/slot fields, module types and import-spec dictionary
identity. These are code inputs only; no Root or filesystem admission result,
observation, database read or effect authorization is retained.

`descriptor_phase` unregisters notifications before Python restores all touched
SDK descriptors on every exit. Closing clears immutable lexical entries and
releases code-input reference cycles. Saved methods after close execute the
original SDK; foreign-thread calls use original fallback. Bounded counters
separately witness C entries, supported calls and fallbacks. Native errors are
never retried. A comparison requires positive equal entry/call counts in all
four roles, zero fallback, equal original observations, descriptor restoration,
watcher removal and fresh source custody before effects.

`tools/ci/native-descriptor-test.py` adds eight portable scope contracts and twelve
actual hosted Linux Root cases. The latter cover C descriptor identity and
values, immutable-cache bounds and fresh lists, original metadata reads,
permanent dictionary invalidation, inherited shadows/noninterned keys,
function/default/cell changes, module-class hooks, constructor import metadata
and argument callbacks, spec-dictionary replacement, foreign threads, saved
methods, interruption, one-shot/nested lifecycle refusal, and a fourth complete
original 372-case Root suite, plus same-process/thread real/effective UID/GID
changes in an isolated child prepared after fork. Portable fixtures establish no C execution or
speedup. Full proof now records `native_descriptor_comparison`; it retains the
same twenty alternating original-actor guard pairs and 0.80/18 benefit gate,
seventeen timers, CPU windows, guard-ten diagnostic, actors, two Root observation
passes, complete archive, guard counts and production deadlines. The bound
descriptor implementation remains unverified until exact hosted review. Full
uninstrumented staging/output/runtime, listener/provisioning, interrupted-effect
reconciliation, installation and actual replacement-host restore remain open.

Review of the first bound-descriptor source found four missing POSIX inputs:
`posixpath.os`, `posixpath._get_sep`, `builtins.map` and `builtins.bytes`.
`join`, `splitroot` and the separator helper read these bindings even for exact
strings. The revised finite contract authenticates the separator body, original
module and builtin types, and watches all four bindings plus the helper's live
code. Additional portable custody and actual Root callback/error cases require
original behavior after every mutation, including an in-place helper-code
change that produces no dictionary event. The first hosted run was superseded
for this source repair; cancellation establishes no native semantics or benefit.

Exact review of the repaired bound-descriptor candidate `c8dc05b` verified all
19 descriptor cases, 43 Path cases, 37 metadata cases, 39 read cases, four
complete original 372-case Root suites, 82 ownership fixtures and 59 installed
production hashes. The unchanged twenty-pair gate rejected it: median ratio
1.500036, zero of twenty faster, baseline median 16.430 ms and prototype median
24.618 ms. All four C entry counts equaled supported calls, fallback was zero,
observations matched, descriptors were restored and watchers/cache cleared.
These within-run values do not establish improvement over another host's earlier
candidate. Root staging still timed out at 240164 ms; the ordinary controller
timed out at 240268 ms, with zero output checks on the same complete archive.
No unchanged paired, baseline-only staging or profiling rerun is warranted.

The next candidate removes a duplicate owner query immediately before the full
descriptor admission. It uses `getresuid` and `getresgid` to read the same four
real/effective UID/GID fields freshly, while retaining PID and thread checks.
The full admission still checks ownership before any SDK slot read/mutation or
import, and ownership remains checked after computation and before imports.
Legacy admission remains in place. No credential, admission or observation
result survives a call. The additional actual Root case prepares its context
after fork so PID loss cannot conceal a credential-check defect, changes each
of the four fields without changing the context's PID/thread, verifies original
fallback with no native/cache activity, restores credentials, and verifies native
handling resumes. It changes only the owned child, which reports bounded results
and exits; no user application or service credentials are changed.

Preparation now authenticates the canonical immutable `super` and
`AttributeError` builtin classes before invoking the SDK or creating a plan.
Their existing live binding rows already detect changes after preparation;
the new portable cases cover changes before it. Helper preparation calls its
known base initializer directly so it cannot execute a changed `super` first.
This revision totals 20 descriptor cases. Hosted credential behavior and benefit
remain unverified; the preceding candidate remains rejected. The original
whole-guard gate, archive, actors, two Root passes, guards and deadlines remain
unchanged, as do all eight existing observation implementations.

Exact review of identity-query candidate `89c77d5` verified all 20 descriptor
cases, including the four credential-field changes, and every retained
43/37/39-case Path/metadata/read scope, four original 372-case Root suites,
82 ownership fixtures and 59 installed production hashes. It still failed the
unchanged benefit gate: median ratio 1.206218 with zero of twenty faster,
baseline median 30.4775 ms and prototype median 36.683 ms. Root staging timed
out at 240205 ms and the ordinary controller at 240398 ms, with zero output
checks on the same complete archive. This backend is rejected. The values are
within that run; they do not measure improvement across different hosted CPUs.
No unchanged paired, baseline-only staging or profiling dispatch is justified.

The next work moves lexical preparation inside complete native observation
roles. The existing read boundary still constructs/converts SDK paths, parts
and parents in Python before `read_file`; C `prepare_plan`/`prepare_custody`
also call original SDK methods through `lexical_path`, `path_rows`,
`parent_descriptor`, names and equality/hash lookups. These are source-derived
boundary costs, not independently timed subcost attribution. The planned
replacement must cover all eight existing observation families and all four
lexical operations together. It must retain fresh role admission, existing
ordered filesystem observations and original SDK classes outside those roles.
No Root admission or observation result may be cached.

The complete-role candidate now prepares arguments and dispatches the eight
original C observation implementations through one scoped code context in
`tools/ci/native_role_probe.py`. SDK classes and descriptors remain original.
Its finite schema includes parent iteration, path properties, raw MRO
descriptors, function defaults and closure cells. Changed code inputs decline
before observations; a refusal or error after dispatch never retries through
the original body. Constructor imports precede copying mutable raw arguments,
and invalid user-written string caches decline before Unicode access.

Twenty portable cases cover dispatch, default and SDK contracts, original-method
preservation, aliases imported during a scope, source-custody failure, partial
binding and interrupted cleanup. They pass locally using test doubles and do
not establish C execution. Twenty additional hosted Root cases reuse the
existing file, custody, descriptor-loss and restored-mtime fixtures, exercise all
eight roles and four lexical witnesses, and run the original 372-case Root
suite under this boundary. These hosted cases are unverified until their actual
run is reviewed. The legacy 20/43/37/39 descriptor/Path/metadata/read cases and
their four original Root suites remain required.

Full proof selects `native_role_comparison`: twenty alternating whole-guard
pairs on the original actors, positive role/lexical witnesses, zero fallback,
equal observations, fresh source custody and cleared contexts before effects.
The benefit gate remains median prototype/baseline at most 0.80 and at least
18 of 20 faster pairs. The full archive, seventeen method timers, calling-thread
CPU and guard-ten sample, two Root passes and production deadlines are unchanged.
Compilation, hosted semantics and benefit remain unverified. Full uninstrumented
staging/runtime and all installation/recovery gates remain open.
