"""Validation artifact scanning and accuracy tracking.

See spec Section 9.2.5.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from riqa.data import db as dbmod
from riqa.data.db import RiqaDatabase


def record_calibration(
    db: RiqaDatabase,
    artifact_id: str,
    certified_value: float,
    certified_uncertainty: float,
    measured_value: float,
    operator: str,
    scanner_model: str = "Creality Ferret SE",
) -> tuple[str, bool]:
    """Record a calibration validation run.

    Computes error = |measured - certified|. If error > 2× certified_uncertainty,
    the calibration fails.

    Returns:
        (calibration_run_id, pass_fail)
    """
    cal_id = dbmod.insert_calibration_run(
        db,
        scanner_model=scanner_model,
        scanner_asset_id=None,
        artifact_id=artifact_id,
        artifact_certified_value=certified_value,
        artifact_cert_uncertainty=certified_uncertainty,
        measured_value=measured_value,
        operator=operator,
    )

    # Read back to get computed pass_fail
    cal = dbmod.get_latest_calibration(db, scanner_model)
    return cal_id, cal["pass_fail"]


def check_calibration_valid(
    db: RiqaDatabase,
    scanner_model: str = "Creality Ferret SE",
    validity_hours: int = 8,
) -> tuple[bool, str | None]:
    """Check if calibration is still valid.

    Returns:
        (is_valid, calibration_run_id or None)
    """
    latest = dbmod.get_latest_calibration(db, scanner_model)
    if latest is None:
        return False, None

    # Check pass/fail
    if not latest["pass_fail"]:
        return False, latest["id"]

    # Check age
    cal_time = datetime.fromisoformat(latest["created_at"])
    if cal_time.tzinfo is None:
        cal_time = cal_time.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)

    if now - cal_time > timedelta(hours=validity_hours):
        return False, latest["id"]

    return True, latest["id"]
