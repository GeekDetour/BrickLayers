#!/bin/bash
if hash pypy3 2>&1 >/dev/null
then
    PYTHON_RUNTIME=pypy3
elif hash python3 2>&1 >/dev/null
then
	PYTHON_RUNTIME=python3
fi
BRICKLAYERS=../bricklayers.py

echo "using $PYTHON_RUNTIME"

for i in ../sample_gcode/*.gcode ; do 
  [[ -f "$i" ]] || continue
  $PYTHON_RUNTIME $BRICKLAYERS $i \
	-outputFolder ../sample_brick/ \
    -outputFilePostfix _brick \
	-extrusionMultiplier 1.05 \
	-verbosity 1
done


