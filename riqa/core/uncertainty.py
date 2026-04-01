"""NIST GUM uncertainty propagation.

Eight named components:
  u_fit, u_repeat, u_reprod, u_align, u_cal, u_ref, u_temp, u_bias_est

Combined: u_c = sqrt(sum of squares)  [RSS, NOT linear sum]
Expanded: U = k * u_c (k=2 default, 95% CI)
Coverage-adjusted: U_adj = f_cov * U

See spec Section 7.5.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class UncertaintyComponents:
    """All 8 GUM uncertainty components plus combined and expanded values."""
    u_fit: float
    u_repeat: float
    u_reprod: float
    u_align: float
    u_cal: float
    u_ref: float
    u_temp: float
    u_bias_est: float
    u_combined: float           # RSS of all 8
    expanded_uncertainty: float  # k * u_combined
    coverage_factor_k: float    # typically 2.0 (95% CI)
    coverage_inflation: float   # f_cov (>= 1.0)
    u_adjusted: float           # f_cov * expanded_uncertainty


def compute_u_fit(
    fit_residual: float,
    n_eff: int,
    c_fit: float = 1.0,
) -> float:
    """Compute fit uncertainty component.

    u_fit = c_fit * (fit_residual / sqrt(n_eff))

    Args:
        fit_residual: RMSE of geometric primitive fit to local scan points.
        n_eff: Effective sample size (spatially decimated, NOT raw inlier count).
        c_fit: Empirical correction factor from MSA. Must be >= 1.0.
               Phase 0: c_fit = 1.0 (no MSA calibration yet).  # PHASE0_SIMPLIFICATION
    """
    if c_fit < 1.0:
        raise ValueError(f"c_fit={c_fit} is < 1.0. c_fit must inflate, never deflate.")
    if n_eff < 1:
        raise ValueError(f"n_eff={n_eff} must be >= 1.")
    return c_fit * (fit_residual / math.sqrt(n_eff))


def compute_u_align(perturbation_values: list[float]) -> float:
    """Compute alignment uncertainty from perturbation test results.

    u_align = half-range of measurement variation across ±0.2°/±0.2mm perturbation set.
    """
    if not perturbation_values:
        raise ValueError("perturbation_values must be non-empty.")
    return (max(perturbation_values) - min(perturbation_values)) / 2.0


def compute_u_cal(
    calibration_error: float,
    calibration_uncertainty: float,
) -> float:
    """Compute calibration uncertainty from most recent calibration run.

    Uses the calibration artifact's certified uncertainty as the base,
    combined with the observed error as an indication of scanner drift.
    """
    return math.sqrt(calibration_error ** 2 + calibration_uncertainty ** 2)


def compute_u_temp(
    cte_per_c: float,
    part_size_mm: float,
    delta_t_from_20c: float,
) -> float:
    """Compute thermal uncertainty.

    u_temp = cte * part_size * |delta_T_from_20C|

    Args:
        cte_per_c: Coefficient of thermal expansion in mm/mm/°C (e.g., 23.6e-6 for 6061-T6).
        part_size_mm: Characteristic part dimension in mm.
        delta_t_from_20c: Absolute temperature deviation from 20°C.
    """
    return cte_per_c * part_size_mm * abs(delta_t_from_20c)


def compute_u_repeat_phase0(per_scan_values: list[float]) -> float:
    """Phase 0 fallback: repeatability from scan-to-scan variation.

    u_repeat = std_dev(per_scan_values) (as standard uncertainty)

    # PHASE0_SIMPLIFICATION: In Phase 1+, this comes from MSA study data.
    """
    if len(per_scan_values) < 2:
        raise ValueError("Need at least 2 scan values for repeatability estimate.")
    mean = sum(per_scan_values) / len(per_scan_values)
    variance = sum((v - mean) ** 2 for v in per_scan_values) / (len(per_scan_values) - 1)
    return math.sqrt(variance)


def compute_u_reprod_phase0(scanner_accuracy_mm: float) -> float:
    """Phase 0 fallback: conservative reproducibility estimate.

    # PHASE0_SIMPLIFICATION: Uses scanner accuracy class / 3 as a rough estimate.
    In Phase 1+, this comes from MSA between-operator variation.
    """
    return scanner_accuracy_mm / 3.0


def compute_u_ref_phase0(caliper_uncertainty_mm: float = 0.01) -> float:
    """Phase 0 fallback: reference instrument uncertainty.

    # PHASE0_SIMPLIFICATION: Hardcoded caliper uncertainty.
    In Phase 1+, this comes from the reference instrument calibration certificate.
    """
    return caliper_uncertainty_mm


def compute_u_bias_est_phase0(
    per_scan_values: list[float],
    reference_value: float,
) -> float:
    """Phase 0 fallback: bias estimation uncertainty.

    u_bias_est = SEM of individual scan biases.

    # PHASE0_SIMPLIFICATION: In Phase 1+, comes from MSA study.
    """
    if len(per_scan_values) < 2:
        raise ValueError("Need at least 2 scan values for bias estimation uncertainty.")
    biases = [v - reference_value for v in per_scan_values]
    mean_bias = sum(biases) / len(biases)
    variance = sum((b - mean_bias) ** 2 for b in biases) / (len(biases) - 1)
    return math.sqrt(variance) / math.sqrt(len(biases))


def combine_uncertainty(
    u_fit: float,
    u_repeat: float,
    u_reprod: float,
    u_align: float,
    u_cal: float,
    u_ref: float,
    u_temp: float,
    u_bias_est: float,
    k: float = 2.0,
    coverage_fraction: float = 1.0,
    required_coverage: float = 0.8,
) -> UncertaintyComponents:
    """Combine all 8 uncertainty components per NIST GUM methodology.

    Combination is RSS (root sum of squares), NOT linear sum, NOT max.

    u_c = sqrt(u_fit^2 + u_repeat^2 + ... + u_bias_est^2)
    U   = k * u_c
    f_cov = required_coverage / actual_coverage  (clamped >= 1.0)
    U_adj = f_cov * U

    Args:
        k: Coverage factor (default 2.0 for 95% CI).
        coverage_fraction: Actual local feature coverage (0-1).
        required_coverage: Recipe-defined minimum coverage (default 0.8).

    Raises:
        ValueError: If coverage_fraction < 0.5 (blocked — feature cannot be measured).
    """
    components = [u_fit, u_repeat, u_reprod, u_align, u_cal, u_ref, u_temp, u_bias_est]
    for i, c in enumerate(components):
        if c is None:
            names = ["u_fit", "u_repeat", "u_reprod", "u_align", "u_cal", "u_ref", "u_temp", "u_bias_est"]
            raise ValueError(f"Uncertainty component {names[i]} is None — all 8 must be computed.")

    # RSS combination — the only correct method per NIST GUM
    u_combined = math.sqrt(sum(c ** 2 for c in components))

    # Expanded uncertainty
    expanded = k * u_combined

    # Coverage inflation
    if coverage_fraction < 0.5:
        raise ValueError(
            f"Coverage fraction {coverage_fraction:.2f} is below 0.50 — feature is blocked "
            f"from measurement (RESCAN_NEEDED or MANUAL_GAUGE_REQUIRED)."
        )

    if coverage_fraction >= required_coverage:
        f_cov = 1.0
    else:
        f_cov = required_coverage / coverage_fraction

    # f_cov must never be < 1.0 — it inflates uncertainty, never deflates
    if f_cov < 1.0:
        raise ValueError(f"f_cov={f_cov} < 1.0 — coverage inflation must never deflate uncertainty.")

    u_adjusted = f_cov * expanded

    return UncertaintyComponents(
        u_fit=u_fit,
        u_repeat=u_repeat,
        u_reprod=u_reprod,
        u_align=u_align,
        u_cal=u_cal,
        u_ref=u_ref,
        u_temp=u_temp,
        u_bias_est=u_bias_est,
        u_combined=u_combined,
        expanded_uncertainty=expanded,
        coverage_factor_k=k,
        coverage_inflation=f_cov,
        u_adjusted=u_adjusted,
    )
