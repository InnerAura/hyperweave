"""Tests for paradigm dispatch mechanism (Session 2A+2B, Principle 26).

Covers:
- ComposeSpec.genome_override field plumbs custom genomes through the frozen spec
- ComposeSpec.genome_id accepts arbitrary slugs (enum relaxation)
- _load_genome(id, override=dict) returns override verbatim
- _resolve_paradigm() helper returns correct slug from genome.paradigms dict
- compose() with genome_override produces SVG using override's DNA, not registry
- Every frame_context now carries `paradigm` and `structural` keys
"""

from __future__ import annotations

import pytest

from hyperweave.compose.engine import compose
from hyperweave.compose.resolver import _load_genome, _resolve_paradigm, resolve
from hyperweave.core.models import ComposeSpec


@pytest.fixture()
def minimal_genome_override() -> dict[str, object]:
    """A minimal but valid genome dict for override testing.

    Not validated by GenomeSpec here — the resolver trusts upstream.
    The CLI path validates via GenomeSpec before passing as override.
    """
    return {
        "id": "inline-test",
        "name": "Inline Test",
        "category": "dark",
        "profile": "brutalist",
        "surface_0": "#111111",
        "surface_1": "#1A1A1A",
        "surface_2": "#0A0A0A",
        "ink": "#FFFFFF",
        "ink_secondary": "#CCCCCC",
        "ink_on_accent": "#000000",
        "accent": "#FF00FF",
        "accent_complement": "#CC00CC",
        "accent_signal": "#00FF00",
        "accent_warning": "#FFAA00",
        "accent_error": "#FF0000",
        "stroke": "#333333",
        "shadow_color": "#000000",
        "shadow_opacity": "0.3",
        "glow": "0px",
        "corner": "0",
        "rhythm_base": "2s",
        "density": "0.7",
        "compatible_motions": ["static"],
        "paradigms": {
            "badge": "default",
            "stats": "brutalist",
            "chart": "brutalist",
        },
        "structural": {
            "stroke_linejoin": "miter",
            "data_point_shape": "square",
        },
    }


# ============================================================================
# ComposeSpec accepts custom slugs + genome_override
# ============================================================================


def test_compose_spec_accepts_custom_genome_slug() -> None:
    """genome_id relaxed from GenomeId StrEnum to str — custom slugs allowed."""
    spec = ComposeSpec(type="badge", genome_id="my-custom-slug")
    assert spec.genome_id == "my-custom-slug"
    # Profile resolution falls through to brutalist default for unknown slug.
    assert spec.profile_id == "brutalist"


def test_compose_spec_genome_override_sets_profile_from_dict(
    minimal_genome_override: dict[str, object],
) -> None:
    """When genome_override contains a profile field, it wins over registry fallback."""
    spec = ComposeSpec(
        type="badge",
        genome_id="inline-test",
        genome_override=minimal_genome_override,
    )
    # genome_override.profile = "brutalist" → model_validator picks it up.
    assert spec.profile_id == "brutalist"
    assert spec.genome_override is not None
    assert spec.genome_override["accent"] == "#FF00FF"


def test_compose_spec_connector_data_field() -> None:
    """connector_data is a generic dict slot for pre-fetched external data."""
    spec = ComposeSpec(
        type="stats",
        stats_username="eli64s",
        connector_data={"stars_total": 12847, "commits_total": 1203},
    )
    assert spec.connector_data is not None
    assert spec.connector_data["stars_total"] == 12847


# ============================================================================
# _load_genome override path
# ============================================================================


def test_load_genome_returns_override_verbatim(
    minimal_genome_override: dict[str, object],
) -> None:
    """_load_genome(slug, override=dict) returns override without touching registry."""
    result = _load_genome("any-slug-at-all", override=minimal_genome_override)
    assert result is minimal_genome_override
    assert result["id"] == "inline-test"
    assert result["accent"] == "#FF00FF"


