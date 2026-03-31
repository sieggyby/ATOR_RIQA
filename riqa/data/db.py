"""RIQA database layer — SQLite connection management and CRUD operations.

All entity inserts validate constraints before executing. MeasurementEvidence
inserts require all 8 uncertainty components as explicit non-None parameters.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

# --- Valid enum values (must match schema.sql CHECK constraints) ---

VALID_MATERIAL_TYPES = frozenset({
    "machined_metal", "injection_molded", "fdm_printed", "sla_printed",
})

VALID_DISPOSITIONS = frozenset({
    "pass_scan_only", "pass_after_manual", "fail_by_scan", "fail_after_manual",
    "hold_for_review", "accepted_under_deviation", "incomplete", "fail_by_batch_override",
})

VALID_RESULT_STATUSES = frozenset({
    "pass", "fail_full", "fail_marginal", "marginal_outside", "marginal_inside",
    "rescan_needed", "manual_required", "review_only", "blocked",
})

VALID_FEATURE_TYPES = frozenset({
    "diameter", "distance", "bbox_length", "bbox_width", "bbox_height", "flatness",
})

VALID_ELIGIBILITY_CLASSES = frozenset({"A", "B", "C"})

VALID_CRITICALITY = frozenset({"critical", "noncritical"})

VALID_GUARD_BAND_METHODS = frozenset({
    "simple_percentage", "uncertainty_based", "shared_risk",
})

VALID_RECIPE_STATUSES = frozenset({"draft", "active", "superseded", "revoked"})

VALID_DATUM_OBSERVABILITY_METHODS = frozenset({
    "fiducials", "fixture_geometry", "datum_features", "marker_board",
})

VALID_ALIGNMENT_MODES = frozenset({
    "datum_constrained", "fixture_assisted", "unconstrained",
})

VALID_ALIGNMENT_MODES_ACTUAL = frozenset({
    "datum_observed", "fixture_geometry", "datum_features", "unconstrained",
})

VALID_MSA_TIERS = frozenset({"screening", "release"})

VALID_INSPECTION_LEVELS = frozenset({"normal", "tightened", "reduced"})

VALID_LOT_DISPOSITIONS = frozenset({
    "pending", "lot_accept", "lot_reject", "lot_hold", "lot_accepted_under_deviation",
})

VALID_MEASUREMENT_SOURCES = frozenset({"scan", "manual"})

# Reason codes from spec Section 8.3
VALID_REASON_CODES = frozenset({
    "PASS_FULL_CONFIDENCE", "PASS_WITH_GUARD_BAND",
    "FAIL_FULL_CONFIDENCE", "FAIL_MARGINAL",
    "MARGINAL_OUTSIDE", "MARGINAL_INSIDE",
    "RESCAN_LOW_COVERAGE", "RESCAN_HIGH_NOISE",
    "MANUAL_ALIGNMENT_SENSITIVE", "MANUAL_FEATURE_TOO_SMALL",
    "MANUAL_NOT_SCAN_ELIGIBLE",
    "BLOCKED_CALIBRATION", "BLOCKED_RECIPE_MISMATCH",
    "REVIEW_ONLY_BEST_FIT", "REVIEW_ONLY_ALIGNMENT_DEGRADED",
    "REVIEW_ONLY_CONFIDENCE_DEMOTED",
    # Batch mode reason codes
    "PLATE_LOCALIZATION_FAILED", "PLATE_POSE_POOR", "PLATE_COVERAGE_INSUFFICIENT",
    "SLOT_OCCUPANCY_MISMATCH", "SLOT_ASSIGNMENT_UNCERTAIN",
    "SLOT_CONTAMINATED", "SLOT_MULTI_CLUSTER", "SLOT_SPARSE",
})

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _new_id() -> str:
    return uuid4().hex


def _validate_enum(value: str, valid_values: frozenset[str], field_name: str) -> None:
    if value not in valid_values:
        raise ValueError(
            f"Invalid {field_name}: {value!r}. Must be one of: {sorted(valid_values)}"
        )


class RiqaDatabase:
    """SQLite database connection with schema initialization and foreign key enforcement."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

    def initialize(self) -> None:
        """Execute schema.sql to create all tables. Idempotent."""
        schema_sql = _SCHEMA_PATH.read_text()
        self.conn.executescript(schema_sql)
        # executescript() may reset PRAGMA state — re-enable foreign keys defensively
        self.conn.execute("PRAGMA foreign_keys=ON")

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> RiqaDatabase:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Part
# ---------------------------------------------------------------------------

