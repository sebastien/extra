#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
BASE="$(dirname "$(readlink -f "$0")")"

exec "$PYTHON" "$BASE/benchmark.py" "$@"

# EOF
