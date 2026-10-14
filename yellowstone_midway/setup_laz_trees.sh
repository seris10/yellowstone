#!/bin/bash
# Installs the tree detection dependencies and runs the detection script.
set -euo pipefail

pip install "laspy[lazrs]" numpy scipy rasterio
python3 scripts/process_laz_trees.py