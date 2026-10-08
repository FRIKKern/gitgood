# Git compatibility experiment

This M4 experiment extends D04 with real client observations on the native forge. It is in progress; the matrix below defines checks, not completed support claims. Keep the current pinned Git versions, native candidate, normal TLS issuer verification and strict SSH host-key identity in each receipt.

| Behavior | Required observation |
|---|---|
| SHA-1 repositories | Exact commits, trees and tag objects survive HTTPS protocol versions 0, 1 and 2. |
| Shallow clients | Depth-one clone, deepen and unshallow recover the expected ancestry over HTTPS; SSH clone/deepen preserves the same commits. |
| Submodules | Preserve gitlink and `.gitmodules`; fetching the separate repository requires its own scoped credential. Native browsing identifies the gitlink without borrowing parent access. |
| Signed commits/tags | Preserve exact signed objects. An independent client verifies against its explicit allowed-signers file. This does not assign native signer trust or a verified badge. |
| Partial clone | Observe current server capabilities and the client's full-clone fallback; do not claim filtered-object hosting from a successful fallback. |
| Git LFS | Preserve pointer blobs as ordinary Git content; the external media/batch service is outside the current hosting profile. Import does not claim to transfer that media. |
| SHA-256 repositories | Incompatible push is refused with existing SHA-1 refs unchanged; do not claim mixed-format hosting. |

These experiments refine the compatibility decision already required by PRODUCT.md. They do not add hosted execution, a signature trust service, LFS media storage or automatic submodule migration. Their absence must be explicit before M4 acceptance. No required behavior is marked passed by this document.

Use isolated synthetic repositories and ordinary scoped native APIs. Record runtime/client versions, exact refs and object digests, credential boundaries and observed limitations. Larger repositories, other client implementations and measured performance remain separate work.