def test_load_genome_falls_back_to_registry_without_override() -> None:
    """Without override, _load_genome queries the built-in registry."""
    result = _load_genome("brutalist-emerald")
    assert result["id"] == "brutalist-emerald"
    assert result["accent"] == "#10B981"  # brutalist-emerald accent from JSON


def test_load_genome_raises_for_unknown_slug() -> None:
    """Unknown slug raises GenomeNotFoundError so the HTTP layer can map to 404.

    The previous behavior silently substituted a default genome dict, which
    masked broken URLs as successful renders. The HTTP layer now classifies
    this exception via :func:`_classify_compose_exception` and returns the
    SMPTE NO SIGNAL fallback badge with an ``ERR_404`` value slab.
    """
    from hyperweave.compose.resolver import GenomeNotFoundError

    with pytest.raises(GenomeNotFoundError) as excinfo:
        _load_genome("definitely-not-a-real-genome")
    assert excinfo.value.genome_id == "definitely-not-a-real-genome"
    # Backward-compat: GenomeNotFoundError inherits from KeyError, so
    # legacy callers that catch KeyError still catch the new exception.
    assert isinstance(excinfo.value, KeyError)


# ============================================================================
# _resolve_paradigm helper
# ============================================================================


def test_resolve_paradigm_reads_declared_slug() -> None:
    """_resolve_paradigm pulls from genome['paradigms'][frame_type]."""
    genome = {"paradigms": {"badge": "chrome", "stats": "chrome"}}
    assert _resolve_paradigm(genome, "badge") == "chrome"
    assert _resolve_paradigm(genome, "stats") == "chrome"


def test_resolve_paradigm_defaults_when_missing() -> None:
    """Missing frame_type key → returns the 'default' argument."""
    genome = {"paradigms": {"badge": "chrome"}}
    assert _resolve_paradigm(genome, "timeline") == "default"
    assert _resolve_paradigm(genome, "chart", default="brutalist") == "brutalist"


def test_resolve_paradigm_handles_missing_paradigms_dict() -> None:
    """Genome without paradigms dict → returns default."""
    assert _resolve_paradigm({}, "badge") == "default"
    assert _resolve_paradigm({"paradigms": None}, "badge") == "default"


# ============================================================================
# End-to-end: compose() with genome_override
# ============================================================================


def test_compose_with_override_produces_svg(
    minimal_genome_override: dict[str, object],
) -> None:
    """compose() using genome_override should render a valid SVG with override's accent color."""
    spec = ComposeSpec(
        type="badge",
        genome_id="inline-test",
        genome_override=minimal_genome_override,
        title="BUILD",
        value="passing",
    )
    result = compose(spec)
    assert "<svg" in result.svg
    assert "</svg>" in result.svg
    # The override's accent (#FF00FF magenta) should appear in the generated CSS
    # as a --dna-signal value, proving override wins over registry.
    assert "#FF00FF" in result.svg or "#ff00ff" in result.svg


def test_resolve_injects_paradigm_context() -> None:
    """Every frame_context now carries `paradigm` and `structural` keys (Phase 2)."""
    spec = ComposeSpec(type="badge", title="BUILD", value="passing")
    resolved = resolve(spec)
    assert "paradigm" in resolved.frame_context
    assert "structural" in resolved.frame_context
    # brutalist-emerald declares paradigms.badge = "default"
    assert resolved.frame_context["paradigm"] == "default"
    # brutalist-emerald.structural.stroke_linejoin = "miter"
    assert resolved.frame_context["structural"].get("stroke_linejoin") == "miter"


def test_resolve_paradigm_differs_between_genomes() -> None:
    """brutalist-emerald.stats = brutalist; chrome-horizon.stats = chrome."""
    br = resolve(ComposeSpec(type="badge", genome_id="brutalist-emerald"))
    ch = resolve(ComposeSpec(type="badge", genome_id="chrome-horizon"))
    # Badge paradigms: brutalist-emerald = "default", chrome-horizon = "chrome"
    assert br.frame_context["paradigm"] == "default"
    assert ch.frame_context["paradigm"] == "chrome"
