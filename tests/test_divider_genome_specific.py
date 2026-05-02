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
    # Genome accent emerald
    assert "#10B981" in result.svg


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