def insert_part(
    db: RiqaDatabase,
    part_number: str,
    revision: str,
    description: str | None,
    cad_file_path: str | None,
    cad_hash: str | None,
    material_type: str,
) -> str:
    _validate_enum(material_type, VALID_MATERIAL_TYPES, "material_type")
    pid = _new_id()
    db.conn.execute(
        """INSERT INTO part (id, part_number, revision, description, cad_file_path, cad_hash, material_type)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (pid, part_number, revision, description, cad_file_path, cad_hash, material_type),
    )
    db.conn.commit()
    return pid


def get_part(db: RiqaDatabase, part_id: str) -> dict | None:
    row = db.conn.execute("SELECT * FROM part WHERE id = ?", (part_id,)).fetchone()
    return dict(row) if row else None


def get_part_by_number_revision(db: RiqaDatabase, part_number: str, revision: str) -> dict | None:
    row = db.conn.execute(
        "SELECT * FROM part WHERE part_number = ? AND revision = ?",
        (part_number, revision),
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# CalibrationRun
# ---------------------------------------------------------------------------

def insert_calibration_run(
    db: RiqaDatabase,
    scanner_model: str,
    scanner_asset_id: str | None,
    artifact_id: str,
    artifact_certified_value: float,
    artifact_cert_uncertainty: float,
    measured_value: float,
    operator: str,
    environment_temp_c: float | None = None,
    environment_notes: str | None = None,
) -> str:
    cid = _new_id()
    error = measured_value - artifact_certified_value
    pass_fail = abs(error) <= artifact_cert_uncertainty * 2
    db.conn.execute(
        """INSERT INTO calibration_run
           (id, scanner_model, scanner_asset_id, artifact_id, artifact_certified_value,
            artifact_cert_uncertainty, measured_value, error, pass_fail, operator,
            environment_temp_c, environment_notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (cid, scanner_model, scanner_asset_id, artifact_id, artifact_certified_value,
         artifact_cert_uncertainty, measured_value, error, pass_fail, operator,
         environment_temp_c, environment_notes),
    )
    db.conn.commit()
    return cid


def get_latest_calibration(db: RiqaDatabase, scanner_model: str) -> dict | None:
    row = db.conn.execute(
        "SELECT * FROM calibration_run WHERE scanner_model = ? ORDER BY created_at DESC LIMIT 1",
        (scanner_model,),
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# EnvironmentSnapshot
# ---------------------------------------------------------------------------

def insert_environment_snapshot(
    db: RiqaDatabase,
    inspection_id: str | None,
    calibration_run_id: str | None,
    ambient_temp_c: float,
    warmup_elapsed_minutes: float,
    cte_material: str,
    cte_value: float,
    cte_source: str,
    delta_t_from_20c: float,
    recorded_by: str,
    part_temp_c: float | None = None,
    humidity_percent: float | None = None,
) -> str:
    eid = _new_id()
    db.conn.execute(
        """INSERT INTO environment_snapshot
           (id, inspection_id, calibration_run_id, ambient_temp_c, part_temp_c,
            humidity_percent, warmup_elapsed_minutes, cte_material, cte_value,
            cte_source, delta_t_from_20c, recorded_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (eid, inspection_id, calibration_run_id, ambient_temp_c, part_temp_c,
         humidity_percent, warmup_elapsed_minutes, cte_material, cte_value,
         cte_source, delta_t_from_20c, recorded_by),
    )
    db.conn.commit()
    return eid


def get_environment_snapshot(db: RiqaDatabase, snapshot_id: str) -> dict | None:
    row = db.conn.execute(
        "SELECT * FROM environment_snapshot WHERE id = ?", (snapshot_id,),
    ).fetchone()
    return dict(row) if row else None


def get_environment_snapshot_for_inspection(db: RiqaDatabase, inspection_id: str) -> dict | None:
    row = db.conn.execute(
        "SELECT * FROM environment_snapshot WHERE inspection_id = ?", (inspection_id,),
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# InspectionRecipe
# ---------------------------------------------------------------------------

def insert_inspection_recipe(
    db: RiqaDatabase,
    part_id: str,
    revision: str,
    scanner_model: str,
    software_version: str,
    status: str = "draft",
    fixture_id: str | None = None,
    fixture_notes: str | None = None,
    datum_observability_method: str | None = None,
    scan_preset: str | None = None,
    surface_prep: str | None = None,
    required_scan_count: int = 3,
    datum_scheme: str | None = None,
    alignment_mode: str | None = None,
    default_guard_band_method: str = "uncertainty_based",
    default_guard_band_percent: float = 10.0,
    msa_study_id: str | None = None,
    approved_by: str | None = None,
    scanner_firmware: str | None = None,
) -> str:
    _validate_enum(status, VALID_RECIPE_STATUSES, "recipe status")
    _validate_enum(default_guard_band_method, VALID_GUARD_BAND_METHODS, "guard_band_method")
    if datum_observability_method is not None:
        _validate_enum(datum_observability_method, VALID_DATUM_OBSERVABILITY_METHODS,
                        "datum_observability_method")
    if alignment_mode is not None:
        _validate_enum(alignment_mode, VALID_ALIGNMENT_MODES, "alignment_mode")
    rid = _new_id()
    db.conn.execute(
        """INSERT INTO inspection_recipe
           (id, part_id, revision, scanner_model, scanner_firmware, software_version,
            fixture_id, fixture_notes, datum_observability_method, scan_preset,
            surface_prep, required_scan_count, datum_scheme, alignment_mode,
            default_guard_band_method, default_guard_band_percent, msa_study_id,
            approved_by, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (rid, part_id, revision, scanner_model, scanner_firmware, software_version,
         fixture_id, fixture_notes, datum_observability_method, scan_preset,
         surface_prep, required_scan_count, datum_scheme, alignment_mode,
         default_guard_band_method, default_guard_band_percent, msa_study_id,
         approved_by, status),
    )
    db.conn.commit()
    return rid


def get_recipe(db: RiqaDatabase, recipe_id: str) -> dict | None:
    row = db.conn.execute("SELECT * FROM inspection_recipe WHERE id = ?", (recipe_id,)).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# MeasurementFeature
# ---------------------------------------------------------------------------

def insert_measurement_feature(
    db: RiqaDatabase,
    recipe_id: str,
    name: str,
    feature_type: str,
    nominal: float,
    tolerance_plus: float,
    tolerance_minus: float,
    eligibility_class: str = "C",
    criticality: str = "noncritical",
    cad_feature_ref: str | None = None,
    sort_order: int = 0,
    guard_band_method: str | None = None,
    guard_band_percent: float | None = None,
    shared_risk_approval: str | None = None,
    class_justification: str | None = None,
) -> str:
    _validate_enum(feature_type, VALID_FEATURE_TYPES, "feature type")
    _validate_enum(eligibility_class, VALID_ELIGIBILITY_CLASSES, "eligibility_class")
    _validate_enum(criticality, VALID_CRITICALITY, "criticality")
    if guard_band_method is not None:
        _validate_enum(guard_band_method, VALID_GUARD_BAND_METHODS, "guard_band_method")
    fid = _new_id()
    db.conn.execute(
        """INSERT INTO measurement_feature
           (id, recipe_id, name, type, nominal, tolerance_plus, tolerance_minus,
            cad_feature_ref, sort_order, eligibility_class, criticality,
            guard_band_method, guard_band_percent, shared_risk_approval, class_justification)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (fid, recipe_id, name, feature_type, nominal, tolerance_plus, tolerance_minus,
         cad_feature_ref, sort_order, eligibility_class, criticality,
         guard_band_method, guard_band_percent, shared_risk_approval, class_justification),
    )
    db.conn.commit()
    return fid


def get_features_for_recipe(db: RiqaDatabase, recipe_id: str) -> list[dict]:
    rows = db.conn.execute(
        "SELECT * FROM measurement_feature WHERE recipe_id = ? ORDER BY sort_order",
        (recipe_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Inspection
# ---------------------------------------------------------------------------

def insert_inspection(
    db: RiqaDatabase,
    part_id: str,
    recipe_id: str,
    operator: str,
    scanner_asset_id: str | None = None,
    fixture_asset_id: str | None = None,
    scan_count: int | None = None,
    receiving_context_id: str | None = None,
    recipe_revision: str | None = None,
    calibration_run_id: str | None = None,
    environment_snapshot_id: str | None = None,
) -> str:
    # Inspections always start as 'incomplete'. Disposition is set via
    # update_inspection_disposition after the pipeline runs. This prevents
    # creating a passing inspection record that bypasses all gate checks.
    disposition = "incomplete"
    iid = _new_id()
    db.conn.execute(
        """INSERT INTO inspection
           (id, part_id, recipe_id, receiving_context_id, recipe_revision, operator,
            scanner_asset_id, fixture_asset_id, scan_count, calibration_run_id,
            environment_snapshot_id, disposition)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (iid, part_id, recipe_id, receiving_context_id, recipe_revision, operator,
         scanner_asset_id, fixture_asset_id, scan_count, calibration_run_id,
         environment_snapshot_id, disposition),
    )
    db.conn.commit()
    return iid


def update_inspection_disposition(db: RiqaDatabase, inspection_id: str, disposition: str) -> None:
    _validate_enum(disposition, VALID_DISPOSITIONS, "disposition")
    db.conn.execute(
        "UPDATE inspection SET disposition = ? WHERE id = ?",
        (disposition, inspection_id),
    )
    db.conn.commit()


def update_inspection_alignment(
    db: RiqaDatabase,
    inspection_id: str,
    fitness: float,
    rmse: float,
    stable: bool,
    mode: str,
) -> None:
    _validate_enum(mode, VALID_ALIGNMENT_MODES_ACTUAL, "alignment_mode_actual")
    db.conn.execute(
        """UPDATE inspection
           SET alignment_fitness = ?, alignment_rmse = ?, alignment_stable = ?,
               alignment_mode_actual = ?
           WHERE id = ?""",
        (fitness, rmse, stable, mode, inspection_id),
    )
    db.conn.commit()


def get_inspection(db: RiqaDatabase, inspection_id: str) -> dict | None:
    row = db.conn.execute("SELECT * FROM inspection WHERE id = ?", (inspection_id,)).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# InspectionResult
# ---------------------------------------------------------------------------

def insert_inspection_result(
    db: RiqaDatabase,
    inspection_id: str,
    feature_id: str,
    raw_value: float | None,
    corrected_value: float | None,
    expanded_uncertainty: float | None,
    deviation: float | None,
    status: str,
    reason_code: str,
    recommended_action: str | None = None,
    measurement_source: str = "scan",
    manual_gauge_id: str | None = None,
    manual_gauge_cal_due: str | None = None,
) -> str:
    _validate_enum(status, VALID_RESULT_STATUSES, "result status")
    _validate_enum(reason_code, VALID_REASON_CODES, "reason_code")
    _validate_enum(measurement_source, VALID_MEASUREMENT_SOURCES, "measurement_source")
    rid = _new_id()
    db.conn.execute(
        """INSERT INTO inspection_result
           (id, inspection_id, feature_id, raw_value, corrected_value, expanded_uncertainty,
            deviation, status, reason_code, recommended_action, measurement_source,
            manual_gauge_id, manual_gauge_cal_due)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (rid, inspection_id, feature_id, raw_value, corrected_value, expanded_uncertainty,
         deviation, status, reason_code, recommended_action, measurement_source,
         manual_gauge_id, manual_gauge_cal_due),
    )
    db.conn.commit()
    return rid


def get_results_for_inspection(db: RiqaDatabase, inspection_id: str) -> list[dict]:
    rows = db.conn.execute(
        "SELECT * FROM inspection_result WHERE inspection_id = ?",
        (inspection_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# MeasurementEvidence
# ---------------------------------------------------------------------------

def insert_measurement_evidence(
    db: RiqaDatabase,
    result_id: str,
    local_coverage: float,
    local_density: float,
    fit_residual: float,
    inlier_count: int,
    effective_sample_size: int,
    # All 8 uncertainty components are REQUIRED — no defaults, no **kwargs.
    u_fit: float,
    u_repeat: float,
    u_reprod: float,
    u_align: float,
    u_cal: float,
    u_ref: float,
    u_temp: float,
    u_bias_est: float,
    u_combined: float,
    expanded_uncertainty: float,
    coverage_inflation_factor: float = 1.0,
    fit_correction_factor: float = 1.0,
    incidence_angle_median: float | None = None,
    inter_scan_stddev: float | None = None,
    alignment_sensitivity: float | None = None,
    boundary_proximity: float | None = None,
    slot_assignment_confidence: float | None = None,
    cluster_count: int | None = None,
    cross_slot_contamination: float | None = None,
) -> str:
    # Enforce all 8 uncertainty components are not None.
    # This is a hard requirement — a MeasurementEvidence record with missing
    # uncertainty data is unauditable and must never be persisted.
    u_components = {
        "u_fit": u_fit, "u_repeat": u_repeat, "u_reprod": u_reprod,
        "u_align": u_align, "u_cal": u_cal, "u_ref": u_ref,
        "u_temp": u_temp, "u_bias_est": u_bias_est,
    }
    for name, value in u_components.items():
        if value is None:
            raise ValueError(
                f"Uncertainty component {name} is None. All 8 GUM components must be "
                f"explicitly computed — silent zeros are not permitted."
            )

    if coverage_inflation_factor < 1.0:
        raise ValueError(
            f"coverage_inflation_factor={coverage_inflation_factor} is < 1.0. "
            f"Coverage inflation must never deflate uncertainty."
        )

    if fit_correction_factor < 1.0:
        raise ValueError(
            f"fit_correction_factor={fit_correction_factor} is < 1.0. "
            f"c_fit must be >= 1.0 (empirical correction inflates, never deflates)."
        )

    eid = _new_id()
    db.conn.execute(
        """INSERT INTO measurement_evidence
           (id, result_id, local_coverage, local_density, incidence_angle_median,
            fit_residual, inter_scan_stddev, alignment_sensitivity, boundary_proximity,
            inlier_count, effective_sample_size, fit_correction_factor,
            u_fit, u_repeat, u_reprod, u_align, u_cal, u_ref, u_temp, u_bias_est,
            u_combined, coverage_inflation_factor, expanded_uncertainty,
            slot_assignment_confidence, cluster_count, cross_slot_contamination)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (eid, result_id, local_coverage, local_density, incidence_angle_median,
         fit_residual, inter_scan_stddev, alignment_sensitivity, boundary_proximity,
         inlier_count, effective_sample_size, fit_correction_factor,
         u_fit, u_repeat, u_reprod, u_align, u_cal, u_ref, u_temp, u_bias_est,
         u_combined, coverage_inflation_factor, expanded_uncertainty,
         slot_assignment_confidence, cluster_count, cross_slot_contamination),
    )
    db.conn.commit()
    return eid


def get_evidence_for_result(db: RiqaDatabase, result_id: str) -> dict | None:
    row = db.conn.execute(
        "SELECT * FROM measurement_evidence WHERE result_id = ?",
        (result_id,),
    ).fetchone()
    return dict(row) if row else None
