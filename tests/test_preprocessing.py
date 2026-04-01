"""Tests for preprocessing and outlier removal.

Open3D-dependent tests are skipped if open3d is not installed.
Pure-logic tests (classification, thresholds) always run.
"""

import pytest


# ========================================================================
# Alignment Classification Tests (pure Python — no Open3D needed)
# ========================================================================

from riqa.core.alignment import classify_alignment


class TestClassifyAlignment:
    def test_pass_band(self):
        band, reason = classify_alignment(
            fitness=0.95, rmse=0.05, stability_passed=True,
        )
        assert band == "pass"
        assert reason is None

    def test_hard_block_low_fitness(self):
        band, reason = classify_alignment(
            fitness=0.60, rmse=0.05, stability_passed=True,
        )
        assert band == "hard_block"

    def test_hard_block_high_rmse(self):
        band, reason = classify_alignment(
            fitness=0.95, rmse=0.20, stability_passed=True,
        )
        assert band == "hard_block"

    def test_hard_block_unconstrained_low_fitness(self):
        """Unconstrained alignment (Phase 0) has higher fitness bar: 0.80."""
        band, reason = classify_alignment(
            fitness=0.75, rmse=0.05, stability_passed=True,
            is_unconstrained=True,
        )
        assert band == "hard_block"

    def test_unconstrained_at_threshold_passes(self):
        """Fitness exactly at 0.80 should pass for unconstrained."""
        band, reason = classify_alignment(
            fitness=0.80, rmse=0.05, stability_passed=True,
            is_unconstrained=True,
        )
        assert band == "pass"

    def test_constrained_lower_fitness_passes(self):
        """Non-unconstrained alignment can pass at 0.75 fitness."""
        band, reason = classify_alignment(
            fitness=0.75, rmse=0.05, stability_passed=True,
            is_unconstrained=False,
        )
        assert band == "pass"

    def test_soft_degrade_stability_fails(self):
        """Good fitness/RMSE but stability failure -> soft_degrade."""
        band, reason = classify_alignment(
            fitness=0.95, rmse=0.05, stability_passed=False,
        )
        assert band == "soft_degrade"
        assert reason == "REVIEW_ONLY_ALIGNMENT_DEGRADED"

    def test_hard_block_returns_none_aligned_pcd(self):
        """When hard-blocked, align() must return aligned_pcd=None.
        This is tested at the classify level — align() checks this band."""
        band, _ = classify_alignment(
            fitness=0.50, rmse=0.30, stability_passed=False,
        )
        assert band == "hard_block"

    def test_hard_block_fitness_boundary(self):
        """Fitness exactly at 0.70 should pass (>= threshold)."""
        band, _ = classify_alignment(
            fitness=0.70, rmse=0.05, stability_passed=True,
            is_unconstrained=False,
        )
        assert band == "pass"

    def test_hard_block_rmse_boundary(self):
        """RMSE exactly at 0.15 should pass (<= threshold)."""
        band, _ = classify_alignment(
            fitness=0.95, rmse=0.15, stability_passed=True,
        )
        assert band == "pass"

    def test_hard_block_rmse_just_over(self):
        """RMSE just over 0.15 -> hard_block."""
        band, _ = classify_alignment(
            fitness=0.95, rmse=0.151, stability_passed=True,
        )
        assert band == "hard_block"
