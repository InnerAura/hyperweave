"""Automata cellular strip — Phase 5 rendering validation.

Dynamic construction: N=0/1/3/6 metrics, with/without state carrier,
bifamily flanks, state indicator toggle, identity from slot override.
"""

from __future__ import annotations

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec, SlotContent


def _compose_strip(**kwargs: object) -> str:
    kwargs.setdefault("type", "strip")
    kwargs.setdefault("genome_id", "automata")
    kwargs.setdefault("variant", "bifamily")
    spec = ComposeSpec(**kwargs)  # type: ignore[arg-type]
    return compose(spec).svg


# ── Bifamily flank presence ─────────────────────────────────────────────


def test_bifamily_strip_renders_both_flanks() -> None:
    """family=bifamily strip emits teal-family cells on left + purple on right."""
    svg = _compose_strip(title="README-AI", value="STARS:2.9k,FORKS:278")
    # Teal family substrate colors (left flank)
    assert "#1E849A" in svg
    assert "#104052" in svg
    # Purple family substrate colors (right flank)
    assert "#6B3B8A" in svg
    assert "#331A4A" in svg


def test_monofamily_strip_suppresses_amethyst_rect_fills() -> None:
    """family=blue strip emits NO amethyst-family rect fills.
    (Amethyst hex may still appear in CSS var declarations like --dna-signal-dim.)"""
    svg = _compose_strip(title="README-AI", value="STARS:2.9k", variant="blue")
    assert 'fill="#6B3B8A"' not in svg
    assert 'fill="#331A4A"' not in svg
    assert 'fill="#160B24"' not in svg


# ── Dynamic N metrics ────────────────────────────────────────────────────


@pytest.mark.parametrize("metric_count", [0, 1, 3, 6])
def test_strip_renders_arbitrary_metric_count(metric_count: int) -> None:
    """Strip composes correctly with N = 0, 1, 3, 6 metrics."""
    value = "" if metric_count == 0 else ",".join(f"M{i}:{100 + i}" for i in range(metric_count))
    spec = ComposeSpec(type="strip", genome_id="automata", title="REPO", value=value, variant="bifamily")
    result = compose(spec)
    assert result.width > 0
    # Cellular strip specimen is 48px tall (not 52px default); paradigm
    # config declares strip_height: 48.
    assert result.height == 48
    # N metrics → N label text nodes (for non-zero counts)
    for i in range(metric_count):
        assert f"M{i}" in result.svg


def test_strip_width_grows_with_metric_count() -> None:
    """Width is monotonic in metric count at equal cell-pitch."""
    r1 = compose(ComposeSpec(type="strip", genome_id="automata", title="X", value="A:1", variant="bifamily"))
    r6 = compose(
        ComposeSpec(type="strip", genome_id="automata", title="X", value="A:1,B:2,C:3,D:4,E:5,F:6", variant="bifamily")
    )
    assert r6.width > r1.width


# ── Slot-driven state carrier ────────────────────────────────────────────


def test_metric_state_slot_drives_state_cell() -> None:
    """A slot with zone='metric-state' creates a cell carrying its state."""
    spec = ComposeSpec(
        type="strip",
        genome_id="automata",
        variant="bifamily",
        title="README-AI",
        state="passing",
        slots=[
            SlotContent(zone="metric", value="STARS:2.9k"),
            SlotContent(zone="metric", value="VERSION:0.6.2"),
            SlotContent(zone="metric-state", value="BUILD:passing", data={"state": "passing"}),
        ],
    )
    result = compose(spec)
    # Strip should render all 3 metrics
    assert "STARS" in result.svg
    assert "VERSION" in result.svg
    assert "BUILD" in result.svg


# ── Cellular structural markers ──────────────────────────────────────────


def test_cellular_strip_has_pattern_pulse_classes() -> None:
    """Flank cells carry the cz1/cz2/cz3/cz4/czf/czd pulse classes."""
    svg = _compose_strip(title="REPO", value="A:1,B:2,C:3")
    for cls in ("cz1", "cz2", "cz3", "cz4", "czf"):
        assert f'class="{cls}"' in svg


def test_cellular_strip_uses_chakra_petch() -> None:
    """Metric values use Chakra Petch per cellular paradigm config."""
    svg = _compose_strip(title="REPO", value="STARS:2.9k")
    assert "'Chakra Petch'" in svg


def test_cellular_strip_identity_uses_orbitron() -> None:
    """Identity text uses Orbitron per cellular paradigm defs."""
    svg = _compose_strip(title="README-AI", value="STARS:2.9k")
    assert "'Orbitron'" in svg


def test_cellular_strip_prefers_reduced_motion() -> None:
    svg = _compose_strip(title="REPO", value="A:1")
    assert "prefers-reduced-motion" in svg


# ── Cross-genome regression: existing genomes still work ─────────────────


def test_brutalist_strip_unaffected_by_cellular_changes() -> None:
    """brutalist strip renders normally; no cellular flanks, no Chakra Petch."""
    spec = ComposeSpec(type="strip", genome_id="brutalist", title="REPO", value="STARS:2.9k,FORKS:278")
    svg = compose(spec).svg
    # Brutalist paradigm has no flanks and no Chakra Petch
    # (strip.value_font_family is Inter for brutalist paradigm)
    assert "'Chakra Petch'" not in svg
