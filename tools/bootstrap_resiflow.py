#!/usr/bin/env python3
"""Bootstrap ResiFlow from the DAFNI-NIRD Phase 0 tag."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RESIFLOW = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO.parent / "ResiFlow"

COPY_DIRS = [
    ("src/nird", "src/resiflow"),
    ("src/preprocess", "src/preprocess"),
    ("parameters", "parameters"),
    ("docs/testbeds", "docs/testbeds"),
    ("docs/reference", "docs/reference"),
    ("tests/data/sioux_falls_tntp", "tests/data/sioux_falls_tntp"),
]

COPY_FILES = [
    ("convert_faf5_to_nird.py", "convert_faf5_to_nird.py"),
    ("convert_faf5_od_to_nird.py", "convert_faf5_od_to_nird.py"),
    ("docs/hazard_agnostic_refactor.md", "docs/hazard_agnostic_refactor.md"),
    ("docs/geo_projection_conus.md", "docs/geo_projection_conus.md"),
    ("docs/faf5_county_disaggregation.md", "docs/faf5_county_disaggregation.md"),
    ("docs/CONUS_FREIGHT_WORKFLOW.md", "docs/CONUS_FREIGHT_WORKFLOW.md"),
    ("docs/lodes_passenger_module.md", "docs/lodes_passenger_module.md"),
    ("FREIGHT_OD_DISAGGREGATION.md", "docs/FREIGHT_OD_DISAGGREGATION.md"),
]

COPY_SCRIPTS = [
    "scripts/1_network_flow_model_revision.py",
    "scripts/2_intersection_analysis.py",
    "scripts/3_damage_analysis.py",
    "scripts/4_rerouting_and_recovery_scenario_loop.py",
    "scripts/build_conus_freight_od.py",
    "scripts/build_lodes_passenger_od.py",
    "scripts/summarize_scenario_run.py",
    "scripts/run_va_workflow.py",
]

TEST_FILES = [
    "tests/toy_pipeline_fixtures.py",
    "tests/sioux_falls_fixtures.py",
    "tests/test_toy_pipeline_disruptions.py",
    "tests/test_sioux_falls_pipeline_disruptions.py",
    "tests/test_disruption_flood_parity.py",
    "tests/test_faf5_paths.py",
    "tests/test_faf5_county_disaggregation.py",
    "tests/test_faf5_conus_county_od.py",
    "tests/test_freight_od_disaggregation.py",
    "tests/test_map_bts_od_to_network_centroids.py",
    "tests/test_combined_od.py",
    "tests/test_lodes_paths.py",
    "tests/test_lodes_county_od.py",
    "tests/test_geo_runtime.py",
    "tests/test_constants.py",
]

VIZ_FILES = [
    "scripts/visualizations/viz_data_loaders.py",
    "scripts/visualizations/visualize_scenario_qa.ipynb",
]


def _copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _rewrite_imports(path: Path) -> None:
    if path.suffix != ".py":
        return
    text = path.read_text(encoding="utf-8")
    updated = (
        text.replace("from nird.", "from resiflow.")
        .replace("import nird.", "import resiflow.")
        .replace('"nird"', '"resiflow"')
    )
    if updated != text:
        path.write_text(updated, encoding="utf-8")


def main() -> int:
    RESIFLOW.mkdir(parents=True, exist_ok=True)

    for src_rel, dst_rel in COPY_DIRS:
        src = REPO / src_rel
        dst = RESIFLOW / dst_rel
        if not src.exists():
            print(f"skip missing {src}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        _copy_tree(src, dst)
        print(f"copied {src_rel} -> {dst_rel}")

    shim_dst = RESIFLOW / "resiflow" / "__init__.py"
    shim_dst.parent.mkdir(parents=True, exist_ok=True)
    shim_dst.write_text(
        '"""Compatibility shim: import resiflow from repo root."""\n'
        "from pkgutil import extend_path\n"
        "from pathlib import Path\n\n"
        '__path__ = extend_path(__path__, __name__)  # type: ignore[name-defined]\n'
        'src_pkg = Path(__file__).resolve().parent.parent / "src" / "resiflow"\n'
        "if src_pkg.exists():\n"
        '    __path__.append(str(src_pkg))\n',
        encoding="utf-8",
    )

    for src_rel, dst_rel in COPY_FILES:
        src = REPO / src_rel
        if not src.exists():
            continue
        dst = RESIFLOW / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    for rel in COPY_SCRIPTS + TEST_FILES + VIZ_FILES:
        src = REPO / rel
        if not src.exists():
            continue
        dst = RESIFLOW / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    # Rewrite imports under src/resiflow and tests/scripts
    for py in (RESIFLOW / "src" / "resiflow").rglob("*.py"):
        _rewrite_imports(py)
    for folder in ("tests", "scripts", "src/resiflow/preprocess"):
        root = RESIFLOW / folder
        if root.exists():
            for py in root.rglob("*.py"):
                _rewrite_imports(py)
    for py in (RESIFLOW / "convert_faf5_to_nird.py", RESIFLOW / "convert_faf5_od_to_nird.py"):
        if py.exists():
            _rewrite_imports(py)

    pyproject = REPO / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(encoding="utf-8")
        text = text.replace('name = "nird"', 'name = "resiflow"')
        text = text.replace("National Infrastructure Resilience Demonstrator", "ResiFlow transport resilience framework")
        (RESIFLOW / "pyproject.toml").write_text(text, encoding="utf-8")

    (RESIFLOW / "LICENSE").write_text(
        (REPO / "LICENSE").read_text(encoding="utf-8")
        if (REPO / "LICENSE").exists()
        else "MIT License\n",
        encoding="utf-8",
    )

    (RESIFLOW / "NOTICE").write_text(
        "ResiFlow incorporates code from DAFNI-NIRD (nismod/DAFNI-NIRD), MIT License.\n"
        "Phase 0 baseline tag: v0.1.0-phase0-baseline\n",
        encoding="utf-8",
    )

    (RESIFLOW / "README.md").write_text(
        """# ResiFlow

Hazard-agnostic transport resilience framework (forked from DAFNI-NIRD Phase 0).

## Quick start

```powershell
pip install -e ".[dev]"
pytest tests/test_toy_pipeline_disruptions.py tests/test_sioux_falls_pipeline_disruptions.py -v --basetemp .pytest-tmp
```

## Testbeds

See [docs/testbeds/README.md](docs/testbeds/README.md).

## Attribution

Derived from [DAFNI-NIRD](https://github.com/nismod/DAFNI-NIRD). See NOTICE.
""",
        encoding="utf-8",
    )

    (RESIFLOW / ".github/workflows/test.yml").parent.mkdir(parents=True, exist_ok=True)
    (RESIFLOW / ".github/workflows/test.yml").write_text(
        """name: test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: pytest tests/test_disruption_flood_parity.py tests/test_toy_pipeline_disruptions.py tests/test_sioux_falls_pipeline_disruptions.py -v --basetemp .pytest-tmp
""",
        encoding="utf-8",
    )

    print(f"ResiFlow bootstrap complete at {RESIFLOW}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
