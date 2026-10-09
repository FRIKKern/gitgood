# Bounded criterion evidence history

This work addresses a resource gap in the first linked-task evidence profile. A link can retain 1,000 immutable results and each result can retain 1,000 withdrawal events. Returning every manifest and event during each five-second browser refresh would make a permitted history needlessly expensive. Existing artifacts and historical records must remain available to authorized viewers.

Implementation is in progress. The intended contract is:

- Criterion states always use the latest result for each criterion across the whole link history, independently of the selected history page. An older visible pass never overrides a newer failed, inconclusive, stale or unavailable result.
- A response contains at most 20 evidence records, with a stable link-bound cursor to older records. Each record contains at most 25 withdrawal events; a separately authorized endpoint pages the remainder.
- Cursors identify positions within a single authorized link or evidence record. Reusing a cursor from another link or record is refused. Cursor position does not confer permission.
- Artifact bytes remain outside history queries. Event counts determine availability without loading every reason into application memory. Historical source metadata remains hidden if the current viewer loses source or native access.
- The browser navigates history explicitly and preserves current criterion state. It does not silently choose an older result when the current result is absent from the selected page.

The immutable storage limits remain unchanged. Pagination is a response/resource boundary; it is not a measured capacity or latency claim. Verification must cover records beyond the first page, older-event access, cursor isolation, latest-result state and both permission owners before this work is considered implemented.

Evidence text excludes NUL bytes. PostgreSQL cannot store NUL in text or JSONB metadata; commands, environment fields, producer labels and withdrawal reasons must refuse it before reaching storage. The text-artifact profile follows the same boundary, and the browser identifies a NUL-containing file as unsupported binary content. This closes a reproduced database exception without changing custody of existing records.
