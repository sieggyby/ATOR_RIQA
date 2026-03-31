"""Tests for RIQA database layer.

Validates: schema initialization, CRUD operations, enum enforcement,
foreign key enforcement, and the critical requirement that all 8
uncertainty components must be non-None in MeasurementEvidence.
"""

import pytest

from riqa.data.db import (
    RiqaDatabase,
    insert_calibration_run,
    insert_environment_snapshot,
    insert_inspection,
    insert_inspection_recipe,
    insert_inspection_result,
    insert_measurement_evidence,
    insert_measurement_feature,
    insert_part,
    get_environment_snapshot,
    get_environment_snapshot_for_inspection,
    get_evidence_for_result,
    get_features_for_recipe,
    get_inspection,
    get_latest_calibration,
    get_part,
    get_part_by_number_revision,
    get_recipe,
    get_results_for_inspection,
    update_inspection_alignment,
    update_inspection_disposition,
)


@pytest.fixture
def db():
    """In-memory database, initialized with schema."""
    database = RiqaDatabase(":memory:")
    database.initialize()
    yield database
    database.close()


@pytest.fixture
def seeded_db(db):
    """Database with a Part, Recipe, Feature, CalibrationRun, and EnvironmentSnapshot."""
    part_id = insert_part(
        db, "TEST-001", "A", "Test part", "/cad/test.step", "abc123", "machined_metal",
    )
    recipe_id = insert_inspection_recipe(
        db, part_id, "1", "Creality Ferret SE", "0.0.1",
    )
    feature_id = insert_measurement_feature(
        db, recipe_id, "Hole A diameter", "diameter", 10.0, 0.1, -0.1,
        eligibility_class="B",
    )
    cal_id = insert_calibration_run(
        db, "Creality Ferret SE", "SCANNER-001", "gauge-block-1",
        25.4, 0.005, 25.41, "operator1", 22.0,
    )
    inspection_id = insert_inspection(
        db, part_id, recipe_id, "operator1",
        scanner_asset_id="SCANNER-001", scan_count=3,
        calibration_run_id=cal_id,
    )
    env_id = insert_environment_snapshot(
        db, inspection_id, None, 22.0, 35.0,
        "6061-T6 aluminum", 23.6, "MatWeb", 2.0, "operator1",
    )
    return {
        "db": db,
        "part_id": part_id,
        "recipe_id": recipe_id,
        "feature_id": feature_id,
        "cal_id": cal_id,
        "inspection_id": inspection_id,
        "env_id": env_id,
    }


# ---- Schema initialization ----

class TestSchemaInit:
    def test_initialize_creates_tables(self, db):
        tables = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {t["name"] for t in tables}
        expected = {
            "part", "inspection_recipe", "measurement_feature", "feature_capability",
            "msa_study", "receiving_context", "environment_snapshot", "calibration_run",
            "inspection", "inspection_result", "measurement_evidence",
            "batch_plate_layout", "batch_inspection", "batch_slot",
        }
        assert expected.issubset(table_names)

    def test_initialize_is_idempotent(self, db):
        """Schema init can be called multiple times without error."""
        db.initialize()
        db.initialize()

    def test_foreign_keys_enabled(self, db):
        """Foreign keys must be ON after initialize() — not just after __init__."""
        result = db.conn.execute("PRAGMA foreign_keys").fetchone()
        assert result[0] == 1


# ---- Part CRUD ----

class TestPart:
    def test_insert_and_get(self, db):
        pid = insert_part(db, "P-100", "B", "Widget", "/cad/p100.step", "hash1", "injection_molded")
        part = get_part(db, pid)
        assert part is not None
        assert part["part_number"] == "P-100"
        assert part["revision"] == "B"
        assert part["material_type"] == "injection_molded"

    def test_get_by_number_revision(self, db):
        insert_part(db, "P-200", "C", None, None, None, "fdm_printed")
        part = get_part_by_number_revision(db, "P-200", "C")
        assert part is not None
        assert part["material_type"] == "fdm_printed"

    def test_get_nonexistent_returns_none(self, db):
        assert get_part(db, "nonexistent") is None

    def test_invalid_material_type_raises(self, db):
        with pytest.raises(ValueError, match="material_type"):
            insert_part(db, "P-300", "A", None, None, None, "cardboard")

    def test_duplicate_part_number_revision_raises(self, db):
        insert_part(db, "P-400", "A", None, None, None, "machined_metal")
        with pytest.raises(Exception):  # sqlite3.IntegrityError
            insert_part(db, "P-400", "A", None, None, None, "machined_metal")


