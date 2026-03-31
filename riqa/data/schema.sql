-- RIQA Database Schema
-- Based on spec Section 12

CREATE TABLE IF NOT EXISTS part (
    id TEXT PRIMARY KEY,
    part_number TEXT NOT NULL,
    revision TEXT NOT NULL,
    description TEXT,
    cad_file_path TEXT,
    cad_hash TEXT,
    material_type TEXT CHECK(material_type IN ('machined_metal', 'injection_molded', 'fdm_printed', 'sla_printed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(part_number, revision)
);

CREATE TABLE IF NOT EXISTS inspection_recipe (
    id TEXT PRIMARY KEY,
    part_id TEXT NOT NULL REFERENCES part(id),
    revision TEXT NOT NULL,
    scanner_model TEXT NOT NULL,
    scanner_firmware TEXT,
    software_version TEXT NOT NULL,
    fixture_id TEXT,
    fixture_notes TEXT,
    datum_observability_method TEXT CHECK(datum_observability_method IN ('fiducials', 'fixture_geometry', 'datum_features', 'marker_board')),
    scan_preset TEXT,  -- JSON
    surface_prep TEXT,
    required_scan_count INTEGER DEFAULT 3,
    datum_scheme TEXT,  -- JSON
    alignment_mode TEXT CHECK(alignment_mode IN ('datum_constrained', 'fixture_assisted', 'unconstrained')),
    default_guard_band_method TEXT CHECK(default_guard_band_method IN ('simple_percentage', 'uncertainty_based', 'shared_risk')) DEFAULT 'uncertainty_based',
    default_guard_band_percent REAL DEFAULT 10.0,
    msa_study_id TEXT REFERENCES msa_study(id),
    approved_by TEXT,
    approved_at TIMESTAMP,
    status TEXT CHECK(status IN ('draft', 'active', 'superseded', 'revoked')) DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS measurement_feature (
    id TEXT PRIMARY KEY,
    recipe_id TEXT NOT NULL REFERENCES inspection_recipe(id),
    name TEXT NOT NULL,
    type TEXT CHECK(type IN ('diameter', 'distance', 'bbox_length', 'bbox_width', 'bbox_height', 'flatness')),
    nominal REAL NOT NULL,
    tolerance_plus REAL NOT NULL,
    tolerance_minus REAL NOT NULL,
    cad_feature_ref TEXT,  -- JSON
    sort_order INTEGER DEFAULT 0,
    eligibility_class TEXT CHECK(eligibility_class IN ('A', 'B', 'C')) DEFAULT 'C',
    criticality TEXT CHECK(criticality IN ('critical', 'noncritical')) DEFAULT 'noncritical',
    guard_band_method TEXT CHECK(guard_band_method IN ('simple_percentage', 'uncertainty_based', 'shared_risk')),
    guard_band_percent REAL,
    shared_risk_approval TEXT,
    class_justification TEXT
);

CREATE TABLE IF NOT EXISTS feature_capability (
    id TEXT PRIMARY KEY,
    feature_id TEXT NOT NULL REFERENCES measurement_feature(id),
    msa_study_id TEXT NOT NULL REFERENCES msa_study(id),
    bias REAL,
    repeatability_2sigma REAL,
    reproducibility_2sigma REAL,
    gage_rr_percent REAL,
    ndc INTEGER,
    fit_correction_factor REAL DEFAULT 1.0,
    alignment_sensitivity REAL,
    min_coverage_required REAL,
    min_density_required REAL,
    validated_min_feature_size REAL,
    max_uncertainty_for_autopass REAL,
    max_fit_residual REAL,
    slot_group TEXT
);

CREATE TABLE IF NOT EXISTS msa_study (
    id TEXT PRIMARY KEY,
    recipe_id TEXT NOT NULL REFERENCES inspection_recipe(id),
    tier TEXT CHECK(tier IN ('screening', 'release')) NOT NULL,
    operators TEXT,  -- JSON
    part_serials TEXT,  -- JSON
    sessions_per_operator INTEGER,
    reference_instrument TEXT,
    reference_instrument_asset_id TEXT,
    reference_instrument_cal_date DATE,
    reference_instrument_cal_due DATE,
    reference_instrument_uncertainty REAL,
    reference_instrument_cert_authority TEXT,
    completed_at TIMESTAMP,
    raw_data_path TEXT
);

CREATE TABLE IF NOT EXISTS receiving_context (
    id TEXT PRIMARY KEY,
    supplier_id TEXT,
    purchase_order TEXT,
    lot_number TEXT,
    serial_number TEXT,
    inspection_level TEXT CHECK(inspection_level IN ('normal', 'tightened', 'reduced')) DEFAULT 'normal',
    sample_plan TEXT,
    quantity_received INTEGER,
    quantity_to_inspect INTEGER,
    lot_disposition TEXT CHECK(lot_disposition IN ('pending', 'lot_accept', 'lot_reject', 'lot_hold', 'lot_accepted_under_deviation')) DEFAULT 'pending',
    lot_disposition_by TEXT,
    lot_disposition_at TIMESTAMP,
    lot_disposition_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS environment_snapshot (
    id TEXT PRIMARY KEY,
    inspection_id TEXT REFERENCES inspection(id),
    calibration_run_id TEXT REFERENCES calibration_run(id),
    ambient_temp_c REAL,
    part_temp_c REAL,
    humidity_percent REAL,
    warmup_elapsed_minutes REAL,
    cte_material TEXT,
    cte_value REAL,
    cte_source TEXT,
    delta_t_from_20c REAL,
    recorded_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS calibration_run (
    id TEXT PRIMARY KEY,
    scanner_model TEXT,
    scanner_asset_id TEXT,
    artifact_id TEXT,
    artifact_certified_value REAL,
    artifact_cert_uncertainty REAL,
    measured_value REAL,
    error REAL,
    pass_fail BOOLEAN,
    operator TEXT,
    environment_temp_c REAL,
    environment_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS inspection (
    id TEXT PRIMARY KEY,
    part_id TEXT NOT NULL REFERENCES part(id),
    recipe_id TEXT NOT NULL REFERENCES inspection_recipe(id),
    receiving_context_id TEXT REFERENCES receiving_context(id),
    recipe_revision TEXT,
    operator TEXT,
    scanner_asset_id TEXT,
    fixture_asset_id TEXT,
    scan_count INTEGER,
    alignment_fitness REAL,
    alignment_rmse REAL,
    alignment_stable BOOLEAN,
    alignment_mode_actual TEXT CHECK(alignment_mode_actual IN ('datum_observed', 'fixture_geometry', 'datum_features', 'unconstrained')),
    calibration_run_id TEXT REFERENCES calibration_run(id),
    environment_snapshot_id TEXT REFERENCES environment_snapshot(id),
    batch_inspection_id TEXT REFERENCES batch_inspection(id),
    batch_slot_id TEXT REFERENCES batch_slot(id),
    disposition TEXT CHECK(disposition IN (
        'pass_scan_only', 'pass_after_manual', 'fail_by_scan', 'fail_after_manual',
        'hold_for_review', 'accepted_under_deviation', 'incomplete', 'fail_by_batch_override'
    )),
    notes TEXT,
    report_pdf_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS inspection_result (
    id TEXT PRIMARY KEY,
    inspection_id TEXT NOT NULL REFERENCES inspection(id),
    feature_id TEXT NOT NULL REFERENCES measurement_feature(id),
    raw_value REAL,
    corrected_value REAL,
    expanded_uncertainty REAL,
    deviation REAL,
    status TEXT CHECK(status IN (
        'pass', 'fail_full', 'fail_marginal', 'marginal_outside', 'marginal_inside',
        'rescan_needed', 'manual_required', 'review_only', 'blocked'
    )),
    reason_code TEXT,
    recommended_action TEXT,
    measurement_source TEXT CHECK(measurement_source IN ('scan', 'manual')) DEFAULT 'scan',
    manual_gauge_id TEXT,
    manual_gauge_cal_due DATE
);

CREATE TABLE IF NOT EXISTS measurement_evidence (
    id TEXT PRIMARY KEY,
    result_id TEXT NOT NULL REFERENCES inspection_result(id),
    local_coverage REAL,
    local_density REAL,
    incidence_angle_median REAL,
    fit_residual REAL,
    inter_scan_stddev REAL,
    alignment_sensitivity REAL,
    boundary_proximity REAL,
    inlier_count INTEGER,
    effective_sample_size INTEGER,
    fit_correction_factor REAL NOT NULL DEFAULT 1.0 CHECK(fit_correction_factor >= 1.0),
    u_fit REAL NOT NULL,
    u_repeat REAL NOT NULL,
    u_reprod REAL NOT NULL,
    u_align REAL NOT NULL,
    u_cal REAL NOT NULL,
    u_ref REAL NOT NULL,
    u_temp REAL NOT NULL,
    u_bias_est REAL NOT NULL,
    u_combined REAL NOT NULL,
    coverage_inflation_factor REAL NOT NULL DEFAULT 1.0 CHECK(coverage_inflation_factor >= 1.0),
    expanded_uncertainty REAL NOT NULL,
    -- Batch mode fields (nullable for single-part)
    slot_assignment_confidence REAL,
    cluster_count INTEGER,
    cross_slot_contamination REAL
);

-- Batch mode tables (Phase 2)

CREATE TABLE IF NOT EXISTS batch_plate_layout (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    plate_dimensions TEXT,  -- JSON
    plate_material TEXT,
    slot_count INTEGER CHECK(slot_count BETWEEN 2 AND 4),
    allowed_part_id TEXT REFERENCES part(id),
    fiducial_definitions TEXT,  -- JSON
    slot_definitions TEXT,  -- JSON
    min_inter_slot_spacing_mm REAL,
    plate_photo_path TEXT,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT CHECK(status IN ('draft', 'active', 'retired')) DEFAULT 'draft'
);

CREATE TABLE IF NOT EXISTS batch_inspection (
    id TEXT PRIMARY KEY,
    plate_layout_id TEXT NOT NULL REFERENCES batch_plate_layout(id),
    recipe_id TEXT NOT NULL REFERENCES inspection_recipe(id),
    receiving_context_id TEXT REFERENCES receiving_context(id),
    operator TEXT,
    scanner_asset_id TEXT,
    scan_count INTEGER,
    plate_localization_rmse REAL,
    plate_localization_method TEXT CHECK(plate_localization_method IN ('fiducials', 'fixture_geometry')),
    slots_occupied INTEGER,
    slots_passed INTEGER DEFAULT 0,
    slots_failed INTEGER DEFAULT 0,
    slots_action_required INTEGER DEFAULT 0,
    batch_disposition TEXT CHECK(batch_disposition IN ('all_passed', 'mixed', 'all_failed', 'incomplete')),
    environment_snapshot_id TEXT REFERENCES environment_snapshot(id),
    calibration_run_id TEXT REFERENCES calibration_run(id),
    notes TEXT,
    report_pdf_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS batch_slot (
    id TEXT PRIMARY KEY,
    batch_inspection_id TEXT NOT NULL REFERENCES batch_inspection(id),
    slot_id_on_plate TEXT NOT NULL,
    slot_pose TEXT,  -- JSON
    serial_number TEXT,
    occupied BOOLEAN DEFAULT 1,
    inspection_id TEXT REFERENCES inspection(id),
    slot_assignment_confidence REAL,
    cluster_count INTEGER,
    cross_slot_contamination REAL,
    slot_status TEXT CHECK(slot_status IN (
        'clean', 'assignment_uncertain', 'contamination_flagged', 'multi_cluster',
        'occupancy_mismatch', 'sparse', 'empty'
    )) DEFAULT 'clean',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
