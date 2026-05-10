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


@pytest.fixture(scope="module")
def static_proofset(proofset_module: object) -> object:
    """Run generate_static() once per test module so variant matrix +
    freestyle pairings exist on disk before downstream tests assert
    artifact presence. ``outputs/`` is gitignored, so on a fresh CI
    checkout the artifacts only exist after this fixture runs."""
    proofset_module.generate_static()  # type: ignore[attr-defined]
    return proofset_module


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


def test_variant_matrix_full_artifact_coverage(static_proofset: object) -> None:
    """Every variant of every genome with a variants[] axis must produce its full
    artifact suite. Compact-badge presence is gated on the genome's badge paradigm:
    cellular declares glyph_size_compact, chrome does not — so chrome variants
    emit only the default size. Charts may legitimately skip if the GitHub
    stargazer cross-check fails — same skip semantics as the base data-cards test.
    """
    from hyperweave.config.loader import load_genomes, load_paradigms
    from hyperweave.core.enums import ArtifactStatus, GenomeId

    static_proofset._generate_data_cards()  # type: ignore[attr-defined]

    out_dir = static_proofset.OUT  # type: ignore[attr-defined]
    genomes = load_genomes()
    paradigms = load_paradigms()

    for genome in GenomeId:
        cfg = genomes.get(str(genome))
        if cfg is None or not cfg.variants:
            continue  # brutalist + telemetry-* skip — no variant axis
        var_dir = out_dir / "proofset" / genome / "variants"
        divider_slug = "band" if genome == GenomeId.CHROME else "dissolve"

        # Compact-badge gate matches the proofset script: cellular paradigm
        # declares glyph_size_compact, chrome does not.
        badge_paradigm_slug = cfg.paradigms.get("badge", "default")
        badge_paradigm = paradigms.get(badge_paradigm_slug)
        supports_compact = badge_paradigm is not None and badge_paradigm.badge.glyph_size_compact > 0

        for variant in cfg.variants:
            # Chrome supports binary-opposition icons (circle + square);
            # other genomes are monoshape.
            if genome == GenomeId.CHROME:
                icon_files = [
                    f"icon_github_{variant}_circle.svg",
                    f"icon_github_{variant}_square.svg",
                ]
            else:
                icon_files = [f"icon_github_{variant}.svg"]
            compact_files = [f"badge_pypi_{variant}_compact.svg"] if supports_compact else []
            expected = [
                f"badge_pypi_{variant}_default.svg",
                *compact_files,
                *icon_files,
                f"strip_{variant}.svg",
                f"marquee_horizontal_{variant}.svg",
                f"divider_{divider_slug}_{variant}.svg",
                f"stats_{variant}.svg",
                # 5 badge states
                *[
                    f"badge_{s.value}_{variant}.svg"
                    for s in (
                        ArtifactStatus.PASSING,
                        ArtifactStatus.WARNING,
                        ArtifactStatus.CRITICAL,
                        ArtifactStatus.BUILDING,
                        ArtifactStatus.OFFLINE,
                    )
                ],
            ]
            for filename in expected:
                path = var_dir / filename
                assert path.exists(), f"variant artifact missing: {path}"
                assert path.stat().st_size > 500, f"variant artifact too small: {path}"

            # Chart is conditional on GitHub fetch — same skip pattern as base.
            chart_path = var_dir / f"chart_stars_{variant}.svg"
            if chart_path.exists():
                assert chart_path.stat().st_size > 500, f"variant chart too small: {chart_path}"


def test_generate_readme_includes_new_sections(static_proofset: object) -> None:
    """README embeds stats + chart inline under each genome section.
    Depends on ``static_proofset`` so the variant matrix + freestyle pairings
    artifacts exist on disk before README emission — the README writer's
    `if path.exists()` guards skip references when files are missing, which
    on a fresh CI checkout (``outputs/`` is gitignored) means image refs
    silently disappear without the variant proofset run."""
    static_proofset._generate_data_cards()  # type: ignore[attr-defined]
    static_proofset.generate_readme(100, 0)  # type: ignore[attr-defined]

    out_dir = static_proofset.OUT  # type: ignore[attr-defined]
    readme = (out_dir / "README.md").read_text()
    assert "### Profile Card (stats)" in readme
    assert "### Star History Chart" in readme
    assert "data-cards/stats.svg" in readme
    assert "data-cards/chart_stars_full.svg" in readme
    # Timeline section removed in v0.2.14.
    assert "### Timeline / Roadmap" not in readme
    assert "timeline.svg" not in readme
    # v0.3.0 variant matrix sections (one per genome with variants[]).
    # Chrome ships 5 variants inline; automata ships 16 solo tones in a
    # sibling README_AUTOMATA.md (the 16-tone matrix would otherwise dominate
    # the main README). The main README links to that sibling and inlines a
    # spot-check of representative tones for flavor.
    assert "### Variant Matrix (5 variants)" in readme  # chrome
    assert "### Variant Matrix (16 variants)" in readme  # automata stub heading
    assert "[README_AUTOMATA.md](README_AUTOMATA.md)" in readme  # link to full matrix
    # Chrome variants — full inline matrix
    for v in ("horizon", "abyssal", "lightning", "graphite", "moth"):
        assert f"variants/badge_pypi_{v}_default.svg" in readme
        assert f"variants/strip_{v}.svg" in readme

    # Automata's full 16-tone matrix lives in README_AUTOMATA.md.
    automata_readme = (out_dir / "README_AUTOMATA.md").read_text()
    assert automata_readme.startswith("# HyperWeave Automata"), "README_AUTOMATA.md should have an H1 header"
    # All 16 solo tones present
    for v in (
        "violet",
        "teal",
        "bone",
        "steel",
        "amber",
        "jade",
        "magenta",
        "cobalt",
        "toxic",
        "solar",
        "abyssal",
        "crimson",
        "sulfur",
        "indigo",
        "burgundy",
        "copper",
    ):
        assert f"variants/badge_pypi_{v}_default.svg" in automata_readme
    # Freestyle pairings showcase
    assert "## Freestyle Pairings" in automata_readme
    # At least a few representative pair examples
    for primary, secondary in (("teal", "violet"), ("cobalt", "magenta"), ("solar", "abyssal")):
        assert f"?variant={primary}&pair={secondary}" in automata_readme
        assert f"pairings/strip_{primary}-{secondary}.svg" in automata_readme
