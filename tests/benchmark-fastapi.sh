BASE=$(dirname $(readlink -f $0))
if [ -z "$(which uvicorn)" ]; then
	echo "ERR Could not find command: 'uvicorn'"
	exit 1
fi
#env PYTHONPATH=$BASE:$PYHTONPATH uvicorn benchmark_fastapi:app 2> /dev/null
echo POUET
exit $?
# EOF