# ---- CalibrationRun ----

class TestCalibrationRun:
    def test_insert_and_get_latest(self, db):
        cid = insert_calibration_run(
            db, "Ferret SE", "S-001", "block-1", 25.4, 0.005, 25.405, "op1", 22.0,
        )
        cal = get_latest_calibration(db, "Ferret SE")
        assert cal is not None
        assert cal["id"] == cid
        assert cal["error"] == pytest.approx(0.005)
        assert cal["pass_fail"] == 1  # 0.005 <= 0.005 * 2 = 0.01

    def test_calibration_fail(self, db):
        insert_calibration_run(
            db, "Ferret SE", "S-001", "block-1", 25.4, 0.002, 25.42, "op1",
        )
        cal = get_latest_calibration(db, "Ferret SE")
        assert cal["pass_fail"] == 0  # 0.02 > 0.002 * 2 = 0.004


# ---- InspectionRecipe ----

class TestRecipe:
    def test_insert_and_get(self, seeded_db):
        recipe = get_recipe(seeded_db["db"], seeded_db["recipe_id"])
        assert recipe is not None
        assert recipe["status"] == "draft"
        assert recipe["default_guard_band_method"] == "uncertainty_based"

    def test_invalid_status_raises(self, seeded_db):
        with pytest.raises(ValueError, match="recipe status"):
            insert_inspection_recipe(
                seeded_db["db"], seeded_db["part_id"], "2", "Scanner", "1.0",
                status="approved",
            )

    def test_invalid_guard_band_method_raises(self, seeded_db):
        with pytest.raises(ValueError, match="guard_band_method"):
            insert_inspection_recipe(
                seeded_db["db"], seeded_db["part_id"], "2", "Scanner", "1.0",
                default_guard_band_method="none",
            )


# ---- MeasurementFeature ----

class TestMeasurementFeature:
    def test_insert_and_list(self, seeded_db):
        db = seeded_db["db"]
        features = get_features_for_recipe(db, seeded_db["recipe_id"])
        assert len(features) == 1
        assert features[0]["name"] == "Hole A diameter"
        assert features[0]["eligibility_class"] == "B"

    def test_invalid_feature_type_raises(self, seeded_db):
        with pytest.raises(ValueError, match="feature type"):
            insert_measurement_feature(
                seeded_db["db"], seeded_db["recipe_id"],
                "Angle X", "angle", 45.0, 1.0, -1.0,
            )

    def test_invalid_eligibility_class_raises(self, seeded_db):
        with pytest.raises(ValueError, match="eligibility_class"):
            insert_measurement_feature(
                seeded_db["db"], seeded_db["recipe_id"],
                "Hole B", "diameter", 5.0, 0.1, -0.1,
                eligibility_class="D",
            )


# ---- Inspection ----

