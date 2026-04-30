"""Smoke test for the proof set generator (Session 2A+2B Phase 7).

Runs ``scripts/generate_proofset.py`` functions directly (skipping the
argparse entry point) and asserts that all expected Session 2A+2B artifacts
are written and non-empty. Does NOT compare pixel output — that's what the
manual visual review is for.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "generate_proofset.py"


@pytest.fixture(scope="module")
def proofset_module() -> object:
    """Load the generator module by path (it's a script, not a package)."""
    spec = importlib.util.spec_from_file_location("generate_proofset", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generate_session_2a2b_writes_stats_and_chart(proofset_module: object) -> None:
    """Run the stats + chart generator and verify every expected artifact exists.

    Timeline was removed in v0.2.14; the section header retained its name
    in the script for git-history continuity but only stats + chart artifacts
    are emitted now.
    """
    from hyperweave.core.enums import GenomeId

    count = proofset_module._generate_session_2a2b()  # type: ignore[attr-defined]
    assert count > 0, "generator should emit at least one artifact"

    out_dir = proofset_module.OUT  # type: ignore[attr-defined]
    expected_files = ("stats.svg", "chart_stars_full.svg")
    for genome in GenomeId:
        gdir = out_dir / "proofset" / genome / "session-2a2b"
        for fname in expected_files:
            fpath = gdir / fname
            assert fpath.exists(), f"expected artifact missing: {fpath}"
            assert fpath.stat().st_size > 500, f"artifact too small: {fpath}"
            assert "<svg" in fpath.read_text(), f"not valid SVG: {fpath}"


def test_generate_readme_includes_new_sections(proofset_module: object) -> None:
    """README embeds stats + chart inline under each genome section."""
    proofset_module._generate_session_2a2b()  # type: ignore[attr-defined]
    proofset_module.generate_readme(100, 0)  # type: ignore[attr-defined]

    out_dir = proofset_module.OUT  # type: ignore[attr-defined]
    readme = (out_dir / "README.md").read_text()
    assert "### Profile Card (stats)" in readme
    assert "### Star History Chart" in readme
    assert "session-2a2b/stats.svg" in readme
    assert "session-2a2b/chart_stars_full.svg" in readme
    # Timeline section removed in v0.2.14.
    assert "### Timeline / Roadmap" not in readme
    assert "timeline.svg" not in readme
    # Automata family-axis section
    assert "### Family Axis" in readme
    assert "families/badge_pypi_blue_default.svg" in readme
    assert "families/badge_pypi_purple_compact.svg" in readme
    assert "families/divider_cellular_dissolve.svg" in readme
