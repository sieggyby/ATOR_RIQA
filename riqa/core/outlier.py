"""Outlier removal: SOR, CAD-proximity filter, consensus filtering.

See spec Sections 7.1 and 7.1.1.
"""

from __future__ import annotations

import numpy as np


def statistical_outlier_removal(
    pcd,
    nb_neighbors: int = 20,
    std_ratio: float = 2.0,
):
    """Statistical outlier removal via Open3D.

    Args:
        pcd: Open3D PointCloud.
        nb_neighbors: Number of neighbors for mean distance computation.
        std_ratio: Standard deviation multiplier threshold.
                   Higher = more permissive. Scanner profile adjusts this
                   (e.g., consumer scanners add +0.5 to base).

    Returns:
        Filtered Open3D PointCloud (outliers removed).
    """
    import open3d as o3d

    filtered, indices = pcd.remove_statistical_outlier(
        nb_neighbors=nb_neighbors,
        std_ratio=std_ratio,
    )
    return filtered


def cad_proximity_filter(
    pcd,
    cad_mesh,
    max_distance_mm: float = 2.5,
):
    """Remove scan points that are too far from the CAD surface.

    PRECONDITION: Must be called AFTER alignment. Points are compared
    to the CAD mesh in the aligned coordinate frame. Calling before
    alignment will remove valid points and keep outliers.

    Args:
        pcd: Open3D PointCloud (aligned to CAD).
        cad_mesh: Open3D TriangleMesh of the CAD model.
        max_distance_mm: Maximum allowable distance from CAD surface.
                         Scanner profile adjusts this (e.g., consumer +1.0mm).

    Returns:
        Filtered Open3D PointCloud with distant points removed.
    """
    import open3d as o3d

    # Create scene for distance queries
    mesh_legacy = o3d.t.geometry.TriangleMesh.from_legacy(cad_mesh)
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(mesh_legacy)

    # Compute closest point distances
    points = np.asarray(pcd.points)
    query_points = o3d.core.Tensor(points, dtype=o3d.core.float32)
    distances = scene.compute_distance(query_points).numpy()

    # Keep only points within threshold
    mask = distances <= max_distance_mm
    indices = np.where(mask)[0]

    return pcd.select_by_index(indices.tolist())
