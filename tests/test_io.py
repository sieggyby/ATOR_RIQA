"""Tests for I/O layer: scanner profiles, point cloud import, CAD import.

Tests for profile loading run against real YAML files.
Tests for PLY/STEP loading use lightweight fixtures or mocks since
Open3D and cadquery may not be installed in all test environments.
"""

import hashlib
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from riqa.scanner.profiles import (
    PartTypeThresholds,
    ScannerProfile,
    get_thresholds_for_part_type,
    load_profile,
)


# ========================================================================
# Helpers (must be defined before use in skipif decorators)
# ========================================================================

def _can_import(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


def _mock_pcd(n_points: int, extent: tuple[float, float, float]):
    """Create a mock Open3D-like PointCloud with numpy arrays.

    If Open3D is available, creates a real PointCloud.
    Otherwise creates a mock that quacks like one.
    """
    rng = np.random.default_rng(42)
    points = rng.random((n_points, 3)) * np.array(extent)

    try:
        import open3d as o3d
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        return pcd
    except ImportError:
        mock = MagicMock()
        mock.points = points
        mock.has_normals.return_value = False
        return mock


# ========================================================================
# Scanner Profile Tests (pure Python — no heavy deps)
# ========================================================================

class TestLoadProfile:
    def test_load_ferret_se(self):
        """Load the real Ferret SE profile from config."""
        profile = load_profile("creality_ferret_se")
        assert profile.scanner_class == "consumer"
        assert profile.model == "Creality Ferret SE"
        assert profile.accuracy_class_mm == 0.1
        assert profile.warmup_minutes == 30
        assert profile.sor_sigma_adjustment == 0.5
        assert profile.cad_proximity_adjustment_mm == 1.0
        assert profile.fusion_voxel_size_mm == 0.25

    def test_part_types_loaded(self):
        profile = load_profile("creality_ferret_se")
        assert "machined_metal" in profile.part_types
        assert "injection_molded" in profile.part_types
        assert "fdm_printed" in profile.part_types
        assert "sla_printed" in profile.part_types

    def test_machined_metal_thresholds(self):
        """Consumer SOR adjustment (+0.5) applied to base threshold."""
        profile = load_profile("creality_ferret_se")
        t = profile.part_types["machined_metal"]
        assert t.sor_std_ratio == 2.5  # base 2.0 + 0.5 consumer adjustment
        assert t.cad_proximity_mm == 2.5  # base 1.5 + 1.0 consumer adjustment
        assert t.consensus_threshold == "ceil(N/2)"

    def test_fdm_printed_thresholds(self):
        """FDM has higher base thresholds + consumer adjustment."""
        profile = load_profile("creality_ferret_se")
        t = profile.part_types["fdm_printed"]
        assert t.sor_std_ratio == 3.0  # base 2.5 + 0.5
        assert t.cad_proximity_mm == 3.0  # base 2.0 + 1.0

    def test_missing_profile_raises(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            load_profile("nonexistent_scanner")

    def test_missing_field_raises(self):
        """Profile YAML missing required fields should raise."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_yaml = Path(tmpdir) / "bad.yaml"
            bad_yaml.write_text("scanner_class: consumer\nmodel: Bad\n")
            with pytest.raises(ValueError, match="missing required field"):
                load_profile("bad", profiles_dir=Path(tmpdir))


class TestGetThresholds:
    def test_valid_part_type(self):
        profile = load_profile("creality_ferret_se")
        t = get_thresholds_for_part_type(profile, "machined_metal")
        assert isinstance(t, PartTypeThresholds)
        assert t.sor_std_ratio == 2.5

    def test_invalid_part_type_raises(self):
        profile = load_profile("creality_ferret_se")
        with pytest.raises(ValueError, match="not defined"):
            get_thresholds_for_part_type(profile, "exotic_ceramic")


# ========================================================================
# CAD Import Tests
# ========================================================================

class TestComputeFileHash:
    def test_deterministic_sha256(self):
        """Hash must be deterministic SHA-256 of raw bytes."""
        from riqa.cad.importer import compute_file_hash

        with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
            f.write(b"STEP file content for hashing test")
            f.flush()
            path = Path(f.name)

        try:
            result = compute_file_hash(path)
            expected = hashlib.sha256(b"STEP file content for hashing test").hexdigest()
            assert result == expected
        finally:
            path.unlink()

    def test_different_content_different_hash(self):
        from riqa.cad.importer import compute_file_hash

        with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f1:
            f1.write(b"content A")
            f1.flush()
            path1 = Path(f1.name)
        with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f2:
            f2.write(b"content B")
            f2.flush()
            path2 = Path(f2.name)

        try:
            assert compute_file_hash(path1) != compute_file_hash(path2)
        finally:
            path1.unlink()
            path2.unlink()


class TestLoadStep:
    def test_missing_file_raises(self):
        from riqa.cad.importer import load_step
        with pytest.raises(FileNotFoundError):
            load_step("/nonexistent/file.step")

    def test_wrong_extension_raises(self):
        from riqa.cad.importer import load_step
        with tempfile.NamedTemporaryFile(suffix=".ply", delete=False) as f:
            f.write(b"not a step file")
            path = Path(f.name)
        try:
            with pytest.raises(ValueError, match="Unsupported CAD"):
                load_step(path)
        finally:
            path.unlink()


# ========================================================================
# PLY Import Tests (mock Open3D since it may not be installed)
# ========================================================================

class TestLoadPly:
    def test_missing_file_raises(self):
        """load_ply must raise FileNotFoundError, not return empty."""
        from riqa.scanner.import_ply import load_ply
        with pytest.raises(FileNotFoundError):
            load_ply("/nonexistent/scan.ply")

    def test_wrong_extension_raises(self):
        from riqa.scanner.import_ply import load_ply
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not a scan")
            path = Path(f.name)
        try:
            with pytest.raises(ValueError, match="Unsupported"):
                load_ply(path)
        finally:
            path.unlink()

    @pytest.mark.skipif(
        not _can_import("open3d"),
        reason="open3d not installed",
    )
    def test_empty_ply_raises(self):
        """Empty or corrupt PLY must raise ValueError, not return empty cloud."""
        from riqa.scanner.import_ply import load_ply
        with tempfile.NamedTemporaryFile(suffix=".ply", delete=False) as f:
            f.write(b"ply\nformat ascii 1.0\nelement vertex 0\nend_header\n")
            path = Path(f.name)
        try:
            with pytest.raises(ValueError, match="empty or corrupt"):
                load_ply(path)
        finally:
            path.unlink()


class TestValidateScan:
    def test_valid_cloud(self):
        """A plausible point cloud should pass validation."""
        from riqa.scanner.import_ply import validate_scan
        pcd = _mock_pcd(n_points=5000, extent=(50, 30, 20))
        result = validate_scan(pcd)
        assert result.is_valid is True
        assert result.point_count == 5000

    def test_too_few_points(self):
        from riqa.scanner.import_ply import validate_scan
        pcd = _mock_pcd(n_points=500, extent=(50, 30, 20))
        result = validate_scan(pcd)
        assert result.is_valid is False
        assert "Too few" in result.rejection_reason

    def test_degenerate_bbox(self):
        from riqa.scanner.import_ply import validate_scan
        pcd = _mock_pcd(n_points=5000, extent=(50, 30, 0.5))
        result = validate_scan(pcd)
        assert result.is_valid is False
        assert "degenerate" in result.rejection_reason.lower()

    def test_oversized_bbox(self):
        from riqa.scanner.import_ply import validate_scan
        pcd = _mock_pcd(n_points=5000, extent=(50, 30, 3000))
        result = validate_scan(pcd)
        assert result.is_valid is False
        assert "too large" in result.rejection_reason.lower()


