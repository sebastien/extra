#!/usr/bin/env bash
set -euo pipefail
BASE=$(dirname "$(readlink -f "$0")")
if ! command -v uvicorn >/dev/null 2>&1; then
	echo "ERR Could not find command: 'uvicorn'"
	exit 1
fi
PORT="${HTTP_PORT:-${PORT:-8000}}"
HOST="${UVICORN_HOST:-0.0.0.0}"
exec env PYTHONPATH="${BASE}${PYTHONPATH:+:$PYTHONPATH}" \
	uvicorn --host "$HOST" --port "$PORT" --log-level warning benchmark_raw:app
# EOF
