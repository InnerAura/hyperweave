"""Smoke test for the proof set generator (Data-bound stats + chart frames).

Runs ``scripts/generate_proofset.py`` functions directly (skipping the
argparse entry point) and asserts that all expected Data cards (stats + chart) artifacts
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


def test_generate_data_cards_writes_stats_and_chart(proofset_module: object) -> None:
    """Run the stats + chart generator and verify every expected artifact exists.

    Timeline was removed in v0.2.14; the section header retained its name
    in the script for git-history continuity but only stats + chart artifacts
    are emitted now.

    Stats are network-independent and must always render. The chart frame
    requires a successful GitHub stargazer fetch with REST/GraphQL cross-
    check agreement; in CI without auth (or under rate-limit pressure) the
    generator deliberately skips the chart rather than ship disagreeing
    data. That's the system working as designed, not a test failure — so
    we verify stats unconditionally and `pytest.skip` the chart leg when
    the generator legitimately omitted it.
    """
    from hyperweave.core.enums import GenomeId

    count = proofset_module._generate_data_cards()  # type: ignore[attr-defined]
    assert count > 0, "generator should emit at least one artifact"

    out_dir = proofset_module.OUT  # type: ignore[attr-defined]
    for genome in GenomeId:
        stats = out_dir / "proofset" / genome / "data-cards" / "stats.svg"
        assert stats.exists(), f"expected artifact missing: {stats}"
        assert stats.stat().st_size > 500, f"artifact too small: {stats}"
        assert "<svg" in stats.read_text(), f"not valid SVG: {stats}"

    # Chart artifacts share a single upstream fetch — if one is missing
    # they're all missing, so probe one genome and skip if absent.
    sample_genome = next(iter(GenomeId))
    sample_chart = out_dir / "proofset" / sample_genome / "data-cards" / "chart_stars_full.svg"
    if not sample_chart.exists():
        pytest.skip(
            "chart artifact intentionally skipped by generator "
            "(GitHub stargazer cross-check disagreement or auth/rate-limit failure); "
            "stats artifacts verified above"
        )
    for genome in GenomeId:
        chart = out_dir / "proofset" / genome / "data-cards" / "chart_stars_full.svg"
        assert chart.exists(), f"expected artifact missing: {chart}"
        assert chart.stat().st_size > 500, f"artifact too small: {chart}"
        assert "<svg" in chart.read_text(), f"not valid SVG: {chart}"


def test_generate_readme_includes_new_sections(proofset_module: object) -> None:
    """README embeds stats + chart inline under each genome section."""
    proofset_module._generate_data_cards()  # type: ignore[attr-defined]
    proofset_module.generate_readme(100, 0)  # type: ignore[attr-defined]

    out_dir = proofset_module.OUT  # type: ignore[attr-defined]
    readme = (out_dir / "README.md").read_text()
    assert "### Profile Card (stats)" in readme
    assert "### Star History Chart" in readme
    assert "data-cards/stats.svg" in readme
    assert "data-cards/chart_stars_full.svg" in readme
    # Timeline section removed in v0.2.14.
    assert "### Timeline / Roadmap" not in readme
    assert "timeline.svg" not in readme
    # Automata variant-axis section
    assert "### Variant Axis" in readme
    assert "variants/badge_pypi_blue_default.svg" in readme
    assert "variants/badge_pypi_purple_compact.svg" in readme
    assert "variants/divider_dissolve.svg" in readme
