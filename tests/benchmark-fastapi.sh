#!/usr/bin/env bash
BASE=$(dirname $(readlink -f $0))
if [ -z "$(which uvicorn)" ]; then
	echo "ERR Could not find command: 'uvicorn'"
	exit 1
fi
env UVICORN_HOST=0.0.0.0 PYTHONPATH=$BASE:$PYHTONPATH uvicorn benchmark_fastapi:app 
# EOF
