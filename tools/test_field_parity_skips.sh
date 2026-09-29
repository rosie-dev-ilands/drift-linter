#!/usr/bin/env bash
# Regression for the v0.1.28 field_parity skip-guard fixes (Arkaon FT, 09-29):
#   1. a filename containing " (could not parse" must not defeat the JS guard
#   2. a Python-side skip must not be invisible on a successful run
# Run: bash tools/test_field_parity_skips.sh
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0

expect() { # $1 description, $2 tree, $3 expected exit code
  node "$HERE/web/field_parity.js" "$2" >/dev/null 2>&1
  got=$?
  if [ "$got" != "$3" ]; then
    echo "FAIL $1: exit $got, wanted $3"
    fail=1
  else
    echo "ok   $1"
  fi
}

# 1. JS engine skips (except*), Python parses -> must fail loud, even when the
#    filename itself contains the note text the guard used to regex for.
mkdir -p "$TMP/name"
printf 'try:\n    x = 1\nexcept* ValueError:\n    pass\n' > "$TMP/name/x (could not parse.py"
expect "filename cannot defeat the JS skip guard" "$TMP/name" 1

# 2. Neither engine can parse -> a fair two-sided skip, still passes.
mkdir -p "$TMP/fair"
printf 'def f(:\n    pass\n' > "$TMP/fair/broken.py"
expect "fair two-sided skip still passes" "$TMP/fair" 0

# 3. Python engine skips (null byte), JS engine scans -> must fail loud instead
#    of printing PARITY OK over a half Python scan.
mkdir -p "$TMP/py"
printf 'x = 1\n\x00\n' > "$TMP/py/nullbyte.py"
expect "Python-side skip is not invisible on success" "$TMP/py" 1

if [ "$fail" = 0 ]; then echo "all field_parity skip-guard checks passed"; fi
exit $fail
