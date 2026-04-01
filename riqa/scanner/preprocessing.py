"""Downsample, normal estimation, noise filtering.

Orchestrates the preprocessing pipeline per scan:
  1. Statistical outlier removal (SOR) using profile thresholds
  2. ROI clip to bounding box with margin
  3. Normal estimation on full-resolution cloud
  4. Voxel downsample (for alignment only — not for measurement)

See spec Section 7.1.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from riqa.core.outlier import statistical_outlier_removal
from riqa.scanner.profiles import ScannerProfile, PartTypeThresholds


@dataclass
class PreprocessedScan:
    """Result of preprocessing a single scan."""
    pcd_full: object       # Open3D PointCloud — full resolution, SOR-filtered, normals estimated
    pcd_downsampled: object  # Open3D PointCloud — voxel downsampled for alignment
    original_point_count: int
    filtered_point_count: int
    points_removed_pct: float


def roi_clip(
    pcd,
    bbox_min: np.ndarray,
    bbox_max: np.ndarray,
    margin_mm: float = 10.0,
):
    """Clip point cloud to region of interest (bounding box + margin).

    Args:
        pcd: Open3D PointCloud.
        bbox_min: (3,) min corner of ROI.
        bbox_max: (3,) max corner of ROI.
        margin_mm: Extra margin on each side.

    Returns:
        Clipped Open3D PointCloud.
    """
    import open3d as o3d

    # Expand bbox by margin
    low = bbox_min - margin_mm
    high = bbox_max + margin_mm

    # Create axis-aligned bounding box
    aabb = o3d.geometry.AxisAlignedBoundingBox(
        min_bound=low,
        max_bound=high,
    )
    return pcd.crop(aabb)


def estimate_normals(
    pcd,
    search_radius_mm: float = 2.0,
    max_nn: int = 30,
):
    """Estimate normals on full-resolution cloud.

    Normals are estimated BEFORE downsampling to preserve surface
    detail for ICP point-to-plane alignment.

    Args:
        pcd: Open3D PointCloud (full resolution).
        search_radius_mm: Radius for normal estimation KNN search.
        max_nn: Maximum number of neighbors.

    Returns:
        Same PointCloud with normals computed (modifies in-place and returns).
    """
    import open3d as o3d

    pcd.estimate_normals(
        search_param=o3d.geometry.KDTreeSearchParamHybrid(
            radius=search_radius_mm,
            max_nn=max_nn,
        )
    )
    return pcd


def voxel_downsample(pcd, voxel_size_mm: float = 0.3):
    """Voxel downsample for alignment.

    This is for alignment ONLY — measurement always uses full-resolution cloud.

    Args:
        pcd: Open3D PointCloud.
        voxel_size_mm: Voxel edge length in mm.

    Returns:
        Downsampled Open3D PointCloud.
    """
    return pcd.voxel_down_sample(voxel_size=voxel_size_mm)


def preprocess_scan(
    pcd,
    thresholds: PartTypeThresholds,
    profile: ScannerProfile,
    cad_bbox_min: np.ndarray | None = None,
    cad_bbox_max: np.ndarray | None = None,
    roi_margin_mm: float = 10.0,
) -> PreprocessedScan:
    """Full preprocessing pipeline for a single scan.

    Pipeline order:
      1. SOR (using profile-adjusted threshold)
      2. ROI clip (if CAD bbox provided)
      3. Normal estimation (on full-res cloud)
      4. Voxel downsample (for alignment)

    Args:
        pcd: Open3D PointCloud (raw scan).
        thresholds: Part-type thresholds from scanner profile.
        profile: Scanner profile for voxel size and other params.
        cad_bbox_min: Optional CAD bounding box min for ROI clip.
        cad_bbox_max: Optional CAD bounding box max for ROI clip.
        roi_margin_mm: Margin for ROI clip.

    Returns:
        PreprocessedScan with full-res and downsampled clouds.
    """
    original_count = len(pcd.points)

    # 1. SOR with profile-adjusted threshold
    pcd_filtered = statistical_outlier_removal(
        pcd,
        nb_neighbors=20,
        std_ratio=thresholds.sor_std_ratio,
    )

    # 2. ROI clip (optional — only if CAD bbox provided)
    if cad_bbox_min is not None and cad_bbox_max is not None:
        pcd_filtered = roi_clip(pcd_filtered, cad_bbox_min, cad_bbox_max, roi_margin_mm)

    filtered_count = len(pcd_filtered.points)
    removed_pct = (1.0 - filtered_count / original_count) * 100.0 if original_count > 0 else 0.0

    # 3. Normal estimation on full-res cloud
    pcd_full = estimate_normals(pcd_filtered)

    # 4. Voxel downsample for alignment
    pcd_down = voxel_downsample(pcd_full, voxel_size_mm=profile.fusion_voxel_size_mm)

    return PreprocessedScan(
        pcd_full=pcd_full,
        pcd_downsampled=pcd_down,
        original_point_count=original_count,
        filtered_point_count=filtered_count,
        points_removed_pct=removed_pct,
    )
