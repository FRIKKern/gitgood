#!/bin/bash
set -euo pipefail
umask 077
uid="$(id -u)"
test "$uid" -ne 0
test "$#" = 1
workspace="${GITHUB_WORKSPACE:?GitHub workspace is required}"
test "$workspace" != /
test -d "$workspace"
test ! -L "$workspace"
test "$(realpath "$workspace")" = "$workspace"
test "$(stat -c %u "$workspace")" = "$uid"
prefix="$1"
test "$prefix" = "$workspace/.gitgood/postgres-18.4"
test ! -e "$prefix"
test ! -L "$prefix"
parent="$(dirname "$prefix")"
test ! -L "$parent"
if test -e "$parent"; then
  test -d "$parent"
  test "$(stat -c %u "$parent")" = "$uid"
fi
mkdir -p "$parent"
test "$(realpath "$parent")" = "$parent"
test "$(stat -c %u "$parent")" = "$uid"
test "$(uname -m)" = x86_64
. /etc/os-release
test "$ID" = ubuntu
test "$VERSION_ID" = 24.04
build="$(mktemp -d "$parent/postgres-build-XXXXXX")"
curl -fsSL --retry 2 https://ftp.postgresql.org/pub/source/v18.4/postgresql-18.4.tar.gz -o "$build/postgresql-18.4.tar.gz"
printf '%s  %s\n' '450aa8f2da06c46f8221916e82ae06b04fb1040f8f00643dbf8b7d663caac0b9' "$build/postgresql-18.4.tar.gz" | sha256sum --check
tar -xzf "$build/postgresql-18.4.tar.gz" -C "$build"
cd "$build/postgresql-18.4"
./configure --prefix="$prefix" --without-readline --without-icu --with-openssl --with-zlib --without-lz4 --without-zstd
make -j2
make install
test "$("$prefix/bin/postgres" --version)" = 'postgres (PostgreSQL) 18.4'
test "$("$prefix/bin/pg_dump" --version)" = 'pg_dump (PostgreSQL) 18.4'
test "$("$prefix/bin/pg_restore" --version)" = 'pg_restore (PostgreSQL) 18.4'
echo 'PASS pinned PostgreSQL 18.4 server and recovery clients built on Ubuntu 24.04'
