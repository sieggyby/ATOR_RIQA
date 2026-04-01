"""Three-stage alignment pipeline.

Stage 1: Coarse pose via PCA + bounding box (Phase 0: always unconstrained)
Stage 2: Feature-based refinement via FPFH feature matching
Stage 3: Fine alignment via two-pass point-to-plane ICP

See spec Section 7.2.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field

import numpy as np


@dataclass
class AlignmentResult:
    """Full result of the 3-stage alignment pipeline."""
    aligned_pcd: object | None       # Open3D PointCloud aligned to CAD. None if hard-blocked.
    transformation: np.ndarray       # 4x4 transformation matrix
    fitness: float                   # ICP fitness (fraction of inlier correspondences)
    rmse: float                      # ICP RMSE (mm)
    alignment_band: str              # 'pass', 'soft_degrade', or 'hard_block'
    reason_code: str | None          # e.g. REVIEW_ONLY_ALIGNMENT_DEGRADED
    stability_passed: bool
    perturbation_values: list[float] = field(default_factory=list)


def stage1_coarse_pose(
    scan_pcd,
    cad_pcd,
) -> np.ndarray:
    """Stage 1: PCA-based coarse pose estimation.

    Aligns principal axes of scan to CAD. Tests all 8 axis-flip
    combinations and picks the best one by ICP fitness.

    Phase 0: Always unconstrained (no fixture/datum constraints).

    Args:
        scan_pcd: Open3D PointCloud (scan, downsampled).
        cad_pcd: Open3D PointCloud (CAD surface samples, downsampled).

    Returns:
        4x4 transformation matrix for initial alignment.
    """
    import open3d as o3d

    # Compute centroids
    scan_center = np.asarray(scan_pcd.points).mean(axis=0)
    cad_center = np.asarray(cad_pcd.points).mean(axis=0)

    # PCA on both clouds
    scan_cov = np.cov(np.asarray(scan_pcd.points).T)
    cad_cov = np.cov(np.asarray(cad_pcd.points).T)

    _, scan_vecs = np.linalg.eigh(scan_cov)
    _, cad_vecs = np.linalg.eigh(cad_cov)

    # Reverse to get descending eigenvalue order
    scan_vecs = scan_vecs[:, ::-1]
    cad_vecs = cad_vecs[:, ::-1]

    # Test all 8 axis-flip combinations
    best_fitness = -1.0
    best_transform = np.eye(4)

    flip_signs = [
        (1, 1, 1), (1, 1, -1), (1, -1, 1), (1, -1, -1),
        (-1, 1, 1), (-1, 1, -1), (-1, -1, 1), (-1, -1, -1),
    ]

    for signs in flip_signs:
        # Apply flips to scan eigenvectors
        flipped = scan_vecs * np.array(signs)
        # Rotation from scan frame to CAD frame
        R = cad_vecs @ np.linalg.inv(flipped)
        # Translation
        t = cad_center - R @ scan_center

        # Build 4x4
        T = np.eye(4)
        T[:3, :3] = R
        T[:3, 3] = t

        # Quick ICP evaluation
        scan_copy = copy.deepcopy(scan_pcd)
        scan_copy.transform(T)

        reg = o3d.pipelines.registration.evaluate_registration(
            scan_copy, cad_pcd, 5.0,  # large threshold for coarse eval
        )

        if reg.fitness > best_fitness:
            best_fitness = reg.fitness
            best_transform = T

    return best_transform


def stage2_feature_refinement(
    scan_pcd,
    cad_pcd,
    initial_transform: np.ndarray,
    voxel_size: float = 0.5,
) -> np.ndarray:
    """Stage 2: FPFH feature-based refinement.

    Uses Fast Point Feature Histograms for correspondence matching,
    followed by RANSAC-based registration.

    Args:
        scan_pcd: Open3D PointCloud (scan, with normals).
        cad_pcd: Open3D PointCloud (CAD, with normals).
        initial_transform: Transform from Stage 1.
        voxel_size: Voxel size for FPFH feature computation.

    Returns:
        Refined 4x4 transformation matrix.
    """
    import open3d as o3d

    # Apply initial transform
    scan_aligned = copy.deepcopy(scan_pcd)
    scan_aligned.transform(initial_transform)

    # Ensure normals exist
    if not scan_aligned.has_normals():
        scan_aligned.estimate_normals(
            o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size * 2, max_nn=30)
        )
    if not cad_pcd.has_normals():
        cad_copy = copy.deepcopy(cad_pcd)
        cad_copy.estimate_normals(
            o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size * 2, max_nn=30)
        )
    else:
        cad_copy = cad_pcd

    # Compute FPFH features
    radius_feature = voxel_size * 5
    scan_fpfh = o3d.pipelines.registration.compute_fpfh_feature(
        scan_aligned,
        o3d.geometry.KDTreeSearchParamHybrid(radius=radius_feature, max_nn=100),
    )
    cad_fpfh = o3d.pipelines.registration.compute_fpfh_feature(
        cad_copy,
        o3d.geometry.KDTreeSearchParamHybrid(radius=radius_feature, max_nn=100),
    )

    # RANSAC registration
    distance_threshold = voxel_size * 1.5
    result = o3d.pipelines.registration.registration_ransac_based_on_feature_matching(
        scan_aligned,
        cad_copy,
        scan_fpfh,
        cad_fpfh,
        mutual_filter=True,
        max_correspondence_distance=distance_threshold,
        estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPoint(),
        ransac_n=4,
        checkers=[
            o3d.pipelines.registration.CorrespondenceCheckerBasedOnDistance(distance_threshold),
        ],
        criteria=o3d.pipelines.registration.RANSACConvergenceCriteria(4000000, 500),
    )

    # Combine: RANSAC result is relative to scan_aligned, so compose
    combined = result.transformation @ initial_transform
    return combined


def stage3_fine_icp(
    scan_pcd,
    cad_pcd,
    initial_transform: np.ndarray,
    max_iterations: int = 50,
    convergence_threshold: float = 1e-7,
) -> tuple[np.ndarray, float, float]:
    """Stage 3: Two-pass point-to-plane ICP.

    Pass 1: max_correspondence_distance = 2.0mm (broad capture)
    Pass 2: max_correspondence_distance = 0.5mm (fine refinement)

    Args:
        scan_pcd: Open3D PointCloud with normals.
        cad_pcd: Open3D PointCloud with normals.
        initial_transform: Transform from Stage 2.
        max_iterations: ICP max iterations per pass.
        convergence_threshold: ICP convergence tolerance.

    Returns:
        (transformation, fitness, rmse)
    """
    import open3d as o3d

    criteria = o3d.pipelines.registration.ICPConvergenceCriteria(
        max_iteration=max_iterations,
        relative_fitness=convergence_threshold,
        relative_rmse=convergence_threshold,
    )

    # Pass 1: broad
    reg1 = o3d.pipelines.registration.registration_icp(
        scan_pcd, cad_pcd,
        max_correspondence_distance=2.0,
        init=initial_transform,
        estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPlane(),
        criteria=criteria,
    )

    # Pass 2: fine
    reg2 = o3d.pipelines.registration.registration_icp(
        scan_pcd, cad_pcd,
        max_correspondence_distance=0.5,
        init=reg1.transformation,
        estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPlane(),
        criteria=criteria,
    )

    return reg2.transformation, reg2.fitness, reg2.inlier_rmse


def stability_test(
    scan_pcd,
    cad_pcd,
    base_transform: np.ndarray,
    n_perturbations: int = 6,
    angle_deg: float = 0.3,
    translate_mm: float = 0.3,
    max_iterations: int = 50,
    convergence_threshold: float = 1e-7,
) -> tuple[bool, list[float]]:
    """Test alignment stability by perturbing starting pose.

    Perturbs the base transform by ±angle/±translate, re-runs ICP,
    and checks that all results converge to similar RMSE values.

    Args:
        scan_pcd: Open3D PointCloud with normals.
        cad_pcd: Open3D PointCloud with normals.
        base_transform: The converged ICP transformation to test.
        n_perturbations: Number of random perturbations.
        angle_deg: Max perturbation angle in degrees.
        translate_mm: Max perturbation translation in mm.

    Returns:
        (stability_passed, list of RMSE values from perturbation runs)
    """
    import open3d as o3d

    rng = np.random.default_rng(42)
    rmse_values = []

    for _ in range(n_perturbations):
        # Random rotation perturbation
        angles = rng.uniform(-angle_deg, angle_deg, 3) * (math.pi / 180.0)
        Rx = np.array([[1, 0, 0], [0, math.cos(angles[0]), -math.sin(angles[0])],
                        [0, math.sin(angles[0]), math.cos(angles[0])]])
        Ry = np.array([[math.cos(angles[1]), 0, math.sin(angles[1])], [0, 1, 0],
                        [-math.sin(angles[1]), 0, math.cos(angles[1])]])
        Rz = np.array([[math.cos(angles[2]), -math.sin(angles[2]), 0],
                        [math.sin(angles[2]), math.cos(angles[2]), 0], [0, 0, 1]])
        R_perturb = Rz @ Ry @ Rx

        # Random translation perturbation
        t_perturb = rng.uniform(-translate_mm, translate_mm, 3)

        # Build perturbation matrix
        T_perturb = np.eye(4)
        T_perturb[:3, :3] = R_perturb
        T_perturb[:3, 3] = t_perturb

        # Perturbed initial transform
        T_init = T_perturb @ base_transform

        # Re-run ICP from perturbed pose
        criteria = o3d.pipelines.registration.ICPConvergenceCriteria(
            max_iteration=max_iterations,
            relative_fitness=convergence_threshold,
            relative_rmse=convergence_threshold,
        )
        reg = o3d.pipelines.registration.registration_icp(
            scan_pcd, cad_pcd,
            max_correspondence_distance=0.5,
            init=T_init,
            estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPlane(),
            criteria=criteria,
        )
        rmse_values.append(reg.inlier_rmse)

    if not rmse_values:
        return False, []

    # Stability check: all RMSE values within 20% of median
    median_rmse = np.median(rmse_values)
    if median_rmse == 0:
        return True, rmse_values

    max_deviation = max(abs(r - median_rmse) / median_rmse for r in rmse_values)
    passed = max_deviation < 0.20

    return passed, rmse_values


def classify_alignment(
    fitness: float,
    rmse: float,
    stability_passed: bool,
    is_unconstrained: bool = True,
    hard_block_fitness: float = 0.70,
    hard_block_rmse: float = 0.15,
    unconstrained_fitness_threshold: float = 0.80,
) -> tuple[str, str | None]:
    """Classify alignment quality into pass/soft_degrade/hard_block.

    Rules (spec Section 7.2):
    - hard_block: fitness < 0.70 OR RMSE > 0.15mm
                  OR (unconstrained AND fitness < 0.80)
    - soft_degrade: between thresholds OR stability test fails
    - pass: all checks pass

    Args:
        fitness: ICP fitness (0-1).
        rmse: ICP RMSE in mm.
        stability_passed: Whether the stability test passed.
        is_unconstrained: Phase 0 is always True (no fixture constraints).
        hard_block_fitness: Minimum fitness for any alignment.
        hard_block_rmse: Maximum RMSE for any alignment (mm).
        unconstrained_fitness_threshold: Higher bar for unconstrained alignment.

    Returns:
        (band, reason_code) where band is 'pass', 'soft_degrade', or 'hard_block'.
    """
    # Hard-block checks
    if fitness < hard_block_fitness:
        return "hard_block", "REVIEW_ONLY_ALIGNMENT_DEGRADED"

    if rmse > hard_block_rmse:
        return "hard_block", "REVIEW_ONLY_ALIGNMENT_DEGRADED"

    # Unconstrained alignment has a higher fitness bar
    if is_unconstrained and fitness < unconstrained_fitness_threshold:
        return "hard_block", "REVIEW_ONLY_ALIGNMENT_DEGRADED"

    # Soft-degrade if stability fails
    if not stability_passed:
        return "soft_degrade", "REVIEW_ONLY_ALIGNMENT_DEGRADED"

    return "pass", None


def align(
    scan_pcd,
    cad_pcd,
    max_iterations: int = 50,
    convergence_threshold: float = 1e-7,
    hard_block_fitness: float = 0.70,
    hard_block_rmse: float = 0.15,
) -> AlignmentResult:
    """Full 3-stage alignment pipeline.

    When hard-blocked, returns aligned_pcd=None to prevent downstream
    measurement on unreliable alignment.

    Args:
        scan_pcd: Open3D PointCloud (preprocessed scan, with normals).
        cad_pcd: Open3D PointCloud (CAD surface samples, with normals).
        max_iterations: ICP max iterations.
        convergence_threshold: ICP convergence tolerance.

    Returns:
        AlignmentResult with aligned cloud, metrics, and classification.
    """
    # Stage 1: Coarse pose
    T1 = stage1_coarse_pose(scan_pcd, cad_pcd)

    # Stage 2: Feature refinement
    T2 = stage2_feature_refinement(scan_pcd, cad_pcd, T1)

    # Stage 3: Fine ICP (two-pass)
    T3, fitness, rmse = stage3_fine_icp(
        scan_pcd, cad_pcd, T2,
        max_iterations=max_iterations,
        convergence_threshold=convergence_threshold,
    )

    # Stability test
    stability_passed, perturbation_values = stability_test(
        scan_pcd, cad_pcd, T3,
        max_iterations=max_iterations,
        convergence_threshold=convergence_threshold,
    )

    # Classify
    band, reason = classify_alignment(
        fitness, rmse, stability_passed,
        is_unconstrained=True,  # PHASE0_SIMPLIFICATION: always unconstrained
        hard_block_fitness=hard_block_fitness,
        hard_block_rmse=hard_block_rmse,
    )

    # If hard-blocked, aligned_pcd is None — prevents downstream measurement
    if band == "hard_block":
        return AlignmentResult(
            aligned_pcd=None,
            transformation=T3,
            fitness=fitness,
            rmse=rmse,
            alignment_band=band,
            reason_code=reason,
            stability_passed=stability_passed,
            perturbation_values=perturbation_values,
        )

    # Apply final transform to get aligned cloud
    import copy as _copy
    aligned = _copy.deepcopy(scan_pcd)
    aligned.transform(T3)

    return AlignmentResult(
        aligned_pcd=aligned,
        transformation=T3,
        fitness=fitness,
        rmse=rmse,
        alignment_band=band,
        reason_code=reason,
        stability_passed=stability_passed,
        perturbation_values=perturbation_values,
    )
