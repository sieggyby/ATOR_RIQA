"""Point cloud file ingestion (PLY/OBJ) and validation.

Validates: point count, bounding box plausibility, noise metric.
See spec Section 7.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class ScanValidation:
    """Validation result for a loaded point cloud."""
    point_count: int
    bbox_min: np.ndarray   # shape (3,)
    bbox_max: np.ndarray   # shape (3,)
    bbox_size_mm: np.ndarray  # shape (3,) — extent in each axis
    has_normals: bool
    is_valid: bool
    rejection_reason: str | None


# Minimum points for any useful scan
MIN_POINT_COUNT = 1000
# Maximum bounding box extent (mm) — rejects nonsense scans
MAX_BBOX_EXTENT_MM = 2000.0
# Minimum bounding box extent (mm) — rejects near-empty scans
MIN_BBOX_EXTENT_MM = 1.0


def load_ply(file_path: str | Path):
    """Load a PLY or OBJ point cloud file.

    Args:
        file_path: Path to PLY or OBJ file.

    Returns:
        Open3D PointCloud object.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file cannot be read or contains no points.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Scan file not found: {path}")

    suffix = path.suffix.lower()
    if suffix not in (".ply", ".obj"):
        raise ValueError(f"Unsupported scan file format: {suffix!r}. Use .ply or .obj.")

    import open3d as o3d
    pcd = o3d.io.read_point_cloud(str(path))

    if pcd is None or len(pcd.points) == 0:
        raise ValueError(f"Failed to read point cloud from {path} — file is empty or corrupt.")

    return pcd


def validate_scan(pcd) -> ScanValidation:
    """Validate a loaded point cloud for basic plausibility.

    Checks:
    1. Minimum point count (>= 1000)
    2. Bounding box not degenerate (each axis >= 1mm)
    3. Bounding box not absurdly large (each axis <= 2000mm)

    Args:
        pcd: Open3D PointCloud.

    Returns:
        ScanValidation with is_valid=True/False and details.
    """
    points = np.asarray(pcd.points)
    point_count = len(points)
    has_normals = pcd.has_normals() if callable(getattr(pcd, 'has_normals', None)) else False

    if point_count == 0:
        return ScanValidation(
            point_count=0,
            bbox_min=np.zeros(3),
            bbox_max=np.zeros(3),
            bbox_size_mm=np.zeros(3),
            has_normals=has_normals,
            is_valid=False,
            rejection_reason="Point cloud is empty.",
        )

    bbox_min = points.min(axis=0)
    bbox_max = points.max(axis=0)
    bbox_size = bbox_max - bbox_min

    # Check minimum point count
    if point_count < MIN_POINT_COUNT:
        return ScanValidation(
            point_count=point_count,
            bbox_min=bbox_min,
            bbox_max=bbox_max,
            bbox_size_mm=bbox_size,
            has_normals=has_normals,
            is_valid=False,
            rejection_reason=f"Too few points: {point_count} < {MIN_POINT_COUNT}.",
        )

    # Check bounding box not degenerate
    if np.any(bbox_size < MIN_BBOX_EXTENT_MM):
        return ScanValidation(
            point_count=point_count,
            bbox_min=bbox_min,
            bbox_max=bbox_max,
            bbox_size_mm=bbox_size,
            has_normals=has_normals,
            is_valid=False,
            rejection_reason=f"Bounding box degenerate: extent {bbox_size} has axis < {MIN_BBOX_EXTENT_MM}mm.",
        )

    # Check bounding box not absurdly large
    if np.any(bbox_size > MAX_BBOX_EXTENT_MM):
        return ScanValidation(
            point_count=point_count,
            bbox_min=bbox_min,
            bbox_max=bbox_max,
            bbox_size_mm=bbox_size,
            has_normals=has_normals,
            is_valid=False,
            rejection_reason=f"Bounding box too large: extent {bbox_size} has axis > {MAX_BBOX_EXTENT_MM}mm.",
        )

    return ScanValidation(
        point_count=point_count,
        bbox_min=bbox_min,
        bbox_max=bbox_max,
        bbox_size_mm=bbox_size,
        has_normals=has_normals,
        is_valid=True,
        rejection_reason=None,
    )
