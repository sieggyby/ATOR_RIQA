"""Feature class assignment (A/B/C) and gate evaluation.

See spec Section 4.
"""

from __future__ import annotations


def assign_phase0_class(feature_type: str) -> str:
    """Phase 0: All features are Class B.

    In Phase 0 (feasibility kill test), no MSA data exists, so no feature
    can be auto-dispositioned. ALL features are Class B (review-only).
    This means the system will never produce a pass_scan_only disposition.

    # PHASE0_SIMPLIFICATION: In Phase 1+, class assignment depends on
    # MSA study results, feature type, and scanner capability.
    """
    return "B"
