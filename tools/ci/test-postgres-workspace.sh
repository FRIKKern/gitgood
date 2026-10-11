#!/bin/bash
set -euo pipefail

# Exercise the real installer guards, stopping before platform checks or downloads.
installer="$(realpath "$(dirname "${BASH_SOURCE[0]}")/install-postgres-18.4.sh")"
fixture_parent="$(realpath "${TMPDIR:-/tmp}")"
fixtures="$(mktemp -d "$fixture_parent/gitgood-pg-workspace-XXXXXX")"
cleanup() {
  local result=$?
  if [[ "$fixtures" = "$fixture_parent"/gitgood-pg-workspace-* ]] &&
    test "$(dirname "$fixtures")" = "$fixture_parent" &&
    test -d "$fixtures" && test ! -L "$fixtures" &&
    test "$(realpath "$fixtures")" = "$fixtures"; then
    rm -rf -- "$fixtures"
  else
    printf 'Refusing cleanup outside the owned canonical fixture directory\n' >&2
    return 1
  fi
  return "$result"
}
trap cleanup EXIT
mkdir "$fixtures/bin" "$fixtures/workspace with spaces" "$fixtures/other"
workspace="$fixtures/workspace with spaces"
cat > "$fixtures/bin/uname" <<'SH'
#!/bin/bash
printf 'WORKSPACE_GUARD_PASSED\n' >&2
exit 47
SH
cat > "$fixtures/bin/id" <<'SH'
#!/bin/bash
if test -n "${TEST_UID:-}"; then printf '%s\n' "$TEST_UID"; else /usr/bin/id "$@"; fi
SH
cat > "$fixtures/bin/stat" <<'SH'
#!/bin/bash
if test -n "${TEST_OWNER:-}"; then printf '%s\n' "$TEST_OWNER"; else /usr/bin/stat "$@"; fi
SH
chmod +x "$fixtures/bin/"*

check() {
  local expected="$1" label="$2" candidate_workspace="$3" candidate_prefix="$4"
  local output result
  set +e
  output="$(PATH="$fixtures/bin:$PATH" GITHUB_WORKSPACE="$candidate_workspace" bash "$installer" "$candidate_prefix" 2>&1)"
  result=$?
  set -e
  test "$result" -ne 0 # The platform sentinel always prevents an actual build.
  if test "$expected" = accepted; then
    [[ "$output" = *WORKSPACE_GUARD_PASSED* ]]
  else
    [[ "$output" != *WORKSPACE_GUARD_PASSED* ]]
  fi
  printf 'PASS %s\n' "$label"
}

prefix="$workspace/.gitgood/postgres-18.4"
check accepted 'owned canonical workspace with spaces' "$workspace" "$prefix"
check accepted 'existing owned parent' "$workspace" "$prefix"
check refused 'missing workspace' '' "$prefix"
check refused 'root workspace' / /.gitgood/postgres-18.4
check refused 'nonexistent workspace' "$fixtures/missing" "$fixtures/missing/.gitgood/postgres-18.4"
check refused 'noncanonical workspace' "$workspace/../workspace with spaces" "$workspace/../workspace with spaces/.gitgood/postgres-18.4"
check refused 'outside destination' "$workspace" "$fixtures/other/postgres-18.4"
check refused 'destination traversal' "$workspace" "$workspace/.gitgood/../postgres-18.4"
TEST_UID=0 check refused 'root execution' "$workspace" "$prefix"
TEST_OWNER=0 check refused 'foreign workspace owner' "$workspace" "$prefix"
mkdir "$prefix"
check refused 'existing installation' "$workspace" "$prefix"
rmdir "$prefix"
ln -s "$workspace" "$fixtures/linked-workspace"
check refused 'linked workspace' "$fixtures/linked-workspace" "$fixtures/linked-workspace/.gitgood/postgres-18.4"
ln -s "$fixtures/missing" "$prefix"
check refused 'dangling destination link' "$workspace" "$prefix"
unlink "$prefix"
rmdir "$workspace/.gitgood"
ln -s "$fixtures/other" "$workspace/.gitgood"
check refused 'linked parent' "$workspace" "$prefix"
test ! -e "$fixtures/other/postgres-18.4"
printf 'PASS PostgreSQL workspace refusal boundaries; no downloads or builds executed\n'
