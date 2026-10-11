# Native ownership SQL namespace

Native ownership checks must resolve PostgreSQL's actual catalogs and functions.
The installation database owner can create objects and configure its own search
path. A query's fixed text alone does not establish which objects it resolves.
PostgreSQL permits an explicit search path to place writable schemas before
`pg_catalog`; see the [PostgreSQL schema documentation](https://www.postgresql.org/docs/18/ddl-schemas.html#DDL-SCHEMAS-PATH).

The protected ownership observer preserves `search_path=pg_catalog` and
`default_transaction_read_only=on` when tightening its statement timeout to three
seconds. The original native lease connection supplies those same fixed startup
parameters and explicitly qualifies its advisory-lock function. Caller connection
options cannot replace them. The connection still has one session, stops on loss
and never reacquires a replacement lease.

An actual PostgreSQL experiment reproduced an unqualified advisory-lock function
returning true without holding a lock when a writable schema preceded the catalog.
The catalog-only search path acquired the real lock. The experiment used a
transaction and confirmed that its schema was absent after rollback. This
demonstrates namespace resolution. A second experiment created an ordinary
database owner with hostile role defaults, a shadow advisory-lock function and
a shadow lock view. The previous actual Elixir lease returned a valid snapshot
while the real catalog showed no lock. The repaired lease held the real lock;
the protected observer admitted that original session and refused it after the
lease stopped. Both BEAM sessions ended, no advisory lock remained, and the
isolated database fixture was retained privately.

These experiments do not establish complete ownership or installation acceptance.
Installed ownership, prior-owner reconciliation and Cloud deployment remain
required; the native application gate stays closed.