class TestInspection:
    def test_insert_and_get(self, seeded_db):
        insp = get_inspection(seeded_db["db"], seeded_db["inspection_id"])
        assert insp is not None
        assert insp["disposition"] == "incomplete"

    def test_update_disposition(self, seeded_db):
        db = seeded_db["db"]
        update_inspection_disposition(db, seeded_db["inspection_id"], "hold_for_review")
        insp = get_inspection(db, seeded_db["inspection_id"])
        assert insp["disposition"] == "hold_for_review"

    def test_invalid_disposition_raises(self, seeded_db):
        with pytest.raises(ValueError, match="disposition"):
            update_inspection_disposition(seeded_db["db"], seeded_db["inspection_id"], "approved")

    def test_inspection_always_starts_incomplete(self, seeded_db):
        """Inspections must start as 'incomplete' — no backdoor to create a passing record."""
        db = seeded_db["db"]
        insp = get_inspection(db, seeded_db["inspection_id"])
        assert insp["disposition"] == "incomplete"

    def test_update_alignment(self, seeded_db):
        db = seeded_db["db"]
        update_inspection_alignment(
            db, seeded_db["inspection_id"], 0.92, 0.03, True, "unconstrained",
        )
        insp = get_inspection(db, seeded_db["inspection_id"])
        assert insp["alignment_fitness"] == pytest.approx(0.92)
        assert insp["alignment_rmse"] == pytest.approx(0.03)
        assert insp["alignment_stable"] == 1
        assert insp["alignment_mode_actual"] == "unconstrained"

    def test_invalid_alignment_mode_raises(self, seeded_db):
        with pytest.raises(ValueError, match="alignment_mode_actual"):
            update_inspection_alignment(
                seeded_db["db"], seeded_db["inspection_id"],
                0.9, 0.03, True, "best_fit",
            )


# ---- InspectionResult ----

class TestInspectionResult:
    def test_insert_and_list(self, seeded_db):
        db = seeded_db["db"]
        rid = insert_inspection_result(
            db, seeded_db["inspection_id"], seeded_db["feature_id"],
            raw_value=10.05, corrected_value=10.02, expanded_uncertainty=0.04,
            deviation=0.02, status="review_only", reason_code="REVIEW_ONLY_BEST_FIT",
        )
        results = get_results_for_inspection(db, seeded_db["inspection_id"])
        assert len(results) == 1
        assert results[0]["id"] == rid
        assert results[0]["status"] == "review_only"

    def test_invalid_status_raises(self, seeded_db):
        with pytest.raises(ValueError, match="result status"):
            insert_inspection_result(
                seeded_db["db"], seeded_db["inspection_id"], seeded_db["feature_id"],
                10.0, 10.0, 0.01, 0.0, "accepted", "PASS",
            )

    def test_invalid_measurement_source_raises(self, seeded_db):
        with pytest.raises(ValueError, match="measurement_source"):
            insert_inspection_result(
                seeded_db["db"], seeded_db["inspection_id"], seeded_db["feature_id"],
                10.0, 10.0, 0.01, 0.0, "pass", "PASS_FULL_CONFIDENCE",
                measurement_source="laser",
            )

    def test_invalid_reason_code_raises(self, seeded_db):
        with pytest.raises(ValueError, match="reason_code"):
            insert_inspection_result(
                seeded_db["db"], seeded_db["inspection_id"], seeded_db["feature_id"],
                10.0, 10.0, 0.01, 0.0, "pass", "MADE_UP_CODE",
            )


# ---- MeasurementEvidence (CRITICAL SAFETY TESTS) ----

