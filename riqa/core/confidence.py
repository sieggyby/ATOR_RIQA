"""Per-feature local confidence evaluation.

Evaluates: local point density, coverage fraction, incidence angle,
fit residual, inter-scan repeatability, boundary proximity,
alignment sensitivity.

Implements Section 8.2 precedence rule:
  1. If Class A: check A gates. If any fail but B gates pass -> demote to B.
  2. If Class B (original or demoted): check B gates. If any fail -> escalate.
  3. Escalation routing depends on which gate failed and whether a rescan
     has already been attempted.

See spec Section 8.2.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConfidenceEvidence:
    """Raw metric values for local confidence evaluation."""
    local_density: float          # pts/mm^2
    local_coverage: float         # fraction 0-1
    incidence_angle_median: float  # degrees
    fit_residual: float           # RMSE of primitive fit
    inter_scan_stddev: float      # std dev of measurement across individual scans
    boundary_proximity: float     # mm from feature centroid to nearest scan edge
    alignment_sensitivity: float  # measurement change as fraction of tolerance


@dataclass
class ConfidenceThresholds:
    """Gate thresholds for Class A or Class B evaluation."""
    min_density: float            # pts/mm^2
    min_coverage: float           # fraction
    max_incidence_angle: float    # degrees
    max_fit_residual: float       # mm
    max_inter_scan_stddev: float  # fraction of tolerance (multiply by tolerance to get mm)
    min_boundary_proximity: float  # mm
    max_alignment_sensitivity: float  # fraction of tolerance


# Default thresholds from spec Section 8.2 "typical" starting points
DEFAULT_CLASS_A_THRESHOLDS = ConfidenceThresholds(
    min_density=5.0,
    min_coverage=0.80,
    max_incidence_angle=60.0,
    max_fit_residual=0.02,       # will be overridden by recipe MSA value
    max_inter_scan_stddev=0.25,  # 25% of tolerance
    min_boundary_proximity=3.0,
    max_alignment_sensitivity=0.15,  # 15% of tolerance
)

DEFAULT_CLASS_B_THRESHOLDS = ConfidenceThresholds(
    min_density=2.5,             # 50% of Class A
    min_coverage=0.50,
    max_incidence_angle=75.0,
    max_fit_residual=0.05,       # will be overridden by recipe MSA value * 2.5
    max_inter_scan_stddev=0.50,  # 50% of tolerance
    min_boundary_proximity=1.0,
    max_alignment_sensitivity=0.30,  # 30% of tolerance
)


@dataclass
class ConfidenceResult:
    """Result of confidence evaluation for a single feature."""
    effective_class: str          # 'A', 'B', or 'C' (escalated)
    demoted_from: str | None      # 'A' if demoted to B, None otherwise
    reason_code: str | None       # e.g. REVIEW_ONLY_CONFIDENCE_DEMOTED, RESCAN_LOW_COVERAGE
    failed_gates_a: list[str] = field(default_factory=list)
    failed_gates_b: list[str] = field(default_factory=list)
    escalation_target: str | None = None  # 'rescan' or 'manual'


def _check_gates(
    evidence: ConfidenceEvidence,
    thresholds: ConfidenceThresholds,
) -> list[str]:
    """Check all confidence gates. Returns list of failed gate names."""
    failed = []
    if evidence.local_density < thresholds.min_density:
        failed.append("density")
    if evidence.local_coverage < thresholds.min_coverage:
        failed.append("coverage")
    if evidence.incidence_angle_median > thresholds.max_incidence_angle:
        failed.append("incidence_angle")
    if evidence.fit_residual > thresholds.max_fit_residual:
        failed.append("fit_residual")
    if evidence.inter_scan_stddev > thresholds.max_inter_scan_stddev:
        failed.append("inter_scan_repeatability")
    if evidence.boundary_proximity < thresholds.min_boundary_proximity:
        failed.append("boundary_proximity")
    if evidence.alignment_sensitivity > thresholds.max_alignment_sensitivity:
        failed.append("alignment_sensitivity")
    return failed


# Gates that a rescan can plausibly fix
_RESCAN_FIXABLE = frozenset({"coverage", "density", "boundary_proximity", "incidence_angle"})


def _determine_escalation(
    failed_gates: list[str],
    is_rescan: bool,
) -> tuple[str, str]:
    """Determine escalation target and reason code for a feature that failed all Class B gates.

    Returns (escalation_target, reason_code).

    Routing rules (spec Section 8.2):
    - coverage/density/boundary/angle failures -> RESCAN_NEEDED (a better scan may fix)
    - fit_residual or repeatability after rescan already attempted -> MANUAL_GAUGE_REQUIRED
    - alignment_sensitivity -> MANUAL_GAUGE_REQUIRED (geometric limitation, not scan quality)
    """
    rescan_fixable = [g for g in failed_gates if g in _RESCAN_FIXABLE]
    manual_only = [g for g in failed_gates if g not in _RESCAN_FIXABLE]

    # If alignment sensitivity failed, it's always manual — geometric limitation
    if "alignment_sensitivity" in failed_gates:
        return "manual", "MANUAL_ALIGNMENT_SENSITIVE"

    # If we have rescan-fixable failures and haven't tried rescanning yet
    if rescan_fixable and not is_rescan:
        if "coverage" in rescan_fixable or "density" in rescan_fixable:
            return "rescan", "RESCAN_LOW_COVERAGE"
        return "rescan", "RESCAN_HIGH_NOISE"

    # If we already rescanned and still failing, or only non-rescan-fixable gates failed
    if manual_only or is_rescan:
        if "fit_residual" in failed_gates or "inter_scan_repeatability" in failed_gates:
            return "manual", "RESCAN_HIGH_NOISE" if not is_rescan else "MANUAL_FEATURE_TOO_SMALL"
        return "manual", "MANUAL_FEATURE_TOO_SMALL"

    # Fallback: rescan-fixable gates that haven't been rescanned
    return "rescan", "RESCAN_LOW_COVERAGE"


def evaluate_confidence(
    evidence: ConfidenceEvidence,
    feature_class: str,
    thresholds_a: ConfidenceThresholds | None = None,
    thresholds_b: ConfidenceThresholds | None = None,
    is_rescan: bool = False,
) -> ConfidenceResult:
    """Evaluate per-feature local confidence with Section 8.2 precedence.

    PRECEDENCE RULE (spec Section 8.2):
    Section 8.2 demotion is evaluated FIRST. Then Section 7.7 decision rules
    apply to the demoted class. A Class A feature that fails a Class A gate
    but passes Class B is demoted to REVIEW_ONLY_CONFIDENCE_DEMOTED — NOT
    escalated to RESCAN or MANUAL.

    Only features that fail ALL Class B gates get escalated.

    Args:
        evidence: Raw metric values.
        feature_class: 'A', 'B', or 'C'.
        thresholds_a: Class A gate thresholds (defaults used if None).
        thresholds_b: Class B gate thresholds (defaults used if None).
        is_rescan: Whether a rescan has already been attempted.
    """
    if thresholds_a is None:
        thresholds_a = DEFAULT_CLASS_A_THRESHOLDS
    if thresholds_b is None:
        thresholds_b = DEFAULT_CLASS_B_THRESHOLDS

    # Class C: not scan-eligible, no confidence evaluation needed
    if feature_class == "C":
        return ConfidenceResult(
            effective_class="C",
            demoted_from=None,
            reason_code="MANUAL_NOT_SCAN_ELIGIBLE",
        )

    # Check Class B gates (needed for both A and B features)
    failed_b = _check_gates(evidence, thresholds_b)

    if feature_class == "A":
        # Check Class A gates
        failed_a = _check_gates(evidence, thresholds_a)

        if not failed_a:
            # All Class A gates passed — feature stays Class A
            return ConfidenceResult(
                effective_class="A",
                demoted_from=None,
                reason_code=None,
                failed_gates_a=[],
                failed_gates_b=[],
            )

        # Class A gates failed. Check if Class B gates pass.
        if not failed_b:
            # Class A failed but Class B passed -> demote to B (review-only).
            # This is NOT an escalation — no rescan prompt, no manual gauge prompt.
            return ConfidenceResult(
                effective_class="B",
                demoted_from="A",
                reason_code="REVIEW_ONLY_CONFIDENCE_DEMOTED",
                failed_gates_a=failed_a,
                failed_gates_b=[],
            )

        # Both A and B gates failed -> escalate
        target, reason = _determine_escalation(failed_b, is_rescan)
        return ConfidenceResult(
            effective_class="C",  # effectively removed from scan measurement
            demoted_from="A",
            reason_code=reason,
            failed_gates_a=failed_a,
            failed_gates_b=failed_b,
            escalation_target=target,
        )

    # feature_class == "B"
    if not failed_b:
        # All Class B gates passed — feature stays Class B
        return ConfidenceResult(
            effective_class="B",
            demoted_from=None,
            reason_code=None,
            failed_gates_b=[],
        )

    # Class B gates failed -> escalate
    target, reason = _determine_escalation(failed_b, is_rescan)
    return ConfidenceResult(
        effective_class="C",
        demoted_from=None,
        reason_code=reason,
        failed_gates_b=failed_b,
        escalation_target=target,
    )
