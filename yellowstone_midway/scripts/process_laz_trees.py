#!/usr/bin/env python3
"""Yellowstone tree detection from LAZ point clouds.
Downloads from USGS, detects tree tops, exports placements in the project format.
"""

import os
import sys
import requests
import json
import numpy as np
from pathlib import Path
import laspy
from laspy import LasReader
from scipy.spatial import cKDTree
import rasterio
from rasterio.transform import from_origin
import traceback

# Configuration
DOWNLOAD_DIR = Path("data/laz_downloads")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR = Path("data")

# USGS LAZ download URLs for the Yellowstone project area.
LAZ_URLS = [
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_3_2020/LAZ/USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ120295.laz",
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_3_2020/LAZ/USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ120300.laz",
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_3_2020/LAZ/USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ120305.laz",
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_2_2020/LAZ/USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ120310.laz",
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_3_2020/LAZ/USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ125295.laz",
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_3_2020/LAZ/USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ125300.laz",
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_3_2020/LAZ/USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ125305.laz",
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_2_2020/LAZ/USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ125310.laz",
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_3_2020/LAZ/USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ130295.laz",
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_3_2020/LAZ/USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ130300.laz",
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_3_2020/LAZ/USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ130305.laz",
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_2_2020/LAZ/USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ130310.laz",
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_3_2020/LAZ/USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ135295.laz",
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_3_2020/LAZ/USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ135300.laz",
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_3_2020/LAZ/USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ135305.laz",
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_2_2020/LAZ/USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ135310.laz",
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_3_2020/LAZ/USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ140295.laz",
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_3_2020/LAZ/USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ140300.laz",
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_3_2020/LAZ/USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ140305.laz",
    "https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_2_2020/LAZ/USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ140310.laz",
]

# Project configuration
PROJECT_BOUNDS = {
    "min_x": -2028, "max_x": 2028,
    "min_z": -2028, "max_z": 2028,
    "min_y": 0, "max_y": 3000,
}

def download_laz_files():
    """Download LAZ files from USGS"""
    print("Downloading LAZ files...")
    downloaded_files = []
    
    for url in LAZ_URLS:
        filename = url.split('/')[-1]
        filepath = DOWNLOAD_DIR / filename
        
        try:
            print(f"  Downloading {filename}...")
            response = requests.get(url, stream=True, timeout=300)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"  Saved: {filepath}")
            downloaded_files.append(filepath)
            
        except Exception as e:
            print(f"  Error downloading {filename}: {e}")
    
    return downloaded_files

def read_laz_file(filepath):
    """Read LAZ file and return points with attributes"""
    try:
        with laspy.open(str(filepath)) as las:
            las = las[0]  # Read first table
            
            # Extract point data
            points = np.column_stack([
                las.x, las.y, las.z,
                las.classification,
                las.intensity,
                las.return_number,
                las.number_of_returns
            ])
            
            print(f"  Read {len(points)} points from {filepath.name}")
            print(f"  Bounding box: X[{las.x.min():.1f}, {las.x.max():.1f}] "
                  f"Z[{las.z.min():.1f}, {las.z.max():.1f}] Y[{las.y.min():.1f}, {las.y.max():.1f}]")
            
            return points, las
            
    except Exception as e:
        print(f"  Error reading {filepath}: {e}")
        return None, None

def filter_points_to_project(points, las, project_bounds):
    """Filter points to only include those within project bounds"""
    x, y, z = points[:, 0], points[:, 1], points[:, 2]
    
    # Apply project bounds
    mask = (
        (x >= project_bounds["min_x"]) & (x <= project_bounds["max_x"]) &
        (z >= project_bounds["min_z"]) & (z <= project_bounds["max_z"]) &
        (y >= project_bounds["min_y"]) & (y <= project_bounds["max_y"])
    )
    
    filtered_points = points[mask]
    print(f"  Filtered to {len(filtered_points)} points within project bounds")
    return filtered_points

def detect_treetops(points, las):
    """Detect treetop candidates from point cloud"""
    x, y, z, classification, intensity = points[:, 0], points[:, 1], points[:, 2], \
                                         points[:, 3], points[:, 4]
    
    # Keep medium and high vegetation (LAZ classes 4 and 5); drop ground (2) and low veg (3).
    valid_points = (classification == 4) | (classification == 5)
    
    if not np.any(valid_points):
        print("  No vegetation points found")
        return np.array([])
    
    veg_points = points[valid_points]
    print(f"  Found {len(veg_points)} vegetation points (class 4-5)")
    
    # Use clustering to identify tree tops
    tree = cKDTree(veg_points[:, :3])
    
    # Find points that are local maxima in Z within a neighborhood
    treetop_candidates = []
    radius = 5.0  # meters
    min_points = 5
    
    for i, point in enumerate(veg_points):
        neighbors = tree.query_ball_point(point[:3], radius)
        if len(neighbors) >= min_points:
            # Check if this point is the highest in the neighborhood
            neighborhood_z = veg_points[neighbors, 2]
            if z[i] == np.max(neighborhood_z):
                treetop_candidates.append(point)
    
    treetop_candidates = np.array(treetop_candidates)
    print(f"  Found {len(treetop_candidates)} treetop candidates")
    
    # Apply minimum height threshold
    min_height = 5.0
    treetop_candidates = treetop_candidates[treetop_candidates[:, 2] >= min_height]
    print(f"  After height filter: {len(treetop_candidates)} treetops >= {min_height}m")
    
    return treetop_candidates

