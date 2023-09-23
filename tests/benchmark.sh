#!/usr/bin/env bash

function requires() {
	for CMD in $1; do
		if [ -z "$(which $CMD 2>/dev/null)" ]; then
			echo "!!! ERR Could not find tool: $CMD"
			exit 1
		else
			echo "... Using: $CMD"
		fi
	done
}

# TODO: We should have the option of  running the benchmark in client or server mode maybe?
echo "=== Extra benchmark"
requires ab python readlink
BASE=$(dirname $(readlink -f $0))
LOG=$(mktemp --suffix .log benchmark-log-XXX)
SUMMARY=
TESTS=$@
if [ -z "$@" ]; then
	TESTS=$BASE/benchmark-*.??
fi
for TEST in $TESTS; do
	echo ""
	echo "001 DO> Running server $TEST, logging to $LOG"
	EXT="$(echo -n $TEST | tail -c3)"
	case $EXT in
	.py)
		python $TEST 2>$LOG &
		CPID=$!
		;;
	.sh)
		bash $TEST 2>$LOG &
		CPID=$!
		;;
	*)
		echo "ERR Unsupported benchmark suffix: $EXT in $TEST"
		CPID=$!
		;;
	esac
	if [ -z "$CPID" ]; then
		echo WTF
		exit 1
	else
		if ps -p "$CPID" >/dev/null; then
			sleep 1
		fi
	fi
	echo "002 DO> Running Benchmark: request=10000 concurrency=100"
	OUTPUT="$(ab -n10000 -c100 http://localhost:8000/ | tr '\n' '^')"
	RESULT=$?
	if [ "$RESULT" != "0" ]; then
		echo "!!! ERR Benchmark failed: $OUTPUT"
		echo ">>> START Server log"
		cat $LOG
		echo "<<< END Server log"
		SUMMARY="$SUMMARY\n$(basename $TEST)	N/A"
	else
		RPS="$(echo $OUTPUT | tr '^' '\n' | grep 'Requests per second' | cut -d: -f2 | cut -d'[' -f1)"
		echo "=== OK! Benchmark '$(basename $TEST)' succeeded: $RPS requests/s)"
		SUMMARY="$SUMMARY;$(basename $TEST)	$RPS"
	fi
	if ps -p $CPID >/dev/null; then
		pkill -P $CPID &>/dev/null
	fi
done
if [ -e $LOG ]; then
	unlink $LOG
fi
echo "==="
echo $SUMMARY | tr ';' '\n'
echo "EOS"

# EOF
