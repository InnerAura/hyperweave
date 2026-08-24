"""Smoke test for the proof set generator (Data-bound stats + chart frames).

Runs ``python -m scripts.examples`` functions directly (skipping the
argparse entry point) and asserts that all expected Data cards (stats + chart) artifacts
are written and non-empty. Does NOT compare pixel output — that's what the
manual visual review is for.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def proofset_module() -> object:
    """The generator, imported as a module.

    It used to be loaded by file path with importlib because `scripts/` was a
    bag of loose files rather than a package. It is one now, so this is a plain
    import — and a rename can no longer leave the test loading a path that does
    not exist.
    """
    from scripts.examples import proofset

    return proofset


@pytest.fixture(scope="module")
def static_proofset(proofset_module: object) -> object:
    """Run generate_static() once per test module so variant matrix +
    freestyle pairings exist on disk before downstream tests assert
    artifact presence. ``outputs/`` is gitignored, so on a fresh CI
    checkout the artifacts only exist after this fixture runs."""
    proofset_module.generate_static()  # type: ignore[attr-defined]
    return proofset_module


def test_generate_data_cards_writes_stats_and_chart(proofset_module: object) -> None:
    """Run the live data-card generator and verify every artifact it claims.

    Stats are network-independent and must always render. The chart frame
    requires a GitHub stargazer fetch whose REST and GraphQL readings agree; in
    CI without auth, or under rate-limit pressure, the generator deliberately
    ships NO chart rather than a disagreeing one. That is the system working,
    not a test failure — so stats are checked unconditionally and the chart leg
    skips when the generator legitimately omitted it.

    Cards live beside the genome gallery they belong to (``outputs/genomes/
    <genome>/data-cards/``), not in a separate proofset tree.
    """
    from hyperweave.core.enums import GenomeId

    count = proofset_module._generate_data_cards()  # type: ignore[attr-defined]
    assert count > 0, "generator should emit at least one artifact"

    genomes_dir = proofset_module.GENOMES  # type: ignore[attr-defined]
    for genome in GenomeId:
        stats = genomes_dir / str(genome) / "data-cards" / "stats.svg"
        assert stats.exists(), f"expected artifact missing: {stats}"
        assert stats.stat().st_size > 500, f"artifact too small: {stats}"
        assert "<svg" in stats.read_text(), f"not valid SVG: {stats}"

    glm5 = genomes_dir / "chrome" / "data-cards" / "stats_glm5_multiprovider.svg"
    if glm5.exists():
        svg = glm5.read_text()
        assert "https://github.com/zai-org/GLM-5" in svg
        assert "github.com/glm-5" not in svg

    n8n = genomes_dir / "chrome" / "data-cards" / "stats_n8n_distribution.svg"
    if n8n.exists():
        svg = n8n.read_text()
        assert "https://github.com/n8n-io/n8n" in svg
        assert "github.com/n8n</text>" not in svg

    # Chart artifacts share a single upstream fetch — if one is missing they
    # all are, so probe one genome and skip rather than report N failures.
    sample_genome = next(iter(GenomeId))
    if not (genomes_dir / str(sample_genome) / "data-cards" / "chart_stars_full.svg").exists():
        pytest.skip(
            "chart artifact intentionally skipped by generator "
            "(GitHub stargazer cross-check disagreement or auth/rate-limit failure); "
            "stats artifacts verified above"
        )
    for genome in GenomeId:
        chart = genomes_dir / str(genome) / "data-cards" / "chart_stars_full.svg"
        assert chart.exists(), f"expected artifact missing: {chart}"
        assert chart.stat().st_size > 500, f"artifact too small: {chart}"
        assert "<svg" in chart.read_text(), f"not valid SVG: {chart}"


def test_gallery_declares_the_full_suite_for_every_variant() -> None:
    """Every variant of every genome declares its whole artifact suite.

    Asserts against the MANIFEST rather than re-deriving filenames. The old
    version of this test rebuilt the compact gate, the icon-shape lookup and
    the divider slug itself — a fourth copy of derivations that already lived
    in the genome config, the generator and the README emitter, and one that
    could agree with a bug rather than catch it. Here the test states the RULE
    (every declared variant carries every declared frame) and lets the gallery
    say what it built.
    """
    from scripts.examples.genomes import build_all

    from hyperweave.config.loader import load_genomes

    genomes = load_genomes()
    for genome_id, gallery in build_all().items():
        cfg = genomes[genome_id]
        declared = {art.rel for art in gallery}
        for variant in cfg.variants:
            suite = [
                f"variants/badge_pypi_{variant}_default.svg",
                f"variants/strip_{variant}.svg",
                f"variants/marquee_{variant}.svg",
                *[f"variants/divider_{slug}_{variant}.svg" for slug in cfg.dividers],
            ]
            missing = [rel for rel in suite if rel not in declared]
            assert not missing, f"{genome_id}/{variant} is missing {missing}"
            # An icon in some shape, and the five badge states.
            assert any(rel.startswith(f"variants/icon_github_{variant}") for rel in declared), (
                f"{genome_id}/{variant} declares no icon"
            )
            states = [rel for rel in declared if rel.startswith("variants/badge_") and rel.endswith(f"_{variant}.svg")]
            assert len(states) >= 5, f"{genome_id}/{variant} declares {len(states)} state badges, expected >= 5"


def test_gallery_renders_everything_it_declares() -> None:
    """Nothing declared goes unrendered, and nothing rendered goes undeclared.

    The gap this guards is the one the manifest exists to close: a document
    citing an artifact the renderer never wrote (a broken image) or a renderer
    writing one no document shows (a silently dropped section).
    """
    import asyncio

    from scripts.examples.genomes import build_gallery
    from scripts.examples.surfaces import sweep

    gallery = build_gallery("chrome")  # the smallest gallery — the rule is shape-independent
    report = asyncio.run(sweep(gallery, witnesses=()))
    assert report.rendered == len(gallery)
    for artifact in gallery:
        path = artifact.path_under(gallery.root)
        assert path.exists(), f"declared but not rendered: {artifact.rel}"
        assert path.stat().st_size > 500, f"rendered but trivial: {artifact.rel}"


def test_gallery_readme_cites_only_rendered_artifacts() -> None:
    """Every image link in a gallery README resolves to a file on disk.

    Checked on the real emitted document, not on the emitter's internals: a
    README whose links 404 is exactly what a reader sees, and asserting that
    the emitter "called image()" would not catch it.
    """
    import asyncio
    import re

    from scripts.examples.genomes import build_gallery, emit
    from scripts.examples.surfaces import sweep

    gallery = build_gallery("chrome")
    asyncio.run(sweep(gallery, witnesses=()))
    readme = emit(gallery)
    links = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", readme.read_text())
    assert links, "the gallery README embeds no artifacts at all"
    missing = [link for link in links if not (readme.parent / link).exists()]
    assert not missing, f"README cites artifacts that were never rendered: {missing[:5]}"


def test_generate_readme_indexes_every_gallery(static_proofset: object) -> None:
    """The root README is an INDEX: it links each gallery instead of inlining it.

    It used to re-embed each genome's base frames, policy lanes and border
    motions through a second set of hand-built paths — the same artifacts each
    gallery now shows in context. Save/restore the file so a test run doesn't
    clobber the visual-review surface built by a real generator run.
    """
    from hyperweave.config.loader import load_genomes

    out_dir = static_proofset.OUT  # type: ignore[attr-defined]
    readme_path = out_dir / "README.md"
    pre_test_content = readme_path.read_text() if readme_path.exists() else None
    try:
        static_proofset.generate_readme(100, 0)  # type: ignore[attr-defined]
        readme = readme_path.read_text()

        for genome_id, cfg in load_genomes().items():
            if not cfg.variants:
                continue
            assert f"(genomes/{genome_id}/README.md)" in readme, f"{genome_id} gallery not linked"
        # Every gallery is linked, none is inlined — that is what an index is.
        for gallery in ("matrices", "states", "telemetry", "verbs", "artifacts", "parity"):
            assert f"({gallery}/README.md)" in readme, f"{gallery} gallery not linked from the index"

        # The per-genome tours moved into the galleries; the index must not
        # grow a second copy of them.
        for moved in ("### Base Frames", "### Policy Lanes", "### Border Motions", "### Variant Matrix"):
            assert moved not in readme, f"{moved} belongs to the gallery, not the index"
        # Retired documents must not be advertised.
        for retired in ("README_BRUTALIST.md", "README_CHROME.md", "README_AUTOMATA.md", "README_PRIMER.md"):
            assert retired not in readme, f"{retired} was retired — the index still links it"
    finally:
        if pre_test_content is not None:
            readme_path.write_text(pre_test_content)


def test_verb_readme_emits_chains_with_embedded_artifacts() -> None:
    """The verb gallery is three workflow chains, each paired with real renders.

    Guards the convention that every operation is embedded next to the artifact
    it produced — no expected-output prose. The generator runs the verbs for
    real, so this asserts the chains, the appendix, and that every embedded SVG
    resolves. Save/restore the doc so a test run does not clobber the dev's
    visual-review surface.
    """
    import re

    from scripts.examples.verbs import VERBS_ROOT, emit

    readme = VERBS_ROOT / "README.md"
    pre = readme.read_text() if readme.exists() else None
    try:
        emit()
        doc = readme.read_text()
        for chain in (
            "## Chain A — artifact lifecycle",
            "## Chain B — diagram evolution",
            "## Chain C — cross-surface identity",
            "## Appendix — surface contract",
        ):
            assert chain in doc, f"missing {chain}"
        # Depth is verified visually: every embedded SVG resolves to a real file.
        # Links are gallery-relative now — the document sits beside its renders.
        embeds = re.findall(r"!\[[^\]]*\]\(([^)]+\.svg)\)", doc)
        assert len(embeds) >= 6, f"expected the chain renders embedded, found {embeds}"
        for rel in embeds:
            svg = (readme.parent / rel).read_text()
            assert "<svg" in svg[:200], f"{rel} is not an SVG"
        # Chain A's transform is a real content edit: parent and child differ.
        parent = (VERBS_ROOT / "chainA-1-parent.svg").read_text()
        child = (VERBS_ROOT / "chainA-2-child.svg").read_text()
        assert parent != child, "the transformed matrix must differ from its parent"
    finally:
        if pre is not None:
            readme.write_text(pre)


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


def test_mock_receipt_payload_error_ticks_are_self_consistent(proofset_module: object) -> None:
    """The context-load plot draws one red tick per main-thread error's REAL
    minute (``error_min``); a count without minutes renders "14 errors, zero
    ticks" — the self-inconsistency that flattened the committed examples
    once. The shared mock must carry one minute per declared error, inside
    the active window, and its render must actually emit the ticks."""
    payload = proofset_module.MOCK_RECEIPT_PAYLOAD
    minutes = payload["context"]["error_min"]
    assert len(minutes) == payload["errors"]
    assert all(0 <= m <= payload["active_min"] for m in minutes)

    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    svg = compose(ComposeSpec(type="receipt", genome_id="primer", variant="cream", telemetry_data=payload)).svg
    # The tick template stamps this exact stroke signature per error tick.
    assert svg.count('stroke-width="1.4" opacity="0.95"') > 0
    assert "= errors" in svg  # the legend names them


def test_the_gallery_names_the_variant_a_bare_url_renders() -> None:
    """Each genome's flagship line must be present AND correct.

    This document once dropped chrome's line entirely. The cause was reading
    only `flagship_variant`, which chrome leaves empty even though a bare
    `chrome.static` URL does render `horizon` — horizon has no
    `variant_overrides` entry, so it IS the base palette rather than a swap on
    top of it. Asserting the derivation against the two mechanisms keeps the
    claim honest whichever way a genome declares its default.
    """
    from scripts.examples.genomes import _bare_url_variant

    from hyperweave.config.loader import load_genomes

    genomes = load_genomes()

    # Declared flagship: the resolver applies it by name.
    assert _bare_url_variant(genomes["brutalist"]) == "celadon"
    assert _bare_url_variant(genomes["primer"]) == "porcelain"
    # No declared flagship, one variant with no chromatic override: that IS the base.
    assert _bare_url_variant(genomes["chrome"]) == "horizon"
    assert not genomes["chrome"].variant_overrides.get("horizon"), (
        "horizon gained a chromatic override — it is no longer the base palette, "
        "so the gallery's 'a bare chrome.static URL renders this' line is now false"
    )
    # Compositional tones: no single variant is the base, so claim nothing.
    assert _bare_url_variant(genomes["automata"]) == ""


def test_the_flagship_line_reaches_the_emitted_document() -> None:
    """Guard the rendered page, not the helper beneath it.

    The helper returning "horizon" would not have caught the regression — the
    line was missing from the README a reader opens.
    """
    import asyncio

    from scripts.examples.genomes import build_gallery, emit
    from scripts.examples.surfaces import sweep

    gallery = build_gallery("chrome")
    asyncio.run(sweep(gallery, witnesses=()))
    readme = emit(gallery).read_text()
    assert "a bare `chrome.static` URL renders this" in readme
    horizon_block = readme.split("### `?variant=horizon`", 1)[1].split("###", 1)[0]
    assert "flagship" in horizon_block, "the flagship note landed on the wrong variant"