def estimate_tree_height(treetop, las):
    """Estimate tree height from point cloud"""
    # Find ground points near the treetop
    x, y, z, classification = las.x, las.y, las.z, las.classification
    
    # Search for ground points (classification 2) near the treetop
    radius = 15.0
    treetop_x, treetop_y, treetop_z = treetop[:3]
    
    ground_mask = (
        (np.abs(x - treetop_x) <= radius) & 
        (np.abs(y - treetop_y) <= radius) & 
        (z <= treetop_z) & 
        (classification == 2)  # Ground
    )
    
    if np.any(ground_mask):
        ground_points = np.column_stack([x[ground_mask], y[ground_mask], z[ground_mask]])
        ground_tree = cKDTree(ground_points[:, :3])
        
        # Find the ground point closest to treetop
        dist, idx = ground_tree.query([treetop_x, treetop_y], k=1)
        ground_z = ground_points[idx[0], 2]
        
        height = treetop_z - ground_z
        return max(height, 5.0)  # Minimum height
    
    # Fallback to minimum height
    return 10.0

def create_placement_from_treetops(treetops, species="pine", variant=0):
    """Create placement dict from treetop candidates"""
    placements = []
    
    for i, treetop in enumerate(treetops):
        x, y, z = treetop[:3]
        
        # Estimate height
        height = estimate_tree_height(treetop, las)
        
        # Create placement record
        placement = {
            "id": f"pine_{i:03d}",
            "kind": species,
            "position": [round(x, 3), round(z, 3), round(y, 3)],  # [x, z, y] format
            "yaw": round(np.random.uniform(0, 6.28), 3),  # random orientation
            "scale": round(min(height / 15, 2.0), 3),  # scale based on height
            "variant": variant,
            "review": "detected_from_lidar",
            "lidar_source": True
        }
        
        placements.append(placement)
    
    return placements

def export_to_project_format(placements):
    """Export placements to project format"""
    # Create the full placements structure
    output = {
        "schema": 1,
        "status": "fixed authoring draft; review individual placements against the aerial, then edit normally",
        "trees": placements,
        "grass": [],
        "rocks": [],
        "logs": []
    }
    
    # Save to file
    output_path = OUTPUT_DIR / "placements_from_lidar.json"
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"  Exported {len(placements)} tree placements to {output_path}")
    return output_path

def main():
    """Main function"""
    print("=" * 60)
    print("Yellowstone LAZ Point Cloud Tree Detection")
    print("=" * 60)
    
    # Step 1: download the LAZ files listed in LAZ_URLS.
    downloaded_files = download_laz_files()
    
    if not downloaded_files:
        print("No files downloaded. Please check your download URLs.")
        print("To use this script, you need to:")
        print("1. Provide actual USGS LAZ URLs in the LAZ_URLS list")
        print("2. Install required dependencies: laspy[lazrs], numpy, scipy, rasterio")
        return
    
    # Step 2: Process each LAZ file
    all_treetops = []
    global las
    
    for filepath in downloaded_files:
        print(f"\nProcessing {filepath.name}...")
        
        # Read LAZ file
        points, las = read_laz_file(filepath)
        if points is None:
            continue
        
        # Filter to project bounds
        filtered_points = filter_points_to_project(points, las, PROJECT_BOUNDS)
        
        # Detect treetops
        treetops = detect_treetops(filtered_points, las)
        
        # Add to collection
        all_treetops.append(treetops)
    
    if not all_treetops:
        print("No treetops detected. Try adjusting detection parameters.")
        return
    
    # Combine all treetops
    all_treetops = np.vstack(all_treetops)
    print(f"\nTotal treetop candidates: {len(all_treetops)}")
    
    # Step 3: Create placements
    print("\nCreating tree placements...")
    placements = create_placement_from_treetops(all_treetops)
    
    # Step 4: Export to project format
    output_path = export_to_project_format(placements)
    
    print("\n" + "=" * 60)
    print("Processing complete!")
    print(f"Generated {len(placements)} tree placements")
    print("Output saved to:", output_path)
    print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        sys.exit(1)