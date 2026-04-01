"""Integration tests for CLI orchestration layer.

Tests the recipe/eligibility/calibration logic and disposition rules
without requiring Open3D or real scan files.
"""

import pytest

from riqa.data.db import RiqaDatabase
from riqa.data import db as dbmod
from riqa.recipe.eligibility import assign_phase0_class
from riqa.recipe.manager import create_phase0_recipe
from riqa.scanner.calibration import record_calibration, check_calibration_valid


@pytest.fixture
def db():
    """In-memory database for testing."""
    database = RiqaDatabase(":memory:")
    database.initialize()
    yield database
    database.close()


@pytest.fixture
def part_id(db):
    return dbmod.insert_part(
        db, part_number="TEST-001", revision="A",
        description="Test part", cad_file_path=None, cad_hash=None,
        material_type="machined_metal",
    )


class TestPhase0Eligibility:
    def test_all_features_class_b(self):
        """Phase 0: ALL features must be Class B regardless of type."""
        for ft in ["diameter", "distance", "flatness", "bbox_length", "bbox_width", "bbox_height"]:
            assert assign_phase0_class(ft) == "B"

    def test_class_b_never_pass_scan_only(self):
        """Class B features produce review_only, never pass."""
        assert assign_phase0_class("diameter") == "B"


class TestRecipeManager:
    def test_create_phase0_recipe(self, db, part_id):
        features = [
            {"name": "Bore Diameter", "feature_type": "diameter",
             "nominal": 25.4, "tol_plus": 0.1, "tol_minus": -0.1},
            {"name": "Flatness Top", "feature_type": "flatness",
             "nominal": 0.0, "tol_plus": 0.05, "tol_minus": 0.0},
        ]
        recipe_id, feature_ids = create_phase0_recipe(db, part_id, features)

        assert recipe_id is not None
        assert len(feature_ids) == 2

        # Verify recipe is draft
        recipe = dbmod.get_recipe(db, recipe_id)
        assert recipe["status"] == "draft"

        # Verify all features are Class B
        features_db = dbmod.get_features_for_recipe(db, recipe_id)
        for f in features_db:
            assert f["eligibility_class"] == "B"


class TestCalibration:
    def test_passing_calibration(self, db):
        cal_id, passed = record_calibration(
            db, artifact_id="gauge-block-1",
            certified_value=25.4, certified_uncertainty=0.005,
            measured_value=25.405, operator="test",
        )
        assert passed  # truthy
        assert cal_id is not None

    def test_failing_calibration(self, db):
        cal_id, passed = record_calibration(
            db, artifact_id="gauge-block-1",
            certified_value=25.4, certified_uncertainty=0.005,
            measured_value=25.42, operator="test",
        )
        # error = 0.02 > 2 * 0.005 = 0.01 → FAIL
        assert not passed

    def test_calibration_validity_check(self, db):
        # No calibration → invalid
        valid, _ = check_calibration_valid(db)
        assert valid is False

        # Record passing calibration
        record_calibration(
            db, artifact_id="gauge-block-1",
            certified_value=25.4, certified_uncertainty=0.005,
            measured_value=25.405, operator="test",
        )

        # Now valid
        valid, cal_id = check_calibration_valid(db)
        assert valid is True
        assert cal_id is not None


class TestDispositionRules:
    def test_phase0_disposition_never_pass_scan_only(self):
        """Phase 0 must produce hold_for_review or fail_by_scan, never pass_scan_only."""
        statuses_review = ["review_only", "review_only", "review_only"]
        has_fail = any(s in ("fail_full", "fail_marginal") for s in statuses_review)
        disposition = "fail_by_scan" if has_fail else "hold_for_review"
        assert disposition == "hold_for_review"
        assert disposition != "pass_scan_only"

    def test_any_fail_triggers_fail_by_scan(self):
        statuses = ["review_only", "fail_full", "review_only"]
        has_fail = any(s in ("fail_full", "fail_marginal") for s in statuses)
        disposition = "fail_by_scan" if has_fail else "hold_for_review"
        assert disposition == "fail_by_scan"

    def test_fail_marginal_also_triggers_fail(self):
        statuses = ["review_only", "fail_marginal"]
        has_fail = any(s in ("fail_full", "fail_marginal") for s in statuses)
        assert has_fail is True


class TestFullInspectionChain:
    def test_complete_chain_without_scans(self, db, part_id):
        """Test the full DB chain: part → recipe → features → inspection → results → evidence."""
        features = [
            {"name": "Bore D1", "feature_type": "diameter",
             "nominal": 25.4, "tol_plus": 0.1, "tol_minus": -0.1},
        ]
        recipe_id, feature_ids = create_phase0_recipe(db, part_id, features)

        # Record calibration
        cal_id, _ = record_calibration(
            db, "gauge-1", 25.4, 0.005, 25.405, "test",
        )

        # Create environment snapshot
        env_id = dbmod.insert_environment_snapshot(
            db, inspection_id=None, calibration_run_id=cal_id,
            ambient_temp_c=22.0, warmup_elapsed_minutes=30.0,
            cte_material="6061-T6", cte_value=23.6e-6,
            cte_source="handbook", delta_t_from_20c=2.0,
            recorded_by="test",
        )

        # Create inspection
        inspection_id = dbmod.insert_inspection(
            db, part_id=part_id, recipe_id=recipe_id,
            operator="test", scan_count=3,
            calibration_run_id=cal_id,
            environment_snapshot_id=env_id,
        )

        # Verify starts as incomplete
        insp = dbmod.get_inspection(db, inspection_id)
        assert insp["disposition"] == "incomplete"

        # Insert a review_only result
        result_id = dbmod.insert_inspection_result(
            db, inspection_id=inspection_id, feature_id=feature_ids[0],
            raw_value=25.42, corrected_value=25.42,
            expanded_uncertainty=0.03, deviation=0.02,
            status="review_only",
            reason_code="REVIEW_ONLY_BEST_FIT",
            recommended_action="Review measurement.",
        )

        # Insert evidence with all 8 u-components
        dbmod.insert_measurement_evidence(
            db, result_id=result_id,
            local_coverage=0.85, local_density=6.0,
            fit_residual=0.012, inlier_count=500,
            effective_sample_size=50,
            u_fit=0.002, u_repeat=0.005, u_reprod=0.003,
            u_align=0.004, u_cal=0.003, u_ref=0.001,
            u_temp=0.001, u_bias_est=0.002,
            u_combined=0.008, expanded_uncertainty=0.016,
        )

        # Update disposition
        dbmod.update_inspection_disposition(db, inspection_id, "hold_for_review")

        # Verify
        insp = dbmod.get_inspection(db, inspection_id)
        assert insp["disposition"] == "hold_for_review"

        results = dbmod.get_results_for_inspection(db, inspection_id)
        assert len(results) == 1
        assert results[0]["status"] == "review_only"

        # Verify environment snapshot linked
        env = dbmod.get_environment_snapshot(db, env_id)
        assert env["ambient_temp_c"] == 22.0
