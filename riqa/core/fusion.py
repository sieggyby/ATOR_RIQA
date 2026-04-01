"""Multi-scan merge, voxel consensus filtering, and per-voxel averaging.

See spec Section 7.3.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class FusionResult:
    """Result of fusing multiple aligned scans."""
    fused_pcd: object      # Open3D PointCloud
    scan_count: int
    consensus_threshold: int
    total_input_points: int
    fused_point_count: int


def fuse_scans(
    aligned_pcds: list,
    voxel_size_mm: float = 0.25,
    min_scans: int | None = None,
) -> FusionResult:
    """Merge N aligned point clouds with voxel consensus filtering.

    For each voxel, a point is kept only if it contains contributions
    from at least ceil(N/2) scans. The output point is the centroid
    of all contributing points in that voxel.

    Consensus threshold is ceil(N/2), NOT floor. This ensures majority
    agreement — a single noisy scan cannot add phantom points.

    Args:
        aligned_pcds: List of Open3D PointClouds (all aligned to same frame).
        voxel_size_mm: Voxel edge length for consensus grid.
        min_scans: Override for consensus threshold (default: ceil(N/2)).

    Returns:
        FusionResult with fused cloud and metadata.
    """
    n_scans = len(aligned_pcds)
    if n_scans == 0:
        raise ValueError("No point clouds to fuse.")

    # Consensus threshold: ceil(N/2)
    default_consensus = math.ceil(n_scans / 2)
    if min_scans is not None:
        if min_scans < default_consensus:
            raise ValueError(
                f"min_scans ({min_scans}) cannot be less than ceil(N/2) = {default_consensus}. "
                f"Lowering consensus below majority would allow phantom points from noisy scans."
            )
        consensus = min_scans
    else:
        consensus = default_consensus

    import open3d as o3d

    # Collect all points with scan index
    all_points = []
    scan_indices = []
    total_input = 0

    for scan_idx, pcd in enumerate(aligned_pcds):
        pts = np.asarray(pcd.points)
        total_input += len(pts)
        all_points.append(pts)
        scan_indices.append(np.full(len(pts), scan_idx, dtype=np.int32))

    all_points = np.vstack(all_points)
    scan_indices = np.concatenate(scan_indices)

    # Voxelize: assign each point to a voxel
    voxel_keys = np.floor(all_points / voxel_size_mm).astype(np.int64)

    # Group by voxel
    from collections import defaultdict
    voxel_data = defaultdict(lambda: {"points": [], "scans": set()})

    for i in range(len(all_points)):
        key = tuple(voxel_keys[i])
        voxel_data[key]["points"].append(all_points[i])
        voxel_data[key]["scans"].add(scan_indices[i])

    # Apply consensus filter and compute centroids
    fused_points = []
    for key, data in voxel_data.items():
        if len(data["scans"]) >= consensus:
            centroid = np.mean(data["points"], axis=0)
            fused_points.append(centroid)

    if not fused_points:
        fused_points = np.zeros((0, 3))
    else:
        fused_points = np.array(fused_points)

    # Build fused point cloud
    fused_pcd = o3d.geometry.PointCloud()
    fused_pcd.points = o3d.utility.Vector3dVector(fused_points)

    return FusionResult(
        fused_pcd=fused_pcd,
        scan_count=n_scans,
        consensus_threshold=consensus,
        total_input_points=total_input,
        fused_point_count=len(fused_points),
    )
