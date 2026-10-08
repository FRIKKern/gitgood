# Local identity for the first native slice
Accepted for the standalone forge boundary, 8 October 2026. Cloud and Barkpark attribution remain D02 experiments.

Gitgood owns local actors and team membership. Installation operators provision actors through a local bootstrap command.
There is no public signup or shared writer identity. Session credentials are opaque random values; Postgres stores only their SHA-256 digests, expiry and revocation.
Password verification uses PBKDF2-HMAC-SHA256 with individual random salts and 600,000 iterations through OTP crypto, avoiding a platform-specific native build dependency for this first portable experiment.
Argon2id and algorithm migration remain a production-hardening decision; this choice makes no FIPS compliance claim.
Reference: [OWASP password storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

Browser cookies are HttpOnly, SameSite Strict and Secure for HTTPS origins. Cookie mutations require a session-bound CSRF token; supplied origins must match the configured web origin.
Bearer credentials are separated by session/Git/check kind. Membership is looked up by the backend for every repository request.
Cloud billing identities confer no repository role. Barkpark integration must preserve the individual actor through its supported API and remains unconfigured.

Repository creation commits a uniquely keyed intent row before initializing a UUID-named Git store.
Concurrent retries lock the row; a failed initialization retains visible responsibility and retries/reconciliation converge on the same repository.
There is no billing step in this slice. Creation acceptance does not imply general Git/DB merge recovery.
