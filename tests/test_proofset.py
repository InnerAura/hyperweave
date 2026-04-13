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


def test_generate_session_2a2b_writes_all_frames(proofset_module: object) -> None:
    """Run the Session 2A+2B generator and verify every expected artifact exists."""
    # The generator writes under OUT / "proofset" / genome / "session-2a2b".
    # OUT is resolved inside the module and points to the real outputs/ directory.
    # We call the private helper directly so we don't need to shell out.
    from hyperweave.core.enums import GenomeId

    count = proofset_module._generate_session_2a2b()  # type: ignore[attr-defined]
    assert count > 0, "generator should emit at least one artifact"

    out_dir = proofset_module.OUT  # type: ignore[attr-defined]
    expected_files = ("stats.svg", "chart_stars_full.svg", "timeline.svg")
    for genome in GenomeId:
        gdir = out_dir / "proofset" / genome / "session-2a2b"
        for fname in expected_files:
            fpath = gdir / fname
            assert fpath.exists(), f"expected artifact missing: {fpath}"
            assert fpath.stat().st_size > 500, f"artifact too small: {fpath}"
            assert "<svg" in fpath.read_text(), f"not valid SVG: {fpath}"


def test_generate_readme_includes_new_sections(proofset_module: object) -> None:
    """After running the generators, README.md mentions the new sections."""
    proofset_module._generate_session_2a2b()  # type: ignore[attr-defined]
    proofset_module.generate_readme(100, 0)  # type: ignore[attr-defined]

    out_dir = proofset_module.OUT  # type: ignore[attr-defined]
    readme = (out_dir / "README.md").read_text()
    assert "## Stats Cards (Session 2A+2B)" in readme
    assert "## Star Charts (Session 2A+2B)" in readme
    assert "## Timeline / Roadmap (Session 2A+2B)" in readme
    # Every genome's new section should have at least one SVG image reference.
    assert "session-2a2b/stats.svg" in readme
    assert "session-2a2b/chart_stars_full.svg" in readme
    assert "session-2a2b/timeline.svg" in readme
