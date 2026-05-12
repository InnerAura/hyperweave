"""Genome-specific dividers — v0.2.19 dispatch + (slug, genome) pairing.

Three (slug, genome) pairings post-rename:
  - (dissolve, automata) — cellular bifamily bridge, static-baked
  - (band, chrome) — chrome envelope band with material drift
  - (seam, brutalist) — concrete expansion-joint pattern

Editorial generics (block, current, takeoff, void, zeropoint) are no longer
served via /v1/divider/; they live at /a/inneraura/dividers/<slug>. The
compositor route rejects them with 404 + X-HW-Specimen-Moved header.
"""

from __future__ import annotations

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec

# ── Genome-themed dividers render ─────────────────────────────────────────


def test_automata_dissolve_renders() -> None:
    result = compose(ComposeSpec(type="divider", genome_id="automata", divider_variant="dissolve"))
    assert result.width == 800
    assert result.height == 28
    assert "<svg" in result.svg


def test_chrome_band_renders() -> None:
    result = compose(ComposeSpec(type="divider", genome_id="chrome", divider_variant="band"))
    assert result.width == 800
    assert result.height == 22
    # Chrome envelope: must contain the env gradient + at least one of the chrome stops
    assert 'id="' in result.svg and "-env" in result.svg
    # Material drift: SMIL <animate> on x1/x2
    assert '<animate attributeName="x1"' in result.svg
    assert "6.854s" in result.svg  # phi3 cadence


def test_brutalist_seam_renders() -> None:
    result = compose(ComposeSpec(type="divider", genome_id="brutalist", divider_variant="seam"))
    assert result.width == 800
    assert result.height == 16
    # 13 line elements (5 horizontals + 8 perpendicular joint marks)
    assert result.svg.count("<line ") == 13
    # v0.3.2 visual review: celadon flagship accent migrated from base genome
    # emerald #10B981 to the prototype's muted-ceramic-green #48A870
    # (hw-elegant-mono-stat-cards.html celadon panel --a). The divider should
    # render with the new accent. Pre-fix this test pinned #10B981.
    assert "#48A870" in result.svg
    # v0.3.3 chromatic bleed fix: perpendicular joint marks track
    # accent_complement (variant-tonal pair, #78C898 for celadon), not
    # accent_signal which was inheriting the base-genome emerald #059669
    # across every light variant.
    assert "#78C898" in result.svg
    # Regression guard: the stale mint-green literal from the editorial
    # zeropoint template must never appear in brutalist-seam output.
    assert "#00ff94" not in result.svg
    assert "#059669" not in result.svg  # base-genome accent_signal must not bleed


# ── (slug, genome) pairing validator rejects mismatched combinations ──────


def test_band_on_brutalist_rejected() -> None:
    """band is chrome-only — brutalist.dividers does not include it."""
    with pytest.raises(ValueError) as exc_info:
        compose(ComposeSpec(type="divider", genome_id="brutalist", divider_variant="band"))
    assert "divider_variant" in str(exc_info.value)


def test_seam_on_chrome_rejected() -> None:
    """seam is brutalist-only — chrome.dividers does not include it."""
    with pytest.raises(ValueError) as exc_info:
        compose(ComposeSpec(type="divider", genome_id="chrome", divider_variant="seam"))
    assert "divider_variant" in str(exc_info.value)


def test_dissolve_on_chrome_rejected() -> None:
    """dissolve is automata-only — chrome.dividers does not include it."""
    with pytest.raises(ValueError) as exc_info:
        compose(ComposeSpec(type="divider", genome_id="chrome", divider_variant="dissolve"))
    assert "divider_variant" in str(exc_info.value)


# ── Editorial generics still render via the legacy template ───────────────
# (They're served at /a/inneraura/dividers/ in production but the resolver
# accepts them in any (slug, genome) pairing as backward-compat — only the
# compositor HTTP route blocks them.)


@pytest.mark.parametrize("slug", ["block", "current", "takeoff", "void", "zeropoint"])
def test_editorial_generic_still_renders_via_resolver(slug: str) -> None:
    """The resolver doesn't reject editorial slugs — only the HTTP route does.

    Editorial generics keep working through the compose pipeline so the
    /a/inneraura/dividers/ route can use compose() internally. The HTTP
    /v1/divider/ route is the layer that rejects them with the moved-header.
    """
    result = compose(ComposeSpec(type="divider", genome_id="brutalist", divider_variant=slug))
    assert "<svg" in result.svg


# ── v0.3.3 chromatic bleed fix — per-variant divider palette assertions ────
#
# Pre-v0.3.3 the brutalist-seam divider used accent_signal for perpendicular
# joint marks. Variant overrides intentionally inherit accent_signal (semantic
# state register — see compose/validate_paradigms.py:38) so every light variant
# rendered the base genome's mint-green #059669 ticks regardless of palette.
# The fix routes joint marks through accent_complement (variant-tonal pair) and
# adds the same discipline to the zeropoint editorial divider's aurora gradient
# + nexus beacon. These tests pin each variant's expected accents in the
# rendered SVG and assert the legacy literals never appear.


# (variant, accent, accent_complement) tuples — sourced verbatim from
# src/hyperweave/data/genomes/brutalist.json variant_overrides.
_BRUTALIST_DARK_VARIANTS: list[tuple[str, str, str]] = [
    ("celadon", "#48A870", "#78C898"),
    ("carbon", "#6E6888", "#A098B8"),
    ("alloy", "#3888B8", "#68B0D8"),
    ("temper", "#988870", "#C0B098"),
    ("pigment", "#9860A0", "#C090C8"),
    ("ember", "#C0A050", "#E0C878"),
]

_BRUTALIST_LIGHT_VARIANTS: list[tuple[str, str, str]] = [
    ("pulse", "#D4AF37", "#8B1A1A"),
    ("archive", "#A6CE39", "#5C4033"),
    ("depth", "#E07A2F", "#1A3A6B"),
    ("signal", "#2EC4A0", "#1A4A2E"),
    ("afterimage", "#00D4FF", "#2D1B69"),
    ("primer", "#E8A020", "#2A2D32"),
]


@pytest.mark.parametrize(
    ("variant_slug", "accent", "accent_complement"),
    _BRUTALIST_DARK_VARIANTS + _BRUTALIST_LIGHT_VARIANTS,
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_brutalist_seam_per_variant_chromatic_register(variant_slug: str, accent: str, accent_complement: str) -> None:
    """Each brutalist variant's seam divider must render its own accent +
    accent_complement and contain ZERO occurrences of the legacy mint-green
    literals that bled through pre-v0.3.3."""
    result = compose(
        ComposeSpec(
            type="divider",
            genome_id="brutalist",
            divider_variant="seam",
            variant=variant_slug,
        )
    )
    # Horizontal rule segments carry the variant's accent.
    assert accent in result.svg, f"brutalist-seam[{variant_slug}] missing accent {accent} — variant override not merged"
    # Perpendicular joint marks carry the variant's accent_complement.
    assert accent_complement in result.svg, (
        f"brutalist-seam[{variant_slug}] missing accent_complement {accent_complement} — "
        "joint marks not tracking variant tonal pair"
    )
    # The stale literals from divider.svg.j2 (zeropoint) must never appear.
    assert "#00ff94" not in result.svg
    # The base-genome accent_signal must never bleed into a variant.
    assert "#059669" not in result.svg.lower() and "#059669" not in result.svg


@pytest.mark.parametrize(
    ("variant_slug", "accent", "accent_complement"),
    _BRUTALIST_DARK_VARIANTS + _BRUTALIST_LIGHT_VARIANTS,
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_brutalist_zeropoint_per_variant_chromatic_register(
    variant_slug: str, accent: str, accent_complement: str
) -> None:
    """The zeropoint editorial divider's aurora + nexus must track variant
    accent/accent_complement when composed under a brutalist variant. Pre-v0.3.3
    the gradient + beacon were hardcoded mint-green regardless of palette."""
    result = compose(
        ComposeSpec(
            type="divider",
            genome_id="brutalist",
            divider_variant="zeropoint",
            variant=variant_slug,
        )
    )
    assert accent in result.svg, (
        f"zeropoint[{variant_slug}] missing accent {accent} — nexus + aurora-peak should render it"
    )
    assert accent_complement in result.svg, (
        f"zeropoint[{variant_slug}] missing accent_complement {accent_complement} — "
        "aurora halo should render it at stops 20%/80%"
    )
    # Stale literals from the pre-v0.3.3 hardcoded aurora must never appear.
    assert "#00ff94" not in result.svg
    assert "#0a0f1a" not in result.svg.lower()  # was hardcoded aurora endpoint + nexus inner


def test_zeropoint_divider_no_hardcoded_green_in_non_brutalist_dark_variant_genomes() -> None:
    """Generic regression guard: zeropoint composed under genomes whose accent
    is not in the emerald/mint family must contain ZERO occurrences of the
    pre-fix hardcoded green literals.

    Covers brutalist light variants + chrome variants. (Automata's bare genome
    has a teal accent #1E849A and never used the pre-fix literals; included
    for completeness.)"""
    forbidden_greens = ["#00ff94", "#10B981", "#34D399"]
    # Chrome variants — none of their accents are in the green family.
    for variant_slug in ("horizon", "abyssal", "lightning", "graphite", "moth"):
        # Chrome doesn't whitelist zeropoint in its `dividers` list, but the
        # resolver's _editorial_generics carve-out (resolver.py:1072) accepts
        # it for any genome. Per the existing
        # test_editorial_generic_still_renders_via_resolver, editorial generics
        # work everywhere through compose().
        result = compose(
            ComposeSpec(
                type="divider",
                genome_id="chrome",
                divider_variant="zeropoint",
                variant=variant_slug,
            )
        )
        for green in forbidden_greens:
            assert green not in result.svg, (
                f"chrome[{variant_slug}] zeropoint contains forbidden green {green} — chromatic bleed regression"
            )
    # Brutalist LIGHT variants only — dark variants legitimately include the
    # base-genome emerald via inheritance for non-chromatic-identity surfaces.
    for variant_slug, _, _ in _BRUTALIST_LIGHT_VARIANTS:
        result = compose(
            ComposeSpec(
                type="divider",
                genome_id="brutalist",
                divider_variant="zeropoint",
                variant=variant_slug,
            )
        )
        for green in forbidden_greens:
            # The "signal" variant's accent_complement is #1A4A2E (deep forest)
            # — not in forbidden_greens. The "archive" variant's accent #A6CE39
            # is yellow-green but distinct from all three forbidden literals.
            assert green not in result.svg, (
                f"brutalist[{variant_slug}] zeropoint contains forbidden green {green} — chromatic bleed regression"
            )
