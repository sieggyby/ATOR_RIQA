"""Decision engine with uncertainty, guard bands, and reason codes.

Implements the full decision rule table from spec Section 7.7
and reason code taxonomy from Section 8.3.

Decision order:
  1. Class C -> NOT_SCAN_ELIGIBLE
  2. Calibration expired -> BLOCKED_CALIBRATION
  3. Recipe mismatch -> BLOCKED_RECIPE_MISMATCH
  4. Hard-block alignment -> blocked
  5. Confidence escalated -> pass through RESCAN/MANUAL reason
  6. Class B (original or demoted) -> REVIEW_ONLY
  7. [Class A only] Apply guard band, render PASS/FAIL/MARGINAL verdict
"""

from __future__ import annotations

from dataclasses import dataclass

from riqa.core.confidence import ConfidenceResult


@dataclass
class Verdict:
    """Decision engine output for a single feature."""
    status: str              # matches inspection_result.status enum
    reason_code: str         # matches spec Section 8.3 taxonomy
    recommended_action: str | None
    corrected_value: float | None
    expanded_uncertainty: float | None
    guard_band_applied: bool


def apply_bias_correction(measured_value: float, bias: float) -> float:
    """Apply bias correction: corrected = measured - bias.

    Bias is SUBTRACTED from the measured value, not added.
    If the system consistently reads 0.03mm high (bias = +0.03),
    then corrected = measured - 0.03.
    """
    return measured_value - bias


def compute_guard_band_limits(
    nominal: float,
    tol_plus: float,
    tol_minus: float,
    method: str,
    guard_percent: float,
    expanded_uncertainty: float,
) -> tuple[float, float]:
    """Compute guard-banded acceptance limits.

    Returns (guarded_upper, guarded_lower).

    Guard band NARROWS tolerance, never widens. This is the core
    false-accept-prevention mechanism for Class A features.

    Methods:
        simple_percentage: Narrow by G% on each side.
        uncertainty_based: Upper = nominal + tol_plus - U,
                          Lower = nominal + tol_minus + U.
                          (ASME B89.7.3.1 — accept only if value ± U
                          is fully inside tolerance.)
        shared_risk: No narrowing (original limits). Only for noncritical
                     features with written engineering approval.
    """
    upper_limit = nominal + tol_plus
    lower_limit = nominal + tol_minus  # tol_minus is negative

    if method == "simple_percentage":
        tolerance_range = tol_plus - tol_minus  # total range
        guard = tolerance_range * (guard_percent / 100.0) / 2.0
        guarded_upper = upper_limit - guard
        guarded_lower = lower_limit + guard

    elif method == "uncertainty_based":
        # Accept only if measured value ± U is fully inside tolerance.
        # Equivalent to narrowing each limit by U.
        guarded_upper = upper_limit - expanded_uncertainty
        guarded_lower = lower_limit + expanded_uncertainty

    elif method == "shared_risk":
        # No guard band — original limits. Requires written approval.
        guarded_upper = upper_limit
        guarded_lower = lower_limit

    else:
        raise ValueError(f"Unknown guard band method: {method!r}")

    return guarded_upper, guarded_lower


