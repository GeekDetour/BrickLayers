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

$PYTHON_RUNTIME $BRICKLAYERS ../sample_gcode/Sample_BrickLayersChallengeSimple_5walls.gcode \
	-outputFile ../sample_brick/SampleBrickLayersChallengeSimple_5walls_brick.gcode \
	-extrusionMultiplier 1.05 \
	-verbosity 1


$PYTHON_RUNTIME $BRICKLAYERS ../sample_gcode/Sample_3DBenchy_5walls_classic.gcode \
	-outputFolder ../sample_brick/ \
    -outputFilePostfix _brick \
	-extrusionMultiplier 1.05 \
	-startAtLayer 3 \
	-ignoreLayers \
	-ignoreLayersFromTo \
	-enabled 1 \
	-verbosity 2
