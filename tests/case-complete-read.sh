#!/usr/bin/env bash
BASE="$(dirname "$(dirname "$(readlink -f "$0")")")"

function run-case() {
	echo "[test]   === CASE $1"
	python3 "$BASE/tests/case-complete-read-$1.py" &
	local server_pid="$!"
	sleep 1
	python3 "$BASE/tests/case-complete-read-client.py"
	local result="$?"
	kill -9 "$server_pid"
	if [ "$result" == "0" ]; then
		echo "[test]   EOK"
	else
		echo "[test]   EFAIL"
	fi
}

if [ -z "$1" ]; then
	run-case asyncio
	run-case aiohttp
	run-case extra
else
	run-case "$1"
fi
# EOF
