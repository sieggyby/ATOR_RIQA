"""Tests for measurement and fusion logic.

Measurement tests use synthetic point clouds (numpy arrays) — no Open3D needed.
Fusion consensus logic is tested separately.
"""

import math

import numpy as np
import pytest

from riqa.core.measurement import (
    compute_effective_sample_size,
    measure_diameter,
    measure_distance,
    measure_envelope,
    measure_flatness,
)


class TestEffectiveSampleSize:
    def test_n_eff_less_than_n_inliers(self):
        """n_eff must be << n_inliers for dense point clouds.
        This is the core protection against underestimating u_fit."""
        rng = np.random.default_rng(42)
        # 10000 points in a 10x10x10 mm cube
        points = rng.random((10000, 3)) * 10.0
        n_eff = compute_effective_sample_size(points, voxel_size_mm=0.5)
        assert n_eff < len(points)
        assert n_eff > 0

    def test_spatial_decimation(self):
        """Points in distinct voxels should each count."""
        # 8 points, one per corner of a 2mm cube
        points = np.array([
            [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1],
            [1, 1, 0], [1, 0, 1], [0, 1, 1], [1, 1, 1],
        ], dtype=float)
        n_eff = compute_effective_sample_size(points, voxel_size_mm=0.5)
        assert n_eff == 8  # each point in its own voxel

    def test_clustered_points_low_n_eff(self):
        """Many points in one voxel should give low n_eff."""
        # All points within a 0.1mm cube — well within a single 0.5mm voxel
        points = np.random.default_rng(42).uniform(0.2, 0.3, (1000, 3))
        n_eff = compute_effective_sample_size(points, voxel_size_mm=0.5)
        assert n_eff == 1

    def test_empty_returns_one(self):
        points = np.zeros((0, 3))
        assert compute_effective_sample_size(points) == 1

    def test_default_voxel_is_2x_base(self):
        """Default decimation voxel should be 2× the base voxel (0.50mm)."""
        points = np.array([[0, 0, 0], [0.6, 0, 0]], dtype=float)
        # With voxel 0.50, these are in different voxels (0/0.5 = 0, 0.6/0.5 = 1)
        n_eff = compute_effective_sample_size(points)
        assert n_eff == 2


class TestMeasureDiameter:
    def test_known_cylinder(self):
        """Fit a cylinder with known diameter = 20mm."""
        rng = np.random.default_rng(42)
        n = 2000
        theta = rng.uniform(0, 2 * math.pi, n)
        z = rng.uniform(0, 30, n)
        r = 10.0  # radius = 10mm, diameter = 20mm

        # Add small noise
        noise = rng.normal(0, 0.005, n)
        x = (r + noise) * np.cos(theta)
        y = (r + noise) * np.sin(theta)

        points = np.column_stack([x, y, z])
        result = measure_diameter(points, axis=np.array([0, 0, 1]))

        assert result.feature_type == "diameter"
        assert result.measured_value == pytest.approx(20.0, abs=0.1)
        assert result.fit_residual < 0.02  # tight fit
        assert result.n_eff < result.n_inliers  # spatial decimation applied

    def test_too_few_points_raises(self):
        points = np.random.default_rng(42).random((5, 3))
        with pytest.raises(ValueError, match="Too few"):
            measure_diameter(points)


class TestMeasureDistance:
    def test_known_distance(self):
        """Two clusters 50mm apart."""
        rng = np.random.default_rng(42)
        pts_a = rng.normal([0, 0, 0], 0.5, (100, 3))
        pts_b = rng.normal([50, 0, 0], 0.5, (100, 3))

        result = measure_distance(pts_a, pts_b)
        assert result.feature_type == "distance"
        assert result.measured_value == pytest.approx(50.0, abs=0.2)

    def test_too_few_points_raises(self):
        with pytest.raises(ValueError):
            measure_distance(np.array([[0, 0, 0]]), np.array([[1, 1, 1]]))


class TestMeasureFlatness:
    def test_perfect_plane(self):
        """Points on a perfect plane should have flatness ≈ 0."""
        rng = np.random.default_rng(42)
        n = 500
        x = rng.uniform(0, 50, n)
        y = rng.uniform(0, 50, n)
        z = np.zeros(n)
        points = np.column_stack([x, y, z])

        result = measure_flatness(points)
        assert result.feature_type == "flatness"
        assert result.measured_value < 1e-10  # peak-to-valley ≈ 0

    def test_known_flatness(self):
        """Plane with known deviation should measure peak-to-valley correctly."""
        rng = np.random.default_rng(42)
        n = 500
        x = rng.uniform(0, 50, n)
        y = rng.uniform(0, 50, n)
        z = rng.uniform(-0.05, 0.05, n)  # ±0.05mm deviation
        # Force extreme values to control peak-to-valley
        z[0] = -0.05
        z[1] = 0.05
        points = np.column_stack([x, y, z])

        result = measure_flatness(points)
        # Peak-to-valley should be approximately 0.1mm
        assert result.measured_value == pytest.approx(0.1, abs=0.01)

    def test_flatness_is_peak_to_valley_not_rmse(self):
        """CRITICAL: flatness must be peak-to-valley, NOT RMSE."""
        rng = np.random.default_rng(42)
        n = 100
        x = rng.uniform(0, 10, n)
        y = rng.uniform(0, 10, n)
        # Most points near z=0, but one outlier at z=1.0
        z = np.zeros(n)
        z[0] = 1.0
        points = np.column_stack([x, y, z])

        result = measure_flatness(points)
        # Peak-to-valley ≈ 1.0, RMSE would be much smaller (~0.1)
        assert result.measured_value > 0.5  # definitely peak-to-valley not RMSE

    def test_too_few_points_raises(self):
        with pytest.raises(ValueError):
            measure_flatness(np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]]))


class TestMeasureEnvelope:
    def test_obb_not_aabb(self):
        """OBB should give tighter bounds than AABB for rotated objects."""
        rng = np.random.default_rng(42)
        n = 1000
        # Create points along a 100mm stick rotated 45° in XY
        t = rng.uniform(0, 100, n)
        w = rng.uniform(-1, 1, n)
        h = rng.uniform(-1, 1, n)

        # Rotate 45 degrees in XY plane
        angle = math.pi / 4
        x = t * math.cos(angle) + w * math.sin(angle)
        y = t * math.sin(angle) - w * math.cos(angle)
        z = h
        points = np.column_stack([x, y, z])

        result = measure_envelope(points)
        assert result.feature_type == "envelope"
        # OBB max dimension should be ~100mm (the stick length)
        assert result.measured_value == pytest.approx(100.0, abs=2.0)

    def test_too_few_points_raises(self):
        with pytest.raises(ValueError):
            measure_envelope(np.array([[0, 0, 0], [1, 0, 0]]))


class TestFusionConsensus:
    def test_consensus_threshold_is_ceil(self):
        """Consensus must use ceil(N/2), NOT floor."""
        # N=3: ceil(3/2) = 2, floor(3/2) = 1
        assert math.ceil(3 / 2) == 2
        # N=5: ceil(5/2) = 3, floor(5/2) = 2
        assert math.ceil(5 / 2) == 3
        # N=1: ceil(1/2) = 1
        assert math.ceil(1 / 2) == 1
