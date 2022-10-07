#!/usr/bin/env

function requires () {
	for CMD in $1; do
		if [ -z "$(which $CMD 2> /dev/null)" ]; then
			echo "!!! ERR Could not find tool: $CMD"
			exit 1
		fi
	done
}

requires ab python readlink
BASE=$(dirname $(readlink -f $0))
LOG=$(mktemp --suffix .log benchmark-log-XXX)
SUMMARY=
for TEST in $BASE/benchmark-*.py; do
	echo ""
	echo "001 DO> Running server $TEST, logging to $LOG"
	python $TEST 2> $LOG  &
	CPID=$!
	sleep 1
	echo "002 DO> Running Benchmark"
	OUTPUT="$(ab -n10000 -c100 http://localhost:8000/ | tr '\n' '^')"
	RESULT=$?
	if [ "$RESULT" != "0" ]; then
		echo "!!! ERR Benchmark failed: $OUTPUT"
		echo ">>> START Server log"
		cat $LOG
		echo "<<< END Server log"
		SUMMARY="$SUMMARY\n$(basename $TEST)	N/A"
	else
		RPS="$(echo $OUTPUT| tr '^' '\n' | grep 'Requests per second' | cut -d: -f2 | cut -d'[' -f1 )"
		echo "=== OK! Benchmark '$(basename $TEST)' succeeded: $RPS requests/s)"
		SUMMARY="$SUMMARY;$(basename $TEST)	$RPS"
	fi
	if ps -p $CPID > /dev/null; then
		kill -9 $CPID  &> /dev/null
	fi
done
if [ -e $LOG ]; then
	unlink $LOG
fi
echo "==="
echo $SUMMARY | tr ';' '\n'
echo "EOS"

# EOF
