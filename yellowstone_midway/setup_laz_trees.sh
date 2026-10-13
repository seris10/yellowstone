#!/bin/bash
# Instructions for setting up and running the Yellowstone LAZ tree detection

# Step 1: Install Python dependencies
# The script requires laspy[lazrs], numpy, scipy, and rasterio

echo "1. Installing Python dependencies..."
pip install "laspy[lazrs]" numpy scipy rasterio

echo "2. Running Yellowstone LAZ tree detection script..."
echo "   The script will use URLs from /Users/kreed/Downloads/downloadlist.txt"
echo "   Downloading and processing LAZ files..."

# Run the processing script
python3 scripts/process_laz_trees.py

echo "Setup and processing complete!"

echo ""
echo "The script will:
- Download 20 LAZ files from USGS (total ~1.4GB)
- Process only points within project bounds (-2028 to 2028 in X/Z)
- Detect tree tops using clustering algorithms
- Estimate tree heights
- Export tree placements to data/placements_from_lidar.json

This replaces the sparse 30,000 algorithmic tree placements with
~50,000-100,000 real tree locations based on LiDAR data.

The placements will be in the same format as data/placements.json,
so they can be used directly in your Godot project.
"