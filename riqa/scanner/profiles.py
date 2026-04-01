"""Scanner-specific parameter profiles.

Defines per-scanner-class adjustments for SOR, CAD proximity,
fusion voxel size, and min feature size.

See spec Section 7.8.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class PartTypeThresholds:
    """Thresholds for a specific scanner + part type combination."""
    sor_std_ratio: float
    cad_proximity_mm: float
    consensus_threshold: str  # e.g. "ceil(N/2)"


@dataclass
class ScannerProfile:
    """Complete scanner profile loaded from YAML."""
    scanner_class: str          # "consumer", "prosumer", "industrial"
    model: str
    accuracy_class_mm: float
    warmup_minutes: int
    sor_sigma_adjustment: float
    cad_proximity_adjustment_mm: float
    fusion_voxel_size_mm: float
    min_feature_size_class_a_mm: float
    part_types: dict[str, PartTypeThresholds]


_PROFILES_DIR = Path(__file__).resolve().parent.parent / "config" / "scanner_profiles"


def load_profile(profile_name: str, profiles_dir: Path | None = None) -> ScannerProfile:
    """Load a scanner profile YAML into a ScannerProfile dataclass.

    Args:
        profile_name: Name of the profile (without .yaml extension).
        profiles_dir: Directory containing profile YAML files.
                      Defaults to riqa/config/scanner_profiles/.

    Raises:
        FileNotFoundError: If the profile YAML does not exist.
        ValueError: If required fields are missing.
    """
    if profiles_dir is None:
        profiles_dir = _PROFILES_DIR

    path = profiles_dir / f"{profile_name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Scanner profile not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    required = [
        "scanner_class", "model", "accuracy_class_mm", "warmup_minutes",
        "sor_sigma_adjustment", "cad_proximity_adjustment_mm",
        "fusion_voxel_size_mm", "min_feature_size_class_a_mm", "part_types",
    ]
    for key in required:
        if key not in data:
            raise ValueError(f"Scanner profile {profile_name!r} missing required field: {key!r}")

    part_types = {}
    for pt_name, pt_data in data["part_types"].items():
        part_types[pt_name] = PartTypeThresholds(
            sor_std_ratio=pt_data["sor_std_ratio"],
            cad_proximity_mm=pt_data["cad_proximity_mm"],
            consensus_threshold=pt_data["consensus_threshold"],
        )

    return ScannerProfile(
        scanner_class=data["scanner_class"],
        model=data["model"],
        accuracy_class_mm=data["accuracy_class_mm"],
        warmup_minutes=data["warmup_minutes"],
        sor_sigma_adjustment=data["sor_sigma_adjustment"],
        cad_proximity_adjustment_mm=data["cad_proximity_adjustment_mm"],
        fusion_voxel_size_mm=data["fusion_voxel_size_mm"],
        min_feature_size_class_a_mm=data["min_feature_size_class_a_mm"],
        part_types=part_types,
    )


def get_thresholds_for_part_type(
    profile: ScannerProfile,
    part_type: str,
) -> PartTypeThresholds:
    """Get scanner-adjusted thresholds for a specific part type.

    Args:
        profile: Loaded scanner profile.
        part_type: One of the part types defined in the profile
                   (e.g. "machined_metal", "injection_molded", "fdm_printed").

    Raises:
        ValueError: If part_type is not defined in the profile.
    """
    if part_type not in profile.part_types:
        valid = list(profile.part_types.keys())
        raise ValueError(
            f"Part type {part_type!r} not defined in profile {profile.model!r}. "
            f"Valid types: {valid}"
        )
    return profile.part_types[part_type]