class TestMeasurementEvidence:
    """Tests for the most safety-critical database function.

    insert_measurement_evidence MUST require all 8 uncertainty components.
    A record with missing components is unauditable and could mask
    understated uncertainty, leading to false accepts.
    """

    def _make_result(self, seeded_db) -> str:
        return insert_inspection_result(
            seeded_db["db"], seeded_db["inspection_id"], seeded_db["feature_id"],
            10.05, 10.02, 0.04, 0.02, "review_only", "REVIEW_ONLY_BEST_FIT",
        )

    def _valid_evidence_kwargs(self, result_id: str) -> dict:
        return dict(
            result_id=result_id,
            local_coverage=0.85,
            local_density=8.0,
            fit_residual=0.012,
            inlier_count=5000,
            effective_sample_size=200,
            u_fit=0.006,
            u_repeat=0.008,
            u_reprod=0.005,
            u_align=0.003,
            u_cal=0.002,
            u_ref=0.001,
            u_temp=0.001,
            u_bias_est=0.002,
            u_combined=0.012,
            expanded_uncertainty=0.024,
        )

    def test_insert_with_all_components(self, seeded_db):
        db = seeded_db["db"]
        result_id = self._make_result(seeded_db)
        eid = insert_measurement_evidence(db, **self._valid_evidence_kwargs(result_id))
        ev = get_evidence_for_result(db, result_id)
        assert ev is not None
        assert ev["u_fit"] == pytest.approx(0.006)
        assert ev["u_repeat"] == pytest.approx(0.008)
        assert ev["u_reprod"] == pytest.approx(0.005)
        assert ev["u_align"] == pytest.approx(0.003)
        assert ev["u_cal"] == pytest.approx(0.002)
        assert ev["u_ref"] == pytest.approx(0.001)
        assert ev["u_temp"] == pytest.approx(0.001)
        assert ev["u_bias_est"] == pytest.approx(0.002)

    def test_none_u_fit_raises(self, seeded_db):
        result_id = self._make_result(seeded_db)
        kwargs = self._valid_evidence_kwargs(result_id)
        kwargs["u_fit"] = None
        with pytest.raises(ValueError, match="u_fit"):
            insert_measurement_evidence(seeded_db["db"], **kwargs)

    def test_none_u_repeat_raises(self, seeded_db):
        result_id = self._make_result(seeded_db)
        kwargs = self._valid_evidence_kwargs(result_id)
        kwargs["u_repeat"] = None
        with pytest.raises(ValueError, match="u_repeat"):
            insert_measurement_evidence(seeded_db["db"], **kwargs)

    def test_none_u_reprod_raises(self, seeded_db):
        result_id = self._make_result(seeded_db)
        kwargs = self._valid_evidence_kwargs(result_id)
        kwargs["u_reprod"] = None
        with pytest.raises(ValueError, match="u_reprod"):
            insert_measurement_evidence(seeded_db["db"], **kwargs)

    def test_none_u_align_raises(self, seeded_db):
        result_id = self._make_result(seeded_db)
        kwargs = self._valid_evidence_kwargs(result_id)
        kwargs["u_align"] = None
        with pytest.raises(ValueError, match="u_align"):
            insert_measurement_evidence(seeded_db["db"], **kwargs)

    def test_none_u_cal_raises(self, seeded_db):
        result_id = self._make_result(seeded_db)
        kwargs = self._valid_evidence_kwargs(result_id)
        kwargs["u_cal"] = None
        with pytest.raises(ValueError, match="u_cal"):
            insert_measurement_evidence(seeded_db["db"], **kwargs)

    def test_none_u_ref_raises(self, seeded_db):
        result_id = self._make_result(seeded_db)
        kwargs = self._valid_evidence_kwargs(result_id)
        kwargs["u_ref"] = None
        with pytest.raises(ValueError, match="u_ref"):
            insert_measurement_evidence(seeded_db["db"], **kwargs)

    def test_none_u_temp_raises(self, seeded_db):
        result_id = self._make_result(seeded_db)
        kwargs = self._valid_evidence_kwargs(result_id)
        kwargs["u_temp"] = None
        with pytest.raises(ValueError, match="u_temp"):
            insert_measurement_evidence(seeded_db["db"], **kwargs)

    def test_none_u_bias_est_raises(self, seeded_db):
        result_id = self._make_result(seeded_db)
        kwargs = self._valid_evidence_kwargs(result_id)
        kwargs["u_bias_est"] = None
        with pytest.raises(ValueError, match="u_bias_est"):
            insert_measurement_evidence(seeded_db["db"], **kwargs)

    def test_coverage_inflation_below_one_raises(self, seeded_db):
        result_id = self._make_result(seeded_db)
        kwargs = self._valid_evidence_kwargs(result_id)
        kwargs["coverage_inflation_factor"] = 0.9
        with pytest.raises(ValueError, match="coverage_inflation_factor"):
            insert_measurement_evidence(seeded_db["db"], **kwargs)

    def test_fit_correction_below_one_raises(self, seeded_db):
        result_id = self._make_result(seeded_db)
        kwargs = self._valid_evidence_kwargs(result_id)
        kwargs["fit_correction_factor"] = 0.8
        with pytest.raises(ValueError, match="fit_correction_factor"):
            insert_measurement_evidence(seeded_db["db"], **kwargs)


# ---- Foreign key enforcement ----

