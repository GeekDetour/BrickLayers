#!/bin/bash
if hash pypy3 2>&1 >/dev/null
then
    PYTHON_RUNTIME=pypy3
elif hash python3 2>&1 >/dev/null
then
	PYTHON_RUNTIME=python3
fi
BRICKLAYERS=./bricklayers.py

echo "using $PYTHON_RUNTIME"

$PYTHON_RUNTIME $BRICKLAYERS "$@"