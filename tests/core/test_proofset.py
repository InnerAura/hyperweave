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

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
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

    glm5 = out_dir / "proofset" / "chrome" / "data-cards" / "stats_glm5_multiprovider.svg"
    if glm5.exists():
        svg = glm5.read_text()
        assert "https://github.com/zai-org/GLM-5" in svg
        assert "github.com/glm-5" not in svg

    n8n = out_dir / "proofset" / "chrome" / "data-cards" / "stats_n8n_distribution.svg"
    if n8n.exists():
        svg = n8n.read_text()
        assert "https://github.com/n8n-io/n8n" in svg
        assert "github.com/n8n</text>" not in svg

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
        # Divider slug is genome-specific (chrome=band, automata=dissolve,
        # brutalist=seam). Read from genome config so v0.3.2 brutalist variants
        # check against its own seam divider, not a hardcoded "dissolve".
        divider_slug = cfg.dividers[0] if cfg.dividers else "dissolve"

        # Compact-badge gate matches the proofset script: a paradigm supports
        # compact when it declares distinct compact geometry (explicit compact
        # size, a compact ratio — primer: 0.5, or a differing compact height —
        # primer: 20 vs 36). cellular/primer support it; chrome does not.
        badge_paradigm_slug = cfg.paradigms.get("badge", "default")
        badge_paradigm = paradigms.get(badge_paradigm_slug)
        supports_compact = badge_paradigm is not None and (
            badge_paradigm.badge.glyph_size_compact > 0
            or badge_paradigm.badge.glyph_size_compact_ratio > 0
            or badge_paradigm.badge.frame_height_compact != badge_paradigm.badge.frame_height
        )

        for variant in cfg.variants:
            # Divider slug is substrate-aware for brutalist: light scholars
            # default to sigil, dark substrates to seam (mirrors the proofset
            # generator). Other genomes use their single declared divider.
            if genome == GenomeId.BRUTALIST:
                substrate = cfg.variant_overrides.get(variant, {}).get("substrate_kind", "dark")
                variant_divider_slug = "sigil" if substrate == "light" else "seam"
            else:
                variant_divider_slug = divider_slug
            # Icon shapes are data-driven from the genome's icon paradigm
            # ``supported_shapes`` (chrome/brutalist/primer: [circle, square];
            # automata: [square] → single canonical icon). Mirrors the proofset.
            icon_paradigm = paradigms.get(cfg.paradigms.get("icon", "default"))
            icon_shapes = list(icon_paradigm.icon.supported_shapes) if icon_paradigm else []
            if len(icon_shapes) > 1:
                icon_files = [f"icon_github_{variant}_{shape}.svg" for shape in icon_shapes]
            else:
                icon_files = [f"icon_github_{variant}.svg"]
            states = (
                ArtifactStatus.PASSING,
                ArtifactStatus.WARNING,
                ArtifactStatus.CRITICAL,
                ArtifactStatus.BUILDING,
                ArtifactStatus.OFFLINE,
            )
            compact_files = [f"badge_pypi_{variant}_compact.svg"] if supports_compact else []
            compact_state_files = [f"badge_{s.value}_{variant}_compact.svg" for s in states] if supports_compact else []
            expected = [
                f"badge_pypi_{variant}_default.svg",
                *compact_files,
                *icon_files,
                f"strip_{variant}.svg",
                f"marquee_{variant}.svg",
                f"divider_{variant_divider_slug}_{variant}.svg",
                f"stats_{variant}.svg",
                # 5 badge states (+ compact states when the paradigm supports compact)
                *[f"badge_{s.value}_{variant}.svg" for s in states],
                *compact_state_files,
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
    """Main README links out to genome-specific READMEs + telemetry README.

    v0.3.9 round 2 slim restructure: the main README no longer inlines
    Variant Matrix / State Machine / Profile Card / Star History Chart
    sections per genome — those live in the genome-specific README files
    (README_BRUTALIST.md, README_CHROME.md, README_AUTOMATA.md). Telemetry
    moved to README_TELEMETRY.md. The main README retains Base Frames,
    Policy Lanes, Border Motions, InnerAura dividers, telemetry cross-link,
    and the parity summary.

    Save/restore guard: ``generate_readme`` writes the slim base README; the
    full proofset run appends an Edge Cases section + parity summary to that
    file in a second pass. This test only exercises the base writer, so we
    capture the pre-test README content (if any) and restore it on exit. Keeps
    pytest from clobbering the visual-review surface devs build with
    ``python scripts/generate_proofset.py``.
    """
    out_dir = static_proofset.OUT  # type: ignore[attr-defined]
    readme_path = out_dir / "README.md"
    pre_test_content = readme_path.read_text() if readme_path.exists() else None
    try:
        static_proofset._generate_data_cards()  # type: ignore[attr-defined]
        static_proofset.generate_readme(100, 0)  # type: ignore[attr-defined]

        readme = readme_path.read_text()
        # Sections that remain in the slim main README.
        assert "### Base Frames" in readme
        assert "### Policy Lanes" in readme
        assert "### Border Motions" in readme
        assert "## `/a/inneraura/dividers/`" in readme
        assert "## Telemetry" in readme
        # Cross-links to genome READMEs + telemetry README.
        assert "[README_BRUTALIST.md](README_BRUTALIST.md)" in readme
        assert "[README_CHROME.md](README_CHROME.md)" in readme
        assert "[README_AUTOMATA.md](README_AUTOMATA.md)" in readme
        assert "[README_TELEMETRY.md](README_TELEMETRY.md)" in readme
        # Sections that moved to genome-specific READMEs (and should NOT be in main).
        assert "### Profile Card (stats)" not in readme
        assert "### Star History Chart" not in readme
        assert "### Variant Matrix" not in readme
    finally:
        if pre_test_content is not None:
            readme_path.write_text(pre_test_content)
    assert "### State Machine" not in readme
    # Timeline section removed in v0.2.14.
    assert "### Timeline / Roadmap" not in readme

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


def test_cost_buckets_track_session_cost_not_file_size(proofset_module: object) -> None:
    """Telemetry size buckets are picked off the parsed session **cost**, not the
    on-disk byte size — a small-but-costly session outranks a big-but-cheap one.

    Regression guard for the v0.4 fix: file bytes are dominated by attachments +
    file-history snapshots, so byte-size bucketing labelled a $0.34 transcript
    'xlarge'. ``_pick_cost_buckets`` only sees ``(cost_usd, path)`` pairs, so it
    *cannot* fall back to size; this pins the ascending-cost ordering it must keep.
    """
    pick = proofset_module._pick_cost_buckets  # type: ignore[attr-defined]
    # Cost order deliberately unrelated to any notion of file size.
    parsed = [
        (0.34, Path("cheap_but_huge_file.jsonl")),
        (5.43, Path("b.jsonl")),
        (20.75, Path("c.jsonl")),
        (91.36, Path("d.jsonl")),
        (414.88, Path("costly_but_small_file.jsonl")),
    ]
    picks = pick(parsed, "")
    labels = [label for label, _ in picks]
    names = [p.name for _, p in picks]
    assert labels == ["small", "medium", "large", "xlarge", "xxlarge"]
    assert names[0] == "cheap_but_huge_file.jsonl"  # $0.34 → small
    assert names[-1] == "costly_but_small_file.jsonl"  # $414.88 → xxlarge

    cost_by_name = {p.name: c for c, p in parsed}
    pick_costs = [cost_by_name[n] for n in names]
    assert pick_costs == sorted(pick_costs), "buckets must ascend in session cost"

    # Empty pool → empty (caller falls back to the deterministic specimen set).
    assert pick([], "") == []
