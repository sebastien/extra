#!/usr/bin/env bash
# set -euo pipefail

function requires() {
	for CMD in $1; do
		if [ -z "$(which "$CMD" 2>/dev/null)" ]; then
			echo "!!! ERR Could not find tool: $CMD"
			exit 1
		else
			echo "... Using: $CMD"
		fi
	done
}

ulimit -n 10000
# TODO: We should have the option of  running the benchmark in client or server mode maybe?
echo "=== Extra benchmark"
requires ab python readlink
PYTHON="${PYTHON:-python}"
echo "--- Using Python: $PYTHON"
BASE=$(dirname $(readlink -f "$0"))
LOG=$(mktemp --suffix .log benchmark-log-XXX)
SUMMARY=
TESTS=$@
if [ -z "$@" ]; then
	TESTS=$BASE/benchmark-*.??
fi
for TEST in $TESTS; do
	echo ""
	echo "001 DO> Running server $TEST, logging to $LOG"
	EXT="$(echo -n "$TEST" | tail -c3)"
	case $EXT in
	.py)
		echo ... "$PYTHON" "$TEST"
		$PYTHON "$TEST" 2>"$LOG" &
		CPID=$!
		;;
	.sh)
		echo ... bash "$TEST"
		bash "$TEST" 2>"$LOG" &
		CPID=$!
		;;
	*)
		echo "ERR Unsupported benchmark suffix: $EXT in $TEST"
		CPID=$!
		;;
	esac
	if [ -z "$CPID" ]; then
		echo "ERR Do not have a process id for the benchmark"
		exit 1
	else
		if ps -p "$CPID" >/dev/null; then
			echo "... Waiting for $CPID"
			sleep 1
		else
			echo "... Server ready at $CPID: $(ps -aux | grep $CPID)"
		fi
	fi
	echo "002 DO> Running Benchmark: request=10000 concurrency=100"
	OUTPUT_HTTP10="$(ab -n10000 -c1000 http://localhost:8000/ | tr '\n' '^')"
	OUTPUT_HTTP11="$(h2load -n10000 -c1000 -m1 --h1 http://localhost:8000/ | tr '\n' '^')"
	RESULT=$?
	if [ "$RESULT" != "0" ]; then
		echo "!!! ERR Benchmark failed: $OUTPUT"
		echo ">>> START Server log"
		cat "$LOG"
		echo "<<< END Server log"
		SUMMARY="$SUMMARY\n$(basename "$TEST")	N/A"
	else
		RPS_10="$(echo "$OUTPUT_HTTP10" | tr '^' '\n' | grep 'Requests per second' | cut -d: -f2 | cut -d'[' -f1)"
		RPS_11="$(echo "$OUTPUT_HTTP11" | tr '^' '\n' | grep 'finish' | cut -d' ' -f4)"
		echo "=== OK! Benchmark '$(basename "$TEST")' succeeded: $RPS_10 (HTTP 1.0) $RPS_11 (HTTP 1.1) requests/s)"
		SUMMARY="$SUMMARY;$(basename "$TEST")	$RPS_10 | $RPS_11"
	fi
	if ps -p $CPID >/dev/null; then
		echo "...Killing process: $CPID"
		kill -9 $CPID
	fi
	echo "...Recovering for 2s"
	sleep 2
done
if [ -e "$LOG" ]; then
	unlink "$LOG"
fi
echo "==="
echo "$SUMMARY" | tr ';' '\n'
echo "EOS"

# EOF
