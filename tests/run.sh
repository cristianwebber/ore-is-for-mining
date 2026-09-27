#!/usr/bin/env bash
# Runs every scenario against real Factorio prototype data.
# usage: tests/run.sh [factorio-data tag ...]   (default: 2.0.77 2.1.20)
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cache="$root/tests/.factorio-data"
versions=("$@")
[ ${#versions[@]} -eq 0 ] && versions=(2.0.77 2.1.20)

scenarios=(
  base-defaults
  space-age-defaults
  rails-allowed
  splitters-disallowed
  fluids-unrestricted
  extra-allowed-setting
  mod-interface
)

for f in "$root"/*.lua; do
  luac -p "$f"
done

passed=0
failed=0
for version in "${versions[@]}"; do
  fd="$cache/$version"
  if [ ! -d "$fd" ]; then
    echo "Fetching factorio-data $version..."
    git -c advice.detachedHead=false clone -q --depth 1 --branch "$version" https://github.com/wube/factorio-data.git "$fd"
  fi
  for scenario in "${scenarios[@]}"; do
    if output="$(cd "$root" && lua tests/scenario.lua "$fd" "$scenario" 2>&1)"; then
      echo "PASS $version $scenario"
      passed=$((passed + 1))
    else
      echo "FAIL $version $scenario"
      echo "$output"
      failed=$((failed + 1))
    fi
  done
done

echo
echo "$passed passed, $failed failed"
[ "$failed" -eq 0 ]