class TestEnvironmentSnapshot:
    def test_get_by_id(self, seeded_db):
        db = seeded_db["db"]
        snap = get_environment_snapshot(db, seeded_db["env_id"])
        assert snap is not None
        assert snap["ambient_temp_c"] == 22.0

    def test_get_by_inspection(self, seeded_db):
        db = seeded_db["db"]
        snap = get_environment_snapshot_for_inspection(db, seeded_db["inspection_id"])
        assert snap is not None
        assert snap["cte_material"] == "6061-T6 aluminum"


class TestForeignKeys:
    def test_inspection_with_invalid_part_id_raises(self, db):
        """Foreign key: inspection.part_id must reference a real part."""
        # Need a recipe to exist for the FK, so create a part first for recipe
        pid = insert_part(db, "P-FK", "A", None, None, None, "machined_metal")
        rid = insert_inspection_recipe(db, pid, "1", "Scanner", "1.0")
        with pytest.raises(Exception):  # sqlite3.IntegrityError
            insert_inspection(db, "nonexistent_part", rid, "op1")

    def test_inspection_result_with_invalid_inspection_id_raises(self, seeded_db):
        with pytest.raises(Exception):
            insert_inspection_result(
                seeded_db["db"], "nonexistent_inspection", seeded_db["feature_id"],
                10.0, 10.0, 0.01, 0.0, "pass", "PASS_FULL_CONFIDENCE",
            )

    def test_measurement_evidence_with_invalid_result_id_raises(self, seeded_db):
        kwargs = dict(
            result_id="nonexistent_result",
            local_coverage=0.85, local_density=8.0, fit_residual=0.01,
            inlier_count=5000, effective_sample_size=200,
            u_fit=0.006, u_repeat=0.008, u_reprod=0.005, u_align=0.003,
            u_cal=0.002, u_ref=0.001, u_temp=0.001, u_bias_est=0.002,
            u_combined=0.012, expanded_uncertainty=0.024,
        )
        with pytest.raises(Exception):
            insert_measurement_evidence(seeded_db["db"], **kwargs)


# ---- Full chain: Part -> Recipe -> Feature -> Inspection -> Result -> Evidence ----

class TestFullChain:
    def test_complete_inspection_chain(self, seeded_db):
        """Insert a complete inspection chain and verify all data is retrievable."""
        db = seeded_db["db"]
        inspection_id = seeded_db["inspection_id"]

        # Add alignment data
        update_inspection_alignment(db, inspection_id, 0.91, 0.04, True, "unconstrained")

        # Add a result
        result_id = insert_inspection_result(
            db, inspection_id, seeded_db["feature_id"],
            raw_value=10.05, corrected_value=10.02, expanded_uncertainty=0.04,
            deviation=0.02, status="review_only", reason_code="REVIEW_ONLY_BEST_FIT",
        )

        # Add evidence with all 8 components
        evidence_id = insert_measurement_evidence(
            db, result_id,
            local_coverage=0.82, local_density=6.5, fit_residual=0.015,
            inlier_count=4200, effective_sample_size=180,
            u_fit=0.007, u_repeat=0.009, u_reprod=0.006, u_align=0.004,
            u_cal=0.003, u_ref=0.001, u_temp=0.002, u_bias_est=0.002,
            u_combined=0.014, expanded_uncertainty=0.028,
            incidence_angle_median=35.0, inter_scan_stddev=0.008,
            alignment_sensitivity=0.003, boundary_proximity=5.2,
        )

        # Update disposition
        update_inspection_disposition(db, inspection_id, "hold_for_review")

        # Verify the full chain
        insp = get_inspection(db, inspection_id)
        assert insp["disposition"] == "hold_for_review"
        assert insp["alignment_fitness"] == pytest.approx(0.91)

        results = get_results_for_inspection(db, inspection_id)
        assert len(results) == 1
        assert results[0]["status"] == "review_only"

        ev = get_evidence_for_result(db, results[0]["id"])
        assert ev is not None
        # Verify all 8 uncertainty components present and non-None
        for component in ["u_fit", "u_repeat", "u_reprod", "u_align",
                          "u_cal", "u_ref", "u_temp", "u_bias_est"]:
            assert ev[component] is not None, f"{component} is None in evidence record"
            assert ev[component] > 0, f"{component} is zero in evidence record"