def render_verdict(
    corrected_value: float | None,
    expanded_uncertainty: float | None,
    nominal: float,
    tol_plus: float,
    tol_minus: float,
    guard_band_method: str,
    guard_band_percent: float,
    feature_class: str,
    confidence_result: ConfidenceResult,
    calibration_valid: bool,
    recipe_match: bool,
    alignment_band: str,
) -> Verdict:
    """Full decision engine per spec Sections 7.7 and 8.2-8.3.

    Checks are applied in strict order. Each check either produces a
    terminal verdict or passes through to the next check. This ordering
    ensures that safety gates (calibration, alignment, eligibility) are
    always evaluated before any pass/fail logic.

    Args:
        corrected_value: Bias-corrected measured value (None if measurement blocked).
        expanded_uncertainty: U_adj (k=2, coverage-adjusted). None if blocked.
        nominal: Feature nominal dimension.
        tol_plus: Upper tolerance (positive).
        tol_minus: Lower tolerance (negative).
        guard_band_method: 'simple_percentage', 'uncertainty_based', or 'shared_risk'.
        guard_band_percent: G% for simple_percentage method.
        feature_class: Original class from recipe ('A', 'B', 'C').
        confidence_result: Output of evaluate_confidence().
        calibration_valid: Whether calibration is current.
        recipe_match: Whether scanner/fixture/version match the recipe.
        alignment_band: 'pass', 'soft_degrade', or 'hard_block'.
    """

    # --- Check 1: Class C — not scan-eligible ---
    if feature_class == "C":
        return Verdict(
            status="manual_required",
            reason_code="MANUAL_NOT_SCAN_ELIGIBLE",
            recommended_action="Measure with appropriate manual gauge per drawing callout.",
            corrected_value=None,
            expanded_uncertainty=None,
            guard_band_applied=False,
        )

    # --- Check 2: Calibration expired ---
    if not calibration_valid:
        return Verdict(
            status="blocked",
            reason_code="BLOCKED_CALIBRATION",
            recommended_action="Perform calibration validation scan before inspecting.",
            corrected_value=None,
            expanded_uncertainty=None,
            guard_band_applied=False,
        )

    # --- Check 3: Recipe mismatch ---
    if not recipe_match:
        return Verdict(
            status="blocked",
            reason_code="BLOCKED_RECIPE_MISMATCH",
            recommended_action="Verify scanner, fixture, and software match the recipe.",
            corrected_value=None,
            expanded_uncertainty=None,
            guard_band_applied=False,
        )

    # --- Check 4: Alignment hard-block ---
    if alignment_band == "hard_block":
        return Verdict(
            status="blocked",
            reason_code="REVIEW_ONLY_ALIGNMENT_DEGRADED",
            recommended_action="Alignment failed — rescan or check part orientation.",
            corrected_value=None,
            expanded_uncertainty=None,
            guard_band_applied=False,
        )

    # --- Check 4b: Soft-degrade alignment → demote to review-only ---
    # This MUST come before confidence/Class A logic. A Class A feature
    # under degraded alignment cannot receive a PASS verdict.
    if alignment_band == "soft_degrade":
        return Verdict(
            status="review_only",
            reason_code="REVIEW_ONLY_ALIGNMENT_DEGRADED",
            recommended_action="Alignment degraded — review measurement and uncertainty. Human disposition required.",
            corrected_value=corrected_value,
            expanded_uncertainty=expanded_uncertainty,
            guard_band_applied=False,
        )

    # --- Check 5: Confidence escalation (RESCAN / MANUAL) ---
    # Per Section 8.2 precedence: confidence evaluation happens first.
    # If confidence escalated the feature, the decision engine passes
    # through the escalation reason — it does NOT override it.
    if confidence_result.escalation_target is not None:
        if confidence_result.escalation_target == "rescan":
            return Verdict(
                status="rescan_needed",
                reason_code=confidence_result.reason_code,
                recommended_action="Rescan with improved scan path for this feature region.",
                corrected_value=corrected_value,
                expanded_uncertainty=expanded_uncertainty,
                guard_band_applied=False,
            )
        else:  # manual
            return Verdict(
                status="manual_required",
                reason_code=confidence_result.reason_code,
                recommended_action="Measure with manual gauge — scanner cannot resolve this feature.",
                corrected_value=corrected_value,
                expanded_uncertainty=expanded_uncertainty,
                guard_band_applied=False,
            )

    # --- Check 6: Class B (original or demoted from A) → REVIEW_ONLY ---
    effective_class = confidence_result.effective_class
    if effective_class == "B":
        reason = confidence_result.reason_code
        if reason is None:
            reason = "REVIEW_ONLY_BEST_FIT"
        return Verdict(
            status="review_only",
            reason_code=reason,
            recommended_action="Review measurement and uncertainty. Human disposition required.",
            corrected_value=corrected_value,
            expanded_uncertainty=expanded_uncertainty,
            guard_band_applied=False,
        )

    # --- Check 7: Class A — apply guard band and render pass/fail/marginal ---
    if effective_class != "A":
        raise ValueError(
            f"Expected Class A at this point, got {effective_class!r}. "
            f"All non-A paths should have been handled above."
        )
    if corrected_value is None:
        raise ValueError("corrected_value cannot be None for Class A verdict")
    if expanded_uncertainty is None:
        raise ValueError("expanded_uncertainty cannot be None for Class A verdict")

    guarded_upper, guarded_lower = compute_guard_band_limits(
        nominal, tol_plus, tol_minus,
        guard_band_method, guard_band_percent, expanded_uncertainty,
    )

    upper_limit = nominal + tol_plus
    lower_limit = nominal + tol_minus

    # Value ± U bounds
    value_upper = corrected_value + expanded_uncertainty
    value_lower = corrected_value - expanded_uncertainty

    # Deviation from nominal
    deviation = corrected_value - nominal

    # --- Decision rules (spec Section 7.7) ---

    # PASS: value ± U fully inside guard-banded tolerance
    if value_lower >= guarded_lower and value_upper <= guarded_upper:
        return Verdict(
            status="pass",
            reason_code="PASS_WITH_GUARD_BAND" if guard_band_method != "shared_risk" else "PASS_FULL_CONFIDENCE",
            recommended_action=None,
            corrected_value=corrected_value,
            expanded_uncertainty=expanded_uncertainty,
            guard_band_applied=(guard_band_method != "shared_risk"),
        )

    # Is the corrected value itself inside or outside the original tolerance?
    value_in_spec = lower_limit <= corrected_value <= upper_limit

    # MARGINAL_INSIDE: value in-spec but uncertainty extends past guard-banded
    # OR original tolerance limit. This catches two cases:
    #   1. Value between guard-banded and original limit (guard band ambiguity zone)
    #   2. Value in-spec but U extends past original limit
    # Both MUST route to manual verification, NEVER resolve to PASS.
    if value_in_spec and (
        value_upper > guarded_upper or value_lower < guarded_lower
    ):
        return Verdict(
            status="marginal_inside",
            reason_code="MARGINAL_INSIDE",
            recommended_action="Value in-spec but uncertainty extends past guard-banded limit. Verify with manual gauge.",
            corrected_value=corrected_value,
            expanded_uncertainty=expanded_uncertainty,
            guard_band_applied=True,
        )

    # Value is outside tolerance. Determine if uncertainty overlaps the limit.
    if not value_in_spec:
        # Check if uncertainty band overlaps the tolerance limit
        uncertainty_overlaps = (value_lower < upper_limit and value_upper > upper_limit) or \
                               (value_upper > lower_limit and value_lower < lower_limit)

        if uncertainty_overlaps:
            # MARGINAL_OUTSIDE: value out-of-spec but uncertainty overlaps limit.
            # Cannot auto-reject — routes to manual verification.
            return Verdict(
                status="marginal_outside",
                reason_code="MARGINAL_OUTSIDE",
                recommended_action="Value out-of-spec but uncertainty overlaps limit. Verify with manual gauge.",
                corrected_value=corrected_value,
                expanded_uncertainty=expanded_uncertainty,
                guard_band_applied=True,
            )

        # Value ± U entirely outside tolerance. Clear reject.
        # Determine margin: FAIL_MARGINAL if deviation < 2*U beyond limit
        if corrected_value > upper_limit:
            beyond = corrected_value - upper_limit
        else:
            beyond = lower_limit - corrected_value

        if beyond < 2 * expanded_uncertainty:
            return Verdict(
                status="fail_marginal",
                reason_code="FAIL_MARGINAL",
                recommended_action="Clear reject with small margin. Flagged for trend analysis.",
                corrected_value=corrected_value,
                expanded_uncertainty=expanded_uncertainty,
                guard_band_applied=True,
            )

        return Verdict(
            status="fail_full",
            reason_code="FAIL_FULL_CONFIDENCE",
            recommended_action="Clear reject with high confidence.",
            corrected_value=corrected_value,
            expanded_uncertainty=expanded_uncertainty,
            guard_band_applied=True,
        )

    # This path is unreachable: if value_in_spec=True we handled it above
    # (either PASS from guard band check, or MARGINAL_INSIDE). If value_in_spec=False
    # we handled it in the not-value_in_spec block. Raise to catch logic errors.
    raise RuntimeError(
        f"Unreachable decision state: corrected_value={corrected_value}, "
        f"expanded_uncertainty={expanded_uncertainty}, "
        f"guarded_upper={guarded_upper}, guarded_lower={guarded_lower}"
    )
