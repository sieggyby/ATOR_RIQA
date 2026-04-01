"""Search region definition for measurement extraction.

Defines bounding regions around CAD features for local point extraction.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class FeatureSearchRegion:
    """Defines the region around a CAD feature for point extraction."""
    feature_id: str
    feature_type: str       # 'diameter', 'distance', 'flatness', 'envelope'
    center: np.ndarray      # (3,) center of the feature region
    bbox_min: np.ndarray    # (3,) bounding box min
    bbox_max: np.ndarray    # (3,) bounding box max
    margin_mm: float        # extra margin applied around feature bounds
    axis: np.ndarray | None = None  # (3,) feature axis for cylinders/holes


def extract_local_points(
    pcd,
    region: FeatureSearchRegion,
) -> tuple[np.ndarray, int]:
    """Crop fused point cloud to feature bounding box.

    Args:
        pcd: Open3D PointCloud (fused, aligned).
        region: Feature search region.

    Returns:
        (points, n_points) — numpy array of shape (N, 3) and count.
    """
    import open3d as o3d

    aabb = o3d.geometry.AxisAlignedBoundingBox(
        min_bound=region.bbox_min - region.margin_mm,
        max_bound=region.bbox_max + region.margin_mm,
    )
    cropped = pcd.crop(aabb)
    points = np.asarray(cropped.points)
    return points, len(points)
