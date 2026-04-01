"""RIQA CLI entry point.

Commands:
  riqa info         — Show system info
  riqa init-db      — Initialize SQLite database
  riqa calibrate    — Record a calibration validation run
  riqa inspect      — Run Phase 0 inspection pipeline
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
import yaml


@click.group()
@click.version_option(version="0.0.1")
def main():
    """RIQA — Risk-limited receiving inspection QA system."""
    pass


@main.command()
def info():
    """Show system info and configuration status."""
    click.echo("RIQA v0.0.1")
    click.echo("Status: Phase 0 — Feasibility kill test")


@main.command("init-db")
@click.option("--path", default=None, help="Database file path (default: from settings.yaml)")
def init_db(path):
    """Initialize the SQLite database."""
    from riqa.data.db import RiqaDatabase

    if path is None:
        settings = _load_settings()
        path = settings["database"]["path"]

    db = RiqaDatabase(path)
    db.initialize()
    click.echo(f"Database initialized: {path}")
    db.close()


@main.command()
@click.option("--artifact-id", required=True, help="Calibration artifact identifier")
@click.option("--certified-value", required=True, type=float, help="Certified dimension (mm)")
@click.option("--cert-uncertainty", required=True, type=float, help="Certified uncertainty (mm)")
@click.option("--measured-value", required=True, type=float, help="Scanner measurement (mm)")
@click.option("--operator", required=True, help="Operator name")
@click.option("--db-path", default=None, help="Database file path")
def calibrate(artifact_id, certified_value, cert_uncertainty, measured_value, operator, db_path):
    """Record a calibration validation run."""
    from riqa.data.db import RiqaDatabase
    from riqa.scanner.calibration import record_calibration

    if db_path is None:
        settings = _load_settings()
        db_path = settings["database"]["path"]

    db = RiqaDatabase(db_path)
    db.initialize()
    try:
        cal_id, passed = record_calibration(
            db, artifact_id, certified_value, cert_uncertainty, measured_value, operator,
        )
        status = "PASS" if passed else "FAIL"
        error = abs(measured_value - certified_value)
        click.echo(f"Calibration {status}: error={error:.4f}mm, threshold={2*cert_uncertainty:.4f}mm")
        click.echo(f"Calibration run ID: {cal_id}")
    finally:
        db.close()


@main.command()
@click.argument("ply_files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--step", required=True, type=click.Path(exists=True), help="STEP file path")
@click.option("--part-number", required=True, help="Part number")
@click.option("--features-yaml", required=True, type=click.Path(exists=True), help="Feature definitions YAML")
@click.option("--operator", required=True, help="Operator name")
@click.option("--ambient-temp-c", default=20.0, type=float, help="Ambient temperature (°C)")
@click.option("--material-type", default="machined_metal", help="Part material type")
@click.option("--part-revision", default="A", help="Part revision")
@click.option("--db-path", default=None, help="Database file path")
@click.option("--scanner-profile", default="creality_ferret_se", help="Scanner profile name")
def inspect(ply_files, step, part_number, features_yaml, operator, ambient_temp_c,
            material_type, part_revision, db_path, scanner_profile):
    """Run Phase 0 inspection pipeline.

    Accepts PLY scan files and a STEP CAD model. Runs the full pipeline:
    preprocess → align → filter → fuse → measure → uncertainty → confidence → decision.

    Phase 0: All features are Class B. Disposition is hold_for_review or fail_by_scan.
    """
    import numpy as np

    from riqa.cad.importer import load_step
    from riqa.core.alignment import align, classify_alignment
    from riqa.core.confidence import ConfidenceEvidence, evaluate_confidence
    from riqa.core.decision import apply_bias_correction, render_verdict
    from riqa.core.fusion import fuse_scans
    from riqa.core.measurement import (
        compute_effective_sample_size,
        measure_diameter,
        measure_distance,
        measure_envelope,
        measure_flatness,
    )
    from riqa.core.outlier import cad_proximity_filter
    from riqa.core.uncertainty import (
        combine_uncertainty,
        compute_u_align,
        compute_u_bias_est_phase0,
        compute_u_cal,
        compute_u_fit,
        compute_u_ref_phase0,
        compute_u_repeat_phase0,
        compute_u_reprod_phase0,
        compute_u_temp,
    )
    from riqa.data import db as dbmod
    from riqa.data.db import RiqaDatabase
    from riqa.recipe.manager import create_phase0_recipe
    from riqa.scanner.calibration import check_calibration_valid
    from riqa.scanner.import_ply import load_ply, validate_scan
    from riqa.scanner.preprocessing import preprocess_scan
    from riqa.scanner.profiles import get_thresholds_for_part_type, load_profile

    # --- Setup ---
    if db_path is None:
        settings = _load_settings()
        db_path = settings["database"]["path"]

    db = RiqaDatabase(db_path)
    db.initialize()
    profile = load_profile(scanner_profile)
    thresholds = get_thresholds_for_part_type(profile, material_type)

    # Load features YAML
    with open(features_yaml) as f:
        features_def = yaml.safe_load(f)
    features = features_def["features"]

    # Validate feature types
    for feat in features:
        if feat["feature_type"] not in dbmod.VALID_FEATURE_TYPES:
            click.echo(f"ERROR: Invalid feature type {feat['feature_type']!r}", err=True)
            sys.exit(1)

    try:
        # --- Step 1: Create Part record ---
        part_id = dbmod.insert_part(
            db, part_number=part_number, revision=part_revision,
            material_type=material_type,
        )

        # --- Step 2: Create Phase 0 recipe (all features Class B) ---
        recipe_id, feature_ids = create_phase0_recipe(db, part_id, features)

        # --- Step 3: Check calibration ---
        calibration_valid, cal_run_id = check_calibration_valid(db)
        if not calibration_valid:
            click.echo("WARNING: Calibration is expired or missing. Results will be BLOCKED.", err=True)

        # --- Step 4: Create inspection record ---
        env_id = dbmod.insert_environment_snapshot(
            db, ambient_temp_c=ambient_temp_c,
        )

        inspection_id = dbmod.insert_inspection(
            db, part_id=part_id, recipe_id=recipe_id,
            operator=operator,
            scan_count=len(ply_files),
            calibration_run_id=cal_run_id,
            environment_snapshot_id=env_id,
        )

        # --- Step 5: Load and preprocess scans ---
        click.echo(f"Loading {len(ply_files)} scan(s)...")
        scans = []
        for ply in ply_files:
            pcd = load_ply(ply)
            validation = validate_scan(pcd)
            if not validation.is_valid:
                click.echo(f"  REJECTED {ply}: {validation.rejection_reason}", err=True)
                continue
            click.echo(f"  Loaded {ply}: {validation.point_count} points")
            scans.append(pcd)

        if not scans:
            click.echo("ERROR: No valid scans to process.", err=True)
            dbmod.update_inspection_disposition(db, inspection_id, "incomplete")
            sys.exit(1)

        # --- Step 6: Load CAD ---
        click.echo(f"Loading CAD model: {step}")
        cad_model = load_step(step)
        click.echo(f"  CAD loaded: {len(cad_model.vertices)} vertices, hash={cad_model.file_hash_sha256[:12]}...")

        # --- Step 7: Preprocess scans ---
        click.echo("Preprocessing scans...")
        preprocessed = []
        for i, scan in enumerate(scans):
            pp = preprocess_scan(
                scan, thresholds, profile,
                cad_bbox_min=cad_model.bbox_min,
                cad_bbox_max=cad_model.bbox_max,
            )
            click.echo(f"  Scan {i+1}: {pp.original_point_count} -> {pp.filtered_point_count} pts "
                       f"({pp.points_removed_pct:.1f}% removed)")
            preprocessed.append(pp)

        # --- Step 8: Align scans to CAD ---
        click.echo("Aligning scans to CAD...")
        import open3d as o3d
        cad_pcd = o3d.geometry.PointCloud()
        cad_pcd.points = o3d.utility.Vector3dVector(cad_model.surface_points)
        cad_pcd.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=2.0, max_nn=30))

        aligned_scans = []
        alignment_band = "pass"
        alignment_reason = None
        all_perturbation_values = []

        # Load alignment params from settings
        settings = _load_settings()
        align_cfg = settings.get("alignment", {})

        for i, pp in enumerate(preprocessed):
            result = align(
                pp.pcd_downsampled, cad_pcd,
                max_iterations=align_cfg.get("icp_max_iterations", 50),
                convergence_threshold=align_cfg.get("icp_convergence_threshold", 1e-7),
                hard_block_fitness=align_cfg.get("hard_block_fitness", 0.70),
                hard_block_rmse=align_cfg.get("hard_block_rmse_mm", 0.15),
                unconstrained_fitness_threshold=align_cfg.get("default_recipe_fitness", 0.85),
            )
            click.echo(f"  Scan {i+1}: fitness={result.fitness:.3f}, RMSE={result.rmse:.4f}mm, "
                       f"band={result.alignment_band}")

            # Worst band wins (hard_block > soft_degrade > pass)
            if result.alignment_band == "hard_block":
                alignment_band = "hard_block"
                alignment_reason = result.reason_code
            elif result.alignment_band == "soft_degrade" and alignment_band != "hard_block":
                alignment_band = "soft_degrade"
                alignment_reason = result.reason_code

            all_perturbation_values.extend(result.perturbation_values)

            if result.aligned_pcd is not None:
                aligned_scans.append(result.aligned_pcd)

        # Update inspection with alignment metrics
        if preprocessed:
            last_result = result
            dbmod.update_inspection_alignment(
                db, inspection_id,
                fitness=last_result.fitness,
                rmse=last_result.rmse,
                stable=last_result.stability_passed,
                mode="unconstrained",  # PHASE0_SIMPLIFICATION
            )

        # --- Step 9: Hard-block check ---
        if alignment_band == "hard_block":
            click.echo("ALIGNMENT HARD-BLOCKED. Persisting blocked results for all features.")
            for feat, fid in zip(features, feature_ids):
                dbmod.insert_inspection_result(
                    db, inspection_id=inspection_id, feature_id=fid,
                    raw_value=None, corrected_value=None,
                    expanded_uncertainty=None, deviation=None,
                    status="blocked",
                    reason_code="REVIEW_ONLY_ALIGNMENT_DEGRADED",
                    recommended_action="Alignment failed — rescan or check part orientation.",
                )
            dbmod.update_inspection_disposition(db, inspection_id, "incomplete")
            _print_results_table(features, ["blocked"] * len(features))
            return

        # --- Step 10: Post-alignment CAD-proximity filter ---
        click.echo("Applying CAD-proximity filter...")
        import trimesh
        cad_mesh = o3d.geometry.TriangleMesh()
        cad_mesh.vertices = o3d.utility.Vector3dVector(cad_model.vertices)
        cad_mesh.triangles = o3d.utility.Vector3iVector(cad_model.faces)

        filtered_scans = []
        for scan in aligned_scans:
            filtered = cad_proximity_filter(scan, cad_mesh, max_distance_mm=thresholds.cad_proximity_mm)
            filtered_scans.append(filtered)

        # --- Step 11: Fuse aligned scans ---
        click.echo("Fusing scans...")
        fusion_result = fuse_scans(filtered_scans, voxel_size_mm=profile.fusion_voxel_size_mm)
        click.echo(f"  Fused: {fusion_result.fused_point_count} points from {fusion_result.scan_count} scans "
                   f"(consensus >= {fusion_result.consensus_threshold})")

        # --- Step 12: Measure features ---
        click.echo("Measuring features...")
        results_statuses = []

        # Pre-compute shared values for uncertainty
        delta_t = abs(ambient_temp_c - 20.0)
        cte = 23.6e-6  # aluminum 6061-T6 default, overridable in future
        part_size = float(np.max(cad_model.bbox_size_mm))

        for feat, fid in zip(features, feature_ids):
            click.echo(f"  Feature: {feat['name']} ({feat['feature_type']})")

            try:
                # Extract local points
                from riqa.cad.feature_region import FeatureSearchRegion, extract_local_points
                region = FeatureSearchRegion(
                    feature_id=fid,
                    feature_type=feat["feature_type"],
                    center=np.array(feat.get("center", [0, 0, 0]), dtype=float),
                    bbox_min=np.array(feat["bbox_min"], dtype=float),
                    bbox_max=np.array(feat["bbox_max"], dtype=float),
                    margin_mm=feat.get("margin_mm", 5.0),
                    axis=np.array(feat["axis"], dtype=float) if "axis" in feat else None,
                )
                local_points, n_local = extract_local_points(fusion_result.fused_pcd, region)

                if n_local < 10:
                    click.echo(f"    Too few local points ({n_local}), marking as manual_required")
                    dbmod.insert_inspection_result(
                        db, inspection_id=inspection_id, feature_id=fid,
                        raw_value=None, corrected_value=None,
                        expanded_uncertainty=None, deviation=None,
                        status="manual_required",
                        reason_code="MANUAL_FEATURE_TOO_SMALL",
                        recommended_action="Not enough points in feature region.",
                    )
                    results_statuses.append("manual_required")
                    continue

                # Measure
                if feat["feature_type"] == "diameter":
                    meas = measure_diameter(local_points, axis=region.axis)
                elif feat["feature_type"] == "distance":
                    # Distance needs two endpoints — for Phase 0, split local points by centroid
                    mid = local_points.mean(axis=0)
                    mask = local_points[:, 0] < mid[0]
                    if mask.sum() < 3 or (~mask).sum() < 3:
                        raise ValueError("Cannot split points for distance measurement")
                    meas = measure_distance(local_points[mask], local_points[~mask])
                elif feat["feature_type"] == "flatness":
                    meas = measure_flatness(local_points)
                elif feat["feature_type"] in ("bbox_length", "bbox_width", "bbox_height"):
                    meas = measure_envelope(local_points)
                else:
                    raise ValueError(f"Unsupported feature type: {feat['feature_type']}")

                click.echo(f"    Raw value: {meas.measured_value:.4f}mm, "
                          f"fit residual: {meas.fit_residual:.5f}, n_eff: {meas.n_eff}")

                # --- Uncertainty computation (all 8 components) ---
                # Phase 0 fallbacks where MSA data unavailable
                u_fit = compute_u_fit(meas.fit_residual, meas.n_eff, c_fit=1.0)  # PHASE0_SIMPLIFICATION

                # Per-scan values for repeat/bias estimation
                per_scan_values = _estimate_per_scan_values(
                    aligned_scans, region, feat["feature_type"],
                )
                if len(per_scan_values) >= 2:
                    u_repeat = compute_u_repeat_phase0(per_scan_values)
                    u_bias_est = compute_u_bias_est_phase0(per_scan_values, feat["nominal"])
                else:
                    # Fallback: use fit residual as conservative estimate
                    u_repeat = meas.fit_residual
                    u_bias_est = meas.fit_residual / 2.0

                u_reprod = compute_u_reprod_phase0(profile.accuracy_class_mm)
                u_align = compute_u_align(all_perturbation_values) if all_perturbation_values else 0.01
                u_cal_val = 0.005  # Phase 0 default
                latest_cal = db.get_latest_calibration_run()
                if latest_cal:
                    u_cal_val = compute_u_cal(latest_cal["error"], latest_cal["certified_uncertainty"])
                u_ref = compute_u_ref_phase0()
                u_temp = compute_u_temp(cte, part_size, delta_t)

                # Estimate local coverage
                feature_area = np.prod(np.array(feat["bbox_max"]) - np.array(feat["bbox_min"]))
                local_coverage = min(1.0, n_local / max(1, feature_area * 4))  # rough estimate

                uc = combine_uncertainty(
                    u_fit, u_repeat, u_reprod, u_align, u_cal_val, u_ref, u_temp, u_bias_est,
                    coverage_fraction=max(0.5, local_coverage),
                )

                # Bias correction (Phase 0: bias = mean scan value - nominal)
                bias = meas.measured_value - feat["nominal"]  # crude Phase 0 estimate
                # In Phase 0, we don't have MSA bias data, so we just use the raw value
                corrected_value = meas.measured_value  # PHASE0_SIMPLIFICATION: no bias correction applied

                # --- Confidence evaluation ---
                evidence = ConfidenceEvidence(
                    local_density=n_local / max(1.0, feature_area),
                    local_coverage=local_coverage,
                    incidence_angle_median=45.0,  # PHASE0_SIMPLIFICATION: estimated
                    fit_residual=meas.fit_residual,
                    inter_scan_stddev=u_repeat,
                    boundary_proximity=5.0,  # PHASE0_SIMPLIFICATION: estimated
                    alignment_sensitivity=u_align / max(0.001, feat["tol_plus"]),
                )

                confidence = evaluate_confidence(
                    evidence,
                    feature_class="B",  # Phase 0: all Class B
                )

                # --- Decision ---
                verdict = render_verdict(
                    corrected_value=corrected_value,
                    expanded_uncertainty=uc.u_adjusted,
                    nominal=feat["nominal"],
                    tol_plus=feat["tol_plus"],
                    tol_minus=feat["tol_minus"],
                    guard_band_method="uncertainty_based",
                    guard_band_percent=10.0,
                    feature_class="B",  # Phase 0: all Class B
                    confidence_result=confidence,
                    calibration_valid=calibration_valid,
                    recipe_match=True,  # Phase 0: always true
                    alignment_band=alignment_band,
                )

                click.echo(f"    Verdict: {verdict.status} ({verdict.reason_code})")
                results_statuses.append(verdict.status)

                # --- Persist result ---
                deviation = corrected_value - feat["nominal"]
                result_id = dbmod.insert_inspection_result(
                    db, inspection_id=inspection_id, feature_id=fid,
                    raw_value=meas.measured_value,
                    corrected_value=corrected_value,
                    expanded_uncertainty=uc.u_adjusted,
                    deviation=deviation,
                    status=verdict.status,
                    reason_code=verdict.reason_code,
                    recommended_action=verdict.recommended_action,
                )

                # --- Persist evidence ---
                dbmod.insert_measurement_evidence(
                    db, result_id=result_id,
                    local_coverage=local_coverage,
                    local_density=evidence.local_density,
                    fit_residual=meas.fit_residual,
                    inlier_count=meas.n_inliers,
                    effective_sample_size=meas.n_eff,
                    u_fit=u_fit,
                    u_repeat=u_repeat,
                    u_reprod=u_reprod,
                    u_align=u_align,
                    u_cal=u_cal_val,
                    u_ref=u_ref,
                    u_temp=u_temp,
                    u_bias_est=u_bias_est,
                    u_combined=uc.u_combined,
                    expanded_uncertainty=uc.u_adjusted,
                    coverage_inflation_factor=uc.coverage_inflation,
                    incidence_angle_median=evidence.incidence_angle_median,
                    inter_scan_stddev=evidence.inter_scan_stddev,
                    alignment_sensitivity=evidence.alignment_sensitivity,
                    boundary_proximity=evidence.boundary_proximity,
                )

            except Exception as e:
                click.echo(f"    ERROR: {e}", err=True)
                dbmod.insert_inspection_result(
                    db, inspection_id=inspection_id, feature_id=fid,
                    raw_value=None, corrected_value=None,
                    expanded_uncertainty=None, deviation=None,
                    status="blocked",
                    reason_code="BLOCKED_RECIPE_MISMATCH",
                    recommended_action=f"Measurement failed: {e}",
                )
                results_statuses.append("blocked")

        # --- Step 13: Compute disposition ---
        # Phase 0: never pass_scan_only. Either hold_for_review or fail_by_scan.
        has_fail = any(s in ("fail_full", "fail_marginal") for s in results_statuses)
        if has_fail:
            disposition = "fail_by_scan"
        else:
            disposition = "hold_for_review"

        dbmod.update_inspection_disposition(db, inspection_id, disposition)

        # --- Print results ---
        click.echo()
        click.echo(f"{'='*60}")
        click.echo(f"INSPECTION COMPLETE — Disposition: {disposition.upper()}")
        click.echo(f"{'='*60}")
        _print_results_table(features, results_statuses)

    finally:
        db.close()


def _estimate_per_scan_values(aligned_scans, region, feature_type):
    """Get per-scan measurement values for uncertainty estimation."""
    import numpy as np
    from riqa.core.measurement import measure_diameter, measure_envelope, measure_flatness

    values = []
    for scan in aligned_scans:
        try:
            from riqa.cad.feature_region import extract_local_points
            pts, n = extract_local_points(scan, region)
            if n < 10:
                continue
            if feature_type == "diameter":
                m = measure_diameter(pts, axis=region.axis)
            elif feature_type == "flatness":
                m = measure_flatness(pts)
            elif feature_type in ("bbox_length", "bbox_width", "bbox_height"):
                m = measure_envelope(pts)
            else:
                # For distance etc., just use centroid Z as proxy
                values.append(float(np.mean(pts[:, 2])))
                continue
            values.append(m.measured_value)
        except Exception:
            continue
    return values


def _print_results_table(features, statuses):
    """Print a simple results table to stdout."""
    click.echo(f"{'Feature':<30} {'Type':<15} {'Status':<20}")
    click.echo(f"{'-'*30} {'-'*15} {'-'*20}")
    for feat, status in zip(features, statuses):
        click.echo(f"{feat['name']:<30} {feat['feature_type']:<15} {status:<20}")


def _load_settings():
    """Load global settings from YAML."""
    settings_path = Path(__file__).parent / "config" / "settings.yaml"
    with open(settings_path) as f:
        return yaml.safe_load(f)


if __name__ == "__main__":
    main()
