# Native application ownership handoff

Implementation under [decision 0018](../decisions/0018-native-supervision-generations.md).
`Gitgood.NativeOwnershipClaim.claim/4` connects the captured local generation monitor,
the original non-retrying database lease, the record constructor and the fixed
protected publisher. It accepts two distinct live local PIDs and one fixed runtime
or maintenance mode. It resolves no process name and starts no replacement helper.

The handoff obtains fresh ownership context and a checked original session snapshot,
constructs the bounded record, calls the protected publisher and attaches its receipt
to the same monitor. Both original helpers must still pass their current checks
before success returns. The supplied seal map grants no authority: the protected
publisher must observe its actual Root seal and original service/session/storage.

There is one attempt. A failure may follow immutable-record or marker retention;
the caller must end the startup owner and preserve those effects for independent
controller reconciliation. This function removes nothing, reconnects nothing and
provides no retry, replacement, lifecycle or functional-readiness decision. Calling
it again is not an ownership-attachment retry protocol.

Four process-protocol tests cover early monitor refusal, lost original session,
dead/aliased/unsupported helper inputs and invalid captured values. Their helpers
are explicit GenServer stand-ins. All four pass in a standalone Elixir runner using
Root's retained dependency copy without changing its permissions. Successful installed
publication and attachment are not established by them. The full backend precommit
passes 248 tests as the ordinary installation test user in an isolated source copy
and a fresh database. All 336 backend and deployment source files match the tested
copy byte for byte. Installed handoff execution and required GitHub CI on this
branch remain pending.

The application must ultimately execute this handoff before any pooled database,
listener, reconciler or mutation worker starts, inside the permanent ownership tree
that ends the whole BEAM on helper loss. That startup integration, actual installed
handoff, prior-owner reconciliation and lifecycle/controller work remain required.
The native application gate stays closed.
