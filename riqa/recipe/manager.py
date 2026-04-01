"""Recipe creation, locking, and version control.

See spec Section 5, Step 6.
"""

from __future__ import annotations

from riqa.data import db as dbmod
from riqa.data.db import RiqaDatabase
from riqa.recipe.eligibility import assign_phase0_class


def create_phase0_recipe(
    db: RiqaDatabase,
    part_id: str,
    features: list[dict],
    scanner_model: str = "Creality Ferret SE",
    guard_band_method: str = "uncertainty_based",
    guard_band_percent: float = 10.0,
) -> tuple[str, list[str]]:
    """Create a Phase 0 draft recipe with all features as Class B.

    Phase 0 recipes are always 'draft' — no locking or version validation.

    Args:
        db: Database connection.
        part_id: Part UUID.
        features: List of feature dicts with keys:
            name, feature_type, nominal, tol_plus, tol_minus.

    Returns:
        (recipe_id, list of feature_ids)
    """
    recipe_id = dbmod.insert_inspection_recipe(
        db,
        part_id=part_id,
        revision="1",
        scanner_model=scanner_model,
        software_version="0.0.1",
        status="draft",  # PHASE0_SIMPLIFICATION: always draft
        default_guard_band_method=guard_band_method,
        default_guard_band_percent=guard_band_percent,
    )

    feature_ids = []
    for feat in features:
        # Phase 0: all features are Class B
        eligibility_class = assign_phase0_class(feat["feature_type"])

        feature_id = dbmod.insert_measurement_feature(
            db,
            recipe_id=recipe_id,
            name=feat["name"],
            feature_type=feat["feature_type"],
            nominal=feat["nominal"],
            tolerance_plus=feat["tol_plus"],
            tolerance_minus=feat["tol_minus"],
            eligibility_class=eligibility_class,
        )
        feature_ids.append(feature_id)

    return recipe_id, feature_ids
