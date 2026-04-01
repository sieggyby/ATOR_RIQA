"""STEP file loading via OpenCascade/cadquery.

Loads STEP files, tessellates to mesh, samples surface to point cloud,
and computes deterministic SHA-256 hash of raw file bytes.

See spec Section 5, Step 1.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class CADModel:
    """Loaded CAD model with mesh and metadata."""
    file_path: Path
    file_hash_sha256: str       # SHA-256 of raw file bytes — deterministic
    vertices: np.ndarray        # (N, 3) mesh vertices
    faces: np.ndarray           # (M, 3) triangle indices
    surface_points: np.ndarray  # (P, 3) sampled surface point cloud
    bbox_min: np.ndarray        # (3,)
    bbox_max: np.ndarray        # (3,)
    bbox_size_mm: np.ndarray    # (3,)


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of raw file bytes.

    This is a deterministic hash of the file content, not a hash of
    the parsed geometry. Two identical STEP files will produce the
    same hash regardless of platform.
    """
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_step(
    file_path: str | Path,
    surface_sample_count: int = 50000,
) -> CADModel:
    """Load a STEP file, tessellate to mesh, sample surface points.

    Uses cadquery/OpenCascade for STEP parsing and tessellation,
    then trimesh for surface sampling.

    Args:
        file_path: Path to STEP file (.step or .stp).
        surface_sample_count: Number of points to sample from mesh surface.

    Returns:
        CADModel with mesh data, surface point cloud, and file hash.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file cannot be parsed or has no geometry.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"STEP file not found: {path}")

    suffix = path.suffix.lower()
    if suffix not in (".step", ".stp"):
        raise ValueError(f"Unsupported CAD file format: {suffix!r}. Use .step or .stp.")

    import cadquery as cq
    import trimesh

    # SHA-256 of raw bytes — computed BEFORE any parsing
    file_hash = compute_file_hash(path)

    # Load and tessellate via cadquery
    result = cq.importers.importStep(str(path))
    if result is None:
        raise ValueError(f"Failed to load STEP file: {path}")

    # Tessellate to mesh — cadquery returns OCC shapes, tessellate via exportStl trick
    # Export to STL in memory, reload with trimesh for uniform mesh handling
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        cq.exporters.export(result, tmp_path, exportType="STL", tolerance=0.01, angularTolerance=0.1)
        mesh = trimesh.load(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if not hasattr(mesh, "vertices") or len(mesh.vertices) == 0:
        raise ValueError(f"STEP file produced empty mesh: {path}")

    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.faces)

    # Sample surface points uniformly
    surface_points = np.asarray(mesh.sample(surface_sample_count))

    bbox_min = vertices.min(axis=0)
    bbox_max = vertices.max(axis=0)
    bbox_size = bbox_max - bbox_min

    return CADModel(
        file_path=path,
        file_hash_sha256=file_hash,
        vertices=vertices,
        faces=faces,
        surface_points=surface_points,
        bbox_min=bbox_min,
        bbox_max=bbox_max,
        bbox_size_mm=bbox_size,
    )
