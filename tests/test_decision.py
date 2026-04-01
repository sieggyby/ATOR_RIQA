"""Tests for uncertainty model, confidence evaluation, and decision engine.

This is the highest-risk test file in the project. Every test here
validates a safety-critical invariant from the spec.
"""

import math

import pytest

from riqa.core.uncertainty import (
    UncertaintyComponents,
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
from riqa.core.confidence import (
    ConfidenceEvidence,
    ConfidenceResult,
    ConfidenceThresholds,
    evaluate_confidence,
)
from riqa.core.decision import (
    Verdict,
    apply_bias_correction,
    compute_guard_band_limits,
    render_verdict,
)


# ========================================================================
# Uncertainty Model Tests
# ========================================================================

class TestUFit:
    def test_basic(self):
        assert compute_u_fit(0.01, 100) == pytest.approx(0.001)

    def test_with_correction_factor(self):
        assert compute_u_fit(0.01, 100, c_fit=2.0) == pytest.approx(0.002)

    def test_c_fit_below_one_raises(self):
        with pytest.raises(ValueError, match="c_fit"):
            compute_u_fit(0.01, 100, c_fit=0.5)

    def test_n_eff_zero_raises(self):
        with pytest.raises(ValueError, match="n_eff"):
            compute_u_fit(0.01, 0)


class TestUAlign:
    def test_basic(self):
        # Range is 0.03, half-range is 0.015
        assert compute_u_align([10.01, 10.02, 10.04]) == pytest.approx(0.015)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            compute_u_align([])


class TestUCal:
    def test_basic(self):
        # sqrt(0.01^2 + 0.005^2) = sqrt(0.000125) ≈ 0.01118
        assert compute_u_cal(0.01, 0.005) == pytest.approx(math.sqrt(0.000125))


class TestUTemp:
    def test_basic(self):
        # CTE=23.6e-6 mm/mm/°C, part=100mm, deltaT=2°C
        # u_temp = 23.6e-6 * 100 * 2 = 0.00472
        assert compute_u_temp(23.6e-6, 100.0, 2.0) == pytest.approx(0.00472)

    def test_negative_delta_uses_abs(self):
        assert compute_u_temp(23.6e-6, 100.0, -2.0) == pytest.approx(0.00472)


class TestURepeatPhase0:
    def test_basic(self):
        values = [10.01, 10.02, 10.03, 10.02, 10.01]
        result = compute_u_repeat_phase0(values)
        assert result > 0

    def test_single_value_raises(self):
        with pytest.raises(ValueError):
            compute_u_repeat_phase0([10.0])


class TestUBiasEstPhase0:
    def test_basic(self):
        scans = [10.03, 10.02, 10.04, 10.03, 10.02]
        result = compute_u_bias_est_phase0(scans, 10.0)
        assert result > 0


class TestCombineUncertainty:
    def test_rss_not_linear_sum(self):
        """CRITICAL: RSS (root sum of squares), NOT linear sum."""
        result = combine_uncertainty(
            u_fit=0.01, u_repeat=0.02, u_reprod=0.01, u_align=0.005,
            u_cal=0.003, u_ref=0.002, u_temp=0.001, u_bias_est=0.001,
        )
        # RSS
        expected_uc = math.sqrt(0.01**2 + 0.02**2 + 0.01**2 + 0.005**2 +
                                0.003**2 + 0.002**2 + 0.001**2 + 0.001**2)
        assert result.u_combined == pytest.approx(expected_uc)
        # Verify it's NOT the linear sum
        linear_sum = 0.01 + 0.02 + 0.01 + 0.005 + 0.003 + 0.002 + 0.001 + 0.001
        assert result.u_combined < linear_sum

    def test_expanded_uncertainty(self):
        result = combine_uncertainty(
            u_fit=0.01, u_repeat=0.02, u_reprod=0.01, u_align=0.005,
            u_cal=0.003, u_ref=0.002, u_temp=0.001, u_bias_est=0.001,
        )
        assert result.expanded_uncertainty == pytest.approx(result.u_combined * 2.0)

    def test_coverage_inflation_at_full_coverage(self):
        result = combine_uncertainty(
            u_fit=0.01, u_repeat=0.01, u_reprod=0.01, u_align=0.01,
            u_cal=0.01, u_ref=0.01, u_temp=0.01, u_bias_est=0.01,
            coverage_fraction=0.90, required_coverage=0.80,
        )
        assert result.coverage_inflation == 1.0

    def test_coverage_inflation_at_low_coverage(self):
        result = combine_uncertainty(
            u_fit=0.01, u_repeat=0.01, u_reprod=0.01, u_align=0.01,
            u_cal=0.01, u_ref=0.01, u_temp=0.01, u_bias_est=0.01,
            coverage_fraction=0.60, required_coverage=0.80,
        )
        assert result.coverage_inflation == pytest.approx(0.80 / 0.60)
        assert result.coverage_inflation > 1.0  # MUST inflate, never deflate

    def test_coverage_below_50_raises(self):
        with pytest.raises(ValueError, match="below 0.50"):
            combine_uncertainty(
                u_fit=0.01, u_repeat=0.01, u_reprod=0.01, u_align=0.01,
                u_cal=0.01, u_ref=0.01, u_temp=0.01, u_bias_est=0.01,
                coverage_fraction=0.40,
            )

    def test_none_component_raises(self):
        with pytest.raises(ValueError, match="None"):
            combine_uncertainty(
                u_fit=None, u_repeat=0.01, u_reprod=0.01, u_align=0.01,
                u_cal=0.01, u_ref=0.01, u_temp=0.01, u_bias_est=0.01,
            )

    def test_all_8_components_in_result(self):
        result = combine_uncertainty(
            u_fit=0.006, u_repeat=0.008, u_reprod=0.005, u_align=0.003,
            u_cal=0.002, u_ref=0.001, u_temp=0.001, u_bias_est=0.002,
        )
        assert result.u_fit == 0.006
        assert result.u_repeat == 0.008
        assert result.u_reprod == 0.005
        assert result.u_align == 0.003
        assert result.u_cal == 0.002
        assert result.u_ref == 0.001
        assert result.u_temp == 0.001
        assert result.u_bias_est == 0.002


# ========================================================================
# Confidence Evaluation Tests
# ========================================================================

def _good_evidence() -> ConfidenceEvidence:
    """Evidence that passes all Class A gates."""
    return ConfidenceEvidence(
        local_density=8.0,
        local_coverage=0.90,
        incidence_angle_median=30.0,
        fit_residual=0.010,
        inter_scan_stddev=0.10,
        boundary_proximity=5.0,
        alignment_sensitivity=0.05,
    )


def _marginal_evidence() -> ConfidenceEvidence:
    """Evidence that fails Class A but passes Class B."""
    return ConfidenceEvidence(
        local_density=3.0,     # below A (5.0), above B (2.5)
        local_coverage=0.60,   # below A (0.80), above B (0.50)
        incidence_angle_median=65.0,  # above A (60), below B (75)
        fit_residual=0.015,
        inter_scan_stddev=0.30,  # above A (0.25), below B (0.50)
        boundary_proximity=2.0,  # below A (3.0), above B (1.0)
        alignment_sensitivity=0.10,
    )


def _bad_evidence() -> ConfidenceEvidence:
    """Evidence that fails both Class A and Class B gates."""
    return ConfidenceEvidence(
        local_density=1.0,       # below B (2.5)
        local_coverage=0.30,     # below B (0.50)
        incidence_angle_median=80.0,
        fit_residual=0.10,
        inter_scan_stddev=0.60,
        boundary_proximity=0.5,
        alignment_sensitivity=0.40,
    )


class TestConfidenceEvaluation:
    def test_class_c_not_eligible(self):
        result = evaluate_confidence(_good_evidence(), "C")
        assert result.effective_class == "C"
        assert result.reason_code == "MANUAL_NOT_SCAN_ELIGIBLE"

    def test_class_a_all_gates_pass(self):
        result = evaluate_confidence(_good_evidence(), "A")
        assert result.effective_class == "A"
        assert result.demoted_from is None
        assert result.reason_code is None

    def test_class_a_demoted_to_b(self):
        """CRITICAL: A feature that fails Class A but passes Class B is
        demoted to REVIEW_ONLY, not escalated to RESCAN/MANUAL."""
        result = evaluate_confidence(_marginal_evidence(), "A")
        assert result.effective_class == "B"
        assert result.demoted_from == "A"
        assert result.reason_code == "REVIEW_ONLY_CONFIDENCE_DEMOTED"
        assert result.escalation_target is None  # NOT escalated

    def test_class_a_escalated_when_b_also_fails(self):
        result = evaluate_confidence(_bad_evidence(), "A")
        assert result.effective_class == "C"
        assert result.escalation_target is not None

    def test_class_b_all_gates_pass(self):
        result = evaluate_confidence(_good_evidence(), "B")
        assert result.effective_class == "B"
        assert result.reason_code is None

    def test_class_b_escalated_to_rescan(self):
        """Coverage/density failures route to rescan when no alignment sensitivity issue."""
        evidence = _bad_evidence()
        evidence.alignment_sensitivity = 0.10  # pass B gate so rescan route is chosen
        result = evaluate_confidence(evidence, "B", is_rescan=False)
        assert result.effective_class == "C"
        assert result.escalation_target == "rescan"

    def test_class_b_escalated_to_manual_after_rescan(self):
        result = evaluate_confidence(_bad_evidence(), "B", is_rescan=True)
        assert result.effective_class == "C"
        assert result.escalation_target == "manual"

    def test_alignment_sensitivity_always_manual(self):
        """Alignment sensitivity failure is geometric, not scan quality — always manual."""
        evidence = _good_evidence()
        evidence.alignment_sensitivity = 0.40  # way above B threshold of 0.30
        result = evaluate_confidence(evidence, "B")
        assert result.escalation_target == "manual"
        assert "ALIGNMENT" in result.reason_code or "MANUAL" in result.reason_code


# ========================================================================
# Decision Engine Tests
# ========================================================================

def _passing_confidence() -> ConfidenceResult:
    return ConfidenceResult(effective_class="A", demoted_from=None, reason_code=None)

def _demoted_confidence() -> ConfidenceResult:
    return ConfidenceResult(effective_class="B", demoted_from="A",
                            reason_code="REVIEW_ONLY_CONFIDENCE_DEMOTED")

def _escalated_confidence() -> ConfidenceResult:
    return ConfidenceResult(effective_class="C", demoted_from=None,
                            reason_code="RESCAN_LOW_COVERAGE",
                            escalation_target="rescan")

def _class_b_confidence() -> ConfidenceResult:
    return ConfidenceResult(effective_class="B", demoted_from=None, reason_code=None)


class TestBiasCorrection:
    def test_bias_subtracted_not_added(self):
        """CRITICAL: corrected = measured - bias, not measured + bias."""
        assert apply_bias_correction(10.05, 0.03) == pytest.approx(10.02)

    def test_negative_bias(self):
        """If system reads low (bias = -0.02), corrected = measured - (-0.02) = measured + 0.02."""
        assert apply_bias_correction(9.98, -0.02) == pytest.approx(10.00)


class TestGuardBandLimits:
    def test_uncertainty_based_narrows(self):
        """CRITICAL: Guard band must NARROW tolerance, never widen."""
        upper, lower = compute_guard_band_limits(
            nominal=10.0, tol_plus=0.1, tol_minus=-0.1,
            method="uncertainty_based", guard_percent=0.0,
            expanded_uncertainty=0.02,
        )
        assert upper == pytest.approx(10.08)  # 10.1 - 0.02
        assert lower == pytest.approx(9.92)   # 9.9 + 0.02
        # Verify narrowed
        assert upper < 10.0 + 0.1
        assert lower > 10.0 + (-0.1)

    def test_simple_percentage_narrows(self):
        upper, lower = compute_guard_band_limits(
            nominal=10.0, tol_plus=0.1, tol_minus=-0.1,
            method="simple_percentage", guard_percent=10.0,
            expanded_uncertainty=0.0,
        )
        # Total range = 0.2, guard = 0.2 * 10% / 2 = 0.01
        assert upper == pytest.approx(10.09)
        assert lower == pytest.approx(9.91)

    def test_shared_risk_no_narrowing(self):
        upper, lower = compute_guard_band_limits(
            nominal=10.0, tol_plus=0.1, tol_minus=-0.1,
            method="shared_risk", guard_percent=0.0,
            expanded_uncertainty=0.02,
        )
        assert upper == pytest.approx(10.1)
        assert lower == pytest.approx(9.9)


class TestRenderVerdict:
    """Tests for the full decision engine."""

    def test_class_c_not_scan_eligible(self):
        v = render_verdict(
            None, None, 10.0, 0.1, -0.1,
            "uncertainty_based", 10.0, "C",
            _passing_confidence(), True, True, "pass",
        )
        assert v.status == "manual_required"
        assert v.reason_code == "MANUAL_NOT_SCAN_ELIGIBLE"

    def test_calibration_expired_blocks(self):
        v = render_verdict(
            10.02, 0.02, 10.0, 0.1, -0.1,
            "uncertainty_based", 10.0, "A",
            _passing_confidence(), False, True, "pass",
        )
        assert v.status == "blocked"
        assert v.reason_code == "BLOCKED_CALIBRATION"

    def test_recipe_mismatch_blocks(self):
        v = render_verdict(
            10.02, 0.02, 10.0, 0.1, -0.1,
            "uncertainty_based", 10.0, "A",
            _passing_confidence(), True, False, "pass",
        )
        assert v.status == "blocked"
        assert v.reason_code == "BLOCKED_RECIPE_MISMATCH"

    def test_hard_block_alignment_blocks(self):
        v = render_verdict(
            10.02, 0.02, 10.0, 0.1, -0.1,
            "uncertainty_based", 10.0, "A",
            _passing_confidence(), True, True, "hard_block",
        )
        assert v.status == "blocked"

    def test_confidence_escalation_passes_through(self):
        v = render_verdict(
            10.02, 0.02, 10.0, 0.1, -0.1,
            "uncertainty_based", 10.0, "B",
            _escalated_confidence(), True, True, "pass",
        )
        assert v.status == "rescan_needed"
        assert v.reason_code == "RESCAN_LOW_COVERAGE"

    def test_class_b_review_only(self):
        """Class B features MUST be review-only, never auto-pass."""
        v = render_verdict(
            10.02, 0.02, 10.0, 0.1, -0.1,
            "uncertainty_based", 10.0, "B",
            _class_b_confidence(), True, True, "pass",
        )
        assert v.status == "review_only"

    def test_demoted_a_to_b_review_only(self):
        """A feature demoted from A to B must be review-only."""
        v = render_verdict(
            10.02, 0.02, 10.0, 0.1, -0.1,
            "uncertainty_based", 10.0, "A",
            _demoted_confidence(), True, True, "pass",
        )
        assert v.status == "review_only"
        assert v.reason_code == "REVIEW_ONLY_CONFIDENCE_DEMOTED"

    def test_class_a_pass(self):
        """Value ± U fully inside guard-banded tolerance -> PASS."""
        v = render_verdict(
            10.03, 0.02, 10.0, 0.1, -0.1,
            "uncertainty_based", 10.0, "A",
            _passing_confidence(), True, True, "pass",
        )
        # Guard-banded: upper=10.08, lower=9.92
        # 10.03 + 0.02 = 10.05 < 10.08 ✓
        # 10.03 - 0.02 = 10.01 > 9.92 ✓
        assert v.status == "pass"

    def test_marginal_inside_not_pass(self):
        """CRITICAL: MARGINAL_INSIDE must NOT resolve to PASS.
        Value in-spec but uncertainty extends past limit -> manual verification."""
        v = render_verdict(
            10.09, 0.04, 10.0, 0.1, -0.1,
            "shared_risk", 0.0, "A",  # shared_risk = no guard band
            _passing_confidence(), True, True, "pass",
        )
        # 10.09 is in spec (< 10.1)
        # 10.09 + 0.04 = 10.13 > 10.1 — extends past upper limit
        assert v.status == "marginal_inside"
        assert v.status != "pass"

    def test_marginal_outside_not_auto_reject(self):
        """MARGINAL_OUTSIDE routes to manual, does not auto-reject."""
        v = render_verdict(
            10.11, 0.04, 10.0, 0.1, -0.1,
            "shared_risk", 0.0, "A",
            _passing_confidence(), True, True, "pass",
        )
        # 10.11 is out of spec (> 10.1)
        # 10.11 - 0.04 = 10.07 < 10.1 — uncertainty overlaps limit
        assert v.status == "marginal_outside"

    def test_fail_marginal_corrected(self):
        """FAIL_MARGINAL: entirely outside but deviation < 2*U beyond limit."""
        v = render_verdict(
            10.105, 0.004, 10.0, 0.1, -0.1,
            "shared_risk", 0.0, "A",
            _passing_confidence(), True, True, "pass",
        )
        # 10.105 out of spec
        # 10.105 - 0.004 = 10.101 > 10.1 — entirely outside
        # Beyond = 10.105 - 10.1 = 0.005, 2*U = 0.008. 0.005 < 0.008 -> FAIL_MARGINAL
        assert v.status == "fail_marginal"

    def test_fail_full_confidence(self):
        """Clear reject: value ± U entirely outside, large margin."""
        v = render_verdict(
            10.30, 0.02, 10.0, 0.1, -0.1,
            "shared_risk", 0.0, "A",
            _passing_confidence(), True, True, "pass",
        )
        # 10.30 - 0.02 = 10.28 >> 10.1 — way outside
        # Beyond = 10.30 - 10.1 = 0.20, 2*U = 0.04. 0.20 > 0.04 -> FAIL_FULL
        assert v.status == "fail_full"
        assert v.reason_code == "FAIL_FULL_CONFIDENCE"

    def test_phase0_all_class_b_never_pass(self):
        """In Phase 0, all features are Class B. No auto-disposition allowed."""
        v = render_verdict(
            10.00, 0.001, 10.0, 0.1, -0.1,  # perfect measurement
            "uncertainty_based", 10.0, "B",
            _class_b_confidence(), True, True, "pass",
        )
        assert v.status == "review_only"
        assert v.status != "pass"

    def test_check_order_calibration_before_pass(self):
        """Calibration check must happen before any pass verdict."""
        # Class A, perfect measurement, but calibration expired
        v = render_verdict(
            10.00, 0.001, 10.0, 0.1, -0.1,
            "uncertainty_based", 10.0, "A",
            _passing_confidence(), False, True, "pass",  # calibration_valid=False
        )
        assert v.status == "blocked"
        assert v.status != "pass"

    def test_soft_degrade_alignment_makes_review_only(self):
        """Soft-degrade alignment demotes all features to review-only."""
        v = render_verdict(
            10.02, 0.02, 10.0, 0.1, -0.1,
            "uncertainty_based", 10.0, "B",
            _class_b_confidence(), True, True, "soft_degrade",
        )
        assert v.status == "review_only"
        assert v.reason_code == "REVIEW_ONLY_ALIGNMENT_DEGRADED"

    def test_soft_degrade_alignment_blocks_class_a_pass(self):
        """CRITICAL (C2 fix): Class A feature under soft-degrade alignment
        must NOT get a PASS verdict. Must be demoted to review-only."""
        v = render_verdict(
            10.00, 0.001, 10.0, 0.1, -0.1,  # perfect measurement
            "uncertainty_based", 10.0, "A",
            _passing_confidence(), True, True, "soft_degrade",
        )
        assert v.status == "review_only"
        assert v.reason_code == "REVIEW_ONLY_ALIGNMENT_DEGRADED"
        assert v.status != "pass"

    def test_guard_band_gap_no_false_accept(self):
        """CRITICAL (C1 fix): Value between guard-banded and original limits
        must NOT resolve to PASS. Must be MARGINAL_INSIDE.

        Example: nominal=10.0, tol=±0.1, U=0.02, uncertainty_based guard band.
        Guard-banded upper = 10.08, original upper = 10.1.
        Value = 10.07: value_upper = 10.09 > 10.08 (guard-banded) but < 10.1 (original).
        Old code: fell through to defensive PASS. Fixed code: MARGINAL_INSIDE.
        """
        v = render_verdict(
            10.07, 0.02, 10.0, 0.1, -0.1,
            "uncertainty_based", 10.0, "A",
            _passing_confidence(), True, True, "pass",
        )
        # Guard-banded upper = 10.08, value + U = 10.09 > 10.08
        # Value is in-spec (10.07 < 10.1), so this is MARGINAL_INSIDE
        assert v.status == "marginal_inside"
        assert v.status != "pass"

    def test_guard_band_gap_lower_no_false_accept(self):
        """Same as above but on the lower limit side."""
        v = render_verdict(
            9.93, 0.02, 10.0, 0.1, -0.1,
            "uncertainty_based", 10.0, "A",
            _passing_confidence(), True, True, "pass",
        )
        # Guard-banded lower = 9.92, value - U = 9.91 < 9.92
        # Value is in-spec (9.93 > 9.9), so this is MARGINAL_INSIDE
        assert v.status == "marginal_inside"
        assert v.status != "pass"
