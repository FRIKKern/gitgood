# Selected native systemd observations

The generation guard reads the same fifteen required Unit and Service properties
on every observation. Each value comes from a fresh typed D-Bus reply. A bounded
batch checks the originally captured Root-owned library and its parent custody
before and after all selected reads, and returns values only after the complete
batch succeeds. Manager version remains a separate live, bracketed read.

One missing property, wrong type, incomplete reply, library replacement or lost
connection permanently closes the original reader. No partial batch becomes an
observation, and no failed reader reconnects. The generation guard still brackets
its complete worker observations and checks the original identities and seals.

This avoids decoding unrelated properties returned by GetAll. It does not change
the required fields, freshness deadlines, startup limits or service resources.
Its effect on installed service timing needs a fresh native VM measurement.

Nineteen focused reader tests passed. An actual private D-Bus daemon exercised
two successive selected batches through the real libsystemd ABI, missing-property
and wrong-signature refusal, and permanent loss. Existing actual GetAll, unknown
property, array and connection-loss checks also passed against these bytes. The
fixture explicitly substitutes its endpoint and destination; it runs no systemd
manager or protected service and establishes no native application acceptance.

The preceding production VM failed maintenance freshness before ownership
publication. A separate timing VM has an explicitly overlaid diagnostic entry and
cannot establish production acceptance. Complete operator checks and a fresh
proof with the original protected entry remain prerequisites for installed native
application acceptance and activation. Integrating independently tested components
does not satisfy those gates or enable native startup.

The complete ordinary-user Linux operator suite passed: 452 tests with 18
platform-specific skips. Its private receipt records every current deployment
Python source checksum. All 33 planning checks passed. Backend source is unchanged
from the ownership-attachment candidate; these results do not establish installed
timing, publication, ownership attachment or complete journey acceptance.

The subsequent original-entry VM used frozen candidate `af30180`, the unchanged
30-second startup and three-second freshness limits, and the same bounded service
resources. Both native and maintenance owners reported five distinct increasing
heartbeats after actual generation admission. The native publication caller
received a retained receipt, then lost its generation monitor during ownership
attachment. No owned heartbeat, identical ownership retry or ownership reboot
check completed. The precise attachment failure remains under investigation.
The failed guest disk, seed, source, observations and private diagnostics are
retained; its original machine group is empty and its QEMU process is gone.
These observations do not establish installed timing or application acceptance.

A later passive BEAM receive trace retained an ownership-deadline expiry after
3,032 ms, with generation heartbeat age 2,598 ms. The initial ownership path is
being repaired by sharing its completed observation bracket with its immediate
acknowledgement. The selected D-Bus reader and all freshness/resource limits are
unchanged. This trace is separate from a passing installed ownership proof.

## Retained Root interface experiment

Root and ordinary-user service observations both use the selected-property path
above. An earlier Root-only interface-batching experiment passed its actual
system-manager comparisons but did not improve the bounded full staging run.
Its production selection was removed. Manager version remains a separate live
read; both complete unit observations and all original process, group, policy,
file and deadline checks remain. No reply is cached.

The retained dictionary decoder requires exact required variant types, unique
names, all required fields, complete framing and unchanged original library
custody. Other properties are skipped without becoming authority. A missing or
inaccessible required field still refuses, as the
[D-Bus property contract](https://dbus.freedesktop.org/doc/dbus-specification.html#standard-interfaces-properties)
allows inaccessible fields to be omitted. A failed second interface cannot
return the first one's partial result or reconnect the original reader.

Hosted Root decoder checks compare twenty actual Unit/Service reply pairs with selected
typed reads of the existing system-bus unit, then exercise missing fields and
wrong variants without changing that unit. These establish decoder behavior,
not an active production interface-batching path or full-stage timing. Fixed diagnostic timers remain separate
from the later uninstrumented complete-stage acceptance run.
