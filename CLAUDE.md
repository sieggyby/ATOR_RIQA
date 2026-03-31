# CLAUDE.md — RIQA (Receiving Inspection QA)

## What This Project Is

RIQA is a risk-limited, feature-gated, scan-assisted receiving inspection system. It compares 3D scans of incoming parts against CAD models to assess dimensional compliance. It is a fast first-pass screen — not a CMM replacement. It auto-dispositions features with proven capability (Class A), shows review-only measurements for marginal features (Class B), and explicitly escalates everything else to manual gauging (Class C).

The full spec is in `docs/spec-v2.4.2.md`.

## Target Platform

- **Dev machine:** This Mac (developing here, will deploy to a Mac Mini M4 Pro)
- **Production machine:** Mac Mini M4 Pro — 12-core CPU, 16-core GPU, 64GB unified RAM
- **macOS only** through Phase 2. Windows port is Phase 3+.
- **Python 3.11+**

## Architecture

```
riqa/
├── core/           # Processing pipeline (alignment, measurement, uncertainty, decision)
├── cad/            # STEP import and CAD feature extraction
├── scanner/        # Point cloud import, preprocessing, scanner profiles, calibration
├── recipe/         # Recipe management, MSA studies, feature eligibility
├── ui/             # PySide6 GUI (wizard-driven inspection flow)
├── batch/          # Phase 2 batch plate mode
├── reports/        # Jinja2 + weasyprint PDF report generation
├── data/           # SQLite database (runtime, not committed)
├── config/         # YAML settings and scanner profiles
└── cli.py          # Click CLI entry point
```

## Tech Stack

- **UI:** PySide6 (Qt 6)
- **3D rendering:** VTK via PyVista
- **Point cloud:** Open3D (ICP, SOR, normals, downsampling)
- **Primitive fitting:** trimesh + scipy (RANSAC, least-squares)
- **CAD import:** cadquery / OCP (OpenCascade) for STEP files
- **Data:** SQLite
- **Reports:** Jinja2 + weasyprint
- **Config:** YAML

## Development Phases

- **Phase 0 (current):** Feasibility kill test — can Ferret SE + Mac Mini align scans to CAD and extract useful measurements?
- **Phase 1:** Vertical slice — 3 parts, feature eligibility, decision engine, basic UI
- **Phase 2:** Guarded production pilot — recipe locking, MSA workflow, batch mode, 10+ parts
- **Phase 3:** Broaden — datum-constrained alignment, GD&T, scanner upgrade, Windows port

## Key Design Principles

1. **The scanner determines the ceiling, not the software.** Ferret SE is Class B predominantly.
2. **No measurement without validated capability.** MSA gates everything.
3. **Minimize false accepts, not false rejects.** Ambiguous → escalate, never auto-pass.
4. **Feature-level confidence, not global confidence.**
5. **The scanner is a screen, not a sentence.** Clear good parts fast, flag bad ones, route the middle to higher-fidelity instruments.

## Commands

```bash
# Install
pip install -e .

# Run CLI
riqa info

# Run tests
pytest
```

## Repo

GitHub: https://github.com/sieggyby/ATOR_RIQA
