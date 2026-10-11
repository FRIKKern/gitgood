# Native retirement input fixture cleanup

The ordinary-user operator run on `4c3950b` completed 457 tests with two failures
in disposable database cleanup and 18 platform skips. Both failing tests had
completed their input-refusal assertions. A separate six-test diagnostic captured
PostgreSQL canceling a `dropdb` statement at the fixture's five-second statement
limit. The underlying delay remains unmeasured; failed runs are retained.

The input fixture now uses the existing production retirement command's ten-second
statement and five-second lock bounds for administrative cleanup, within the
unchanged fifteen-second child deadline. It first independently reobserves the
exact database identity. It uses the catalog search path and performs no force
drop, session termination or retry. Creation, observations, product commands,
input-refusal assertions and their deadlines are unchanged.

This cleanup is separate from the actual retirement database-removal tests.
Passing these component tests establishes neither installed retirement nor J17
acceptance. The complete operator suite and required CI still need current
results against the changed candidate.
