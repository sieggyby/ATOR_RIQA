"""Local primitive fitting and dimension extraction.

Supports: diameter (RANSAC cylinder/circle), distance,
envelope dimensions (OBB), flatness (least-squares plane).

See spec Section 7.4.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import optimize
from scipy.spatial import ConvexHull


@dataclass
class MeasurementResult:
    """Result of a single feature measurement."""
    feature_type: str
    measured_value: float
    fit_residual: float    # RMSE for cylinder/plane fits
    n_inliers: int
    n_eff: int             # Effective sample size (spatially decimated)
    inlier_points: np.ndarray  # Points used in final fit


def compute_effective_sample_size(
    points: np.ndarray,
    voxel_size_mm: float | None = None,
    base_voxel_mm: float = 0.25,
) -> int:
    """Compute effective sample size via spatial decimation.

    n_eff is the number of spatially independent samples, NOT the raw
    inlier count. This is critical for correct uncertainty computation —
    using n_inliers instead of n_eff would drastically underestimate
    fit uncertainty.

    Decimation grid is 2× the fusion voxel size to ensure independence.

    Args:
        points: (N, 3) numpy array of points.
        voxel_size_mm: Decimation voxel size. Default: 2 × base_voxel_mm.

    Returns:
        n_eff (always >= 1).
    """
    if len(points) == 0:
        return 1

    if voxel_size_mm is None:
        voxel_size_mm = 2.0 * base_voxel_mm

    # Assign each point to a voxel
    voxel_keys = np.floor(points / voxel_size_mm).astype(np.int64)
    # Count unique voxels
    unique_voxels = len(set(map(tuple, voxel_keys)))

    return max(1, unique_voxels)


def measure_diameter(
    points: np.ndarray,
    axis: np.ndarray | None = None,
    ransac_iterations: int = 1000,
    inlier_threshold_mm: float = 0.1,
) -> MeasurementResult:
    """Measure diameter via RANSAC cylinder fit.

    Uses RANSAC to find the best-fit cylinder, then refines with
    least-squares on inliers.

    Args:
        points: (N, 3) local points around the cylindrical feature.
        axis: (3,) approximate cylinder axis from CAD. If None, estimated from PCA.
        ransac_iterations: Number of RANSAC iterations.
        inlier_threshold_mm: Max distance from cylinder surface to be an inlier.

    Returns:
        MeasurementResult with diameter as measured_value.
    """
    if len(points) < 10:
        raise ValueError(f"Too few points for diameter measurement: {len(points)}")

    # Estimate axis from PCA if not provided
    if axis is None:
        centered = points - points.mean(axis=0)
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        axis = vh[0]  # First principal component

    axis = axis / np.linalg.norm(axis)

    # Project points to 2D (perpendicular to axis)
    center_3d = points.mean(axis=0)
    relative = points - center_3d

    # Build orthonormal basis
    u = _perpendicular_vector(axis)
    v = np.cross(axis, u)

    proj_u = relative @ u
    proj_v = relative @ v
    points_2d = np.column_stack([proj_u, proj_v])

    # RANSAC circle fit in 2D
    best_inliers = []
    best_cx, best_cy, best_r = 0.0, 0.0, 0.0
    rng = np.random.default_rng(42)

    for _ in range(ransac_iterations):
        # Sample 3 points
        idx = rng.choice(len(points_2d), 3, replace=False)
        sample = points_2d[idx]

        # Fit circle through 3 points
        cx, cy, r = _circle_from_3_points(sample)
        if r <= 0 or r > 500:  # sanity check
            continue

        # Count inliers
        dists = np.abs(np.sqrt((points_2d[:, 0] - cx)**2 + (points_2d[:, 1] - cy)**2) - r)
        inlier_mask = dists < inlier_threshold_mm

        if inlier_mask.sum() > len(best_inliers):
            best_inliers = np.where(inlier_mask)[0]
            best_cx, best_cy, best_r = cx, cy, r

    if len(best_inliers) < 5:
        raise ValueError("RANSAC cylinder fit failed — too few inliers.")

    # Refine with least-squares on inliers
    inlier_2d = points_2d[best_inliers]

    def circle_residuals(params):
        cx, cy, r = params
        return np.sqrt((inlier_2d[:, 0] - cx)**2 + (inlier_2d[:, 1] - cy)**2) - r

    result = optimize.least_squares(circle_residuals, [best_cx, best_cy, best_r])
    cx_final, cy_final, r_final = result.x

    # Compute RMSE
    residuals = circle_residuals(result.x)
    rmse = np.sqrt(np.mean(residuals**2))

    # Effective sample size
    inlier_points = points[best_inliers]
    n_eff = compute_effective_sample_size(inlier_points)

    return MeasurementResult(
        feature_type="diameter",
        measured_value=2.0 * r_final,
        fit_residual=rmse,
        n_inliers=len(best_inliers),
        n_eff=n_eff,
        inlier_points=inlier_points,
    )


def measure_distance(
    points_a: np.ndarray,
    points_b: np.ndarray,
) -> MeasurementResult:
    """Measure center-to-center distance between two point clusters.

    Fits centroids to both clusters and returns the Euclidean distance.

    Args:
        points_a: (N, 3) points for first endpoint.
        points_b: (M, 3) points for second endpoint.

    Returns:
        MeasurementResult with distance as measured_value.
    """
    if len(points_a) < 3 or len(points_b) < 3:
        raise ValueError("Too few points for distance measurement.")

    center_a = points_a.mean(axis=0)
    center_b = points_b.mean(axis=0)
    distance = np.linalg.norm(center_a - center_b)

    # Combined fit residual: RMS of distances from centroids
    res_a = np.sqrt(np.mean(np.sum((points_a - center_a)**2, axis=1)))
    res_b = np.sqrt(np.mean(np.sum((points_b - center_b)**2, axis=1)))
    combined_residual = math.sqrt(res_a**2 + res_b**2)

    all_points = np.vstack([points_a, points_b])
    n_eff = compute_effective_sample_size(all_points)

    return MeasurementResult(
        feature_type="distance",
        measured_value=distance,
        fit_residual=combined_residual,
        n_inliers=len(points_a) + len(points_b),
        n_eff=n_eff,
        inlier_points=all_points,
    )


def measure_flatness(
    points: np.ndarray,
) -> MeasurementResult:
    """Measure flatness: peak-to-valley residual of least-squares plane.

    NOT RMSE — flatness is the total range of deviation from the best-fit
    plane (max - min residual).

    Args:
        points: (N, 3) points on the nominally flat surface.

    Returns:
        MeasurementResult with flatness (peak-to-valley) as measured_value.
    """
    if len(points) < 4:
        raise ValueError("Too few points for flatness measurement.")

    # Fit plane via SVD
    centroid = points.mean(axis=0)
    centered = points - centroid
    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    normal = vh[2]  # Smallest singular value = plane normal

    # Signed distances from plane
    distances = centered @ normal

    # Flatness = peak-to-valley (NOT RMSE)
    flatness = distances.max() - distances.min()
    rmse = np.sqrt(np.mean(distances**2))

    n_eff = compute_effective_sample_size(points)

    return MeasurementResult(
        feature_type="flatness",
        measured_value=flatness,
        fit_residual=rmse,
        n_inliers=len(points),
        n_eff=n_eff,
        inlier_points=points,
    )


def measure_envelope(
    points: np.ndarray,
) -> MeasurementResult:
    """Measure envelope dimensions via oriented bounding box (OBB).

    Uses OBB, NOT axis-aligned bounding box (AABB). OBB gives
    tighter bounds on arbitrarily oriented parts.

    Args:
        points: (N, 3) points.

    Returns:
        MeasurementResult with max OBB dimension as measured_value.
        The fit_residual contains the OBB volume for reference.
    """
    if len(points) < 4:
        raise ValueError("Too few points for envelope measurement.")

    # Compute OBB via PCA
    centroid = points.mean(axis=0)
    centered = points - centroid
    _, _, vh = np.linalg.svd(centered, full_matrices=False)

    # Project points onto principal axes
    projected = centered @ vh.T
    obb_min = projected.min(axis=0)
    obb_max = projected.max(axis=0)
    obb_extents = obb_max - obb_min

    max_dimension = obb_extents.max()
    volume = np.prod(obb_extents)

    n_eff = compute_effective_sample_size(points)

    return MeasurementResult(
        feature_type="envelope",
        measured_value=max_dimension,
        fit_residual=volume,  # OBB volume as residual proxy
        n_inliers=len(points),
        n_eff=n_eff,
        inlier_points=points,
    )


# ========================================================================
# Internal helpers
# ========================================================================

def _perpendicular_vector(v: np.ndarray) -> np.ndarray:
    """Find a unit vector perpendicular to v."""
    if abs(v[0]) < 0.9:
        perp = np.cross(v, np.array([1, 0, 0]))
    else:
        perp = np.cross(v, np.array([0, 1, 0]))
    return perp / np.linalg.norm(perp)


def _circle_from_3_points(pts: np.ndarray) -> tuple[float, float, float]:
    """Fit a circle through exactly 3 points. Returns (cx, cy, radius)."""
    ax, ay = pts[0]
    bx, by = pts[1]
    cx, cy = pts[2]

    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return 0.0, 0.0, -1.0  # degenerate

    ux = ((ax**2 + ay**2) * (by - cy) + (bx**2 + by**2) * (cy - ay) + (cx**2 + cy**2) * (ay - by)) / d
    uy = ((ax**2 + ay**2) * (cx - bx) + (bx**2 + by**2) * (ax - cx) + (cx**2 + cy**2) * (bx - ax)) / d

    r = math.sqrt((ax - ux)**2 + (ay - uy)**2)
    return ux, uy, r
