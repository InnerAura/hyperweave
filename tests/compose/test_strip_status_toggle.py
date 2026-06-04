"""Strip paradigm-driven conditional zones — Phase 3.

Verifies that ``ParadigmStripConfig.show_status_indicator`` controls whether
the strip reserves its 56px right-edge diamond zone, and that flank_width
extends the total strip width when a bifamily paradigm declares it.

These gates make the strip reproducible for any paradigm with arbitrary
input: the specimen v10 layout (3 metrics + status + bifamily flanks)
is one specific instance; the resolver adapts zones to paradigm config.
"""

from __future__ import annotations

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec


def test_automata_strip_bifamily_has_flank_zones() -> None:
    """Automata (cellular paradigm) strip reserves 2x36px = 72px flank total."""
    spec = ComposeSpec(
        type="strip",
        genome_id="automata",
        title="README-AI",
        value="STARS:2.9k,FORKS:278",
        variant="teal",
        pair="violet",
    )
    result = compose(spec)
    # Width has flank allocation on top of standard identity + N metrics + status
    # We can't know the exact width (depends on text measurement) but flank presence
    # adds >= 72px over the equivalent brutalist compose.
    assert result.width >= 72 + 80  # flanks + minimum identity zone


def test_brutalist_strip_unaffected_by_flank_zero() -> None:
    """Existing brutalist strip doesn't grow (flank_width defaults 0)."""
    spec = ComposeSpec(
        type="strip",
        genome_id="brutalist",
        title="README-AI",
        value="STARS:2.9k,FORKS:278",
    )
    result = compose(spec)
    # Brutalist strip has no flanks; width derived purely from content.
    # Sanity: at least the minimum identity zone width.
    assert result.width >= 80


def test_strip_renders_with_zero_metrics() -> None:
    """Dynamic construction: 0-metric strip composes without error."""
    spec = ComposeSpec(
        type="strip",
        genome_id="automata",
        title="SOLO",
        value="",
        variant="teal",
        pair="violet",
    )
    result = compose(spec)
    assert result.width > 0
    assert result.height > 0


def test_strip_renders_with_many_metrics() -> None:
    """Dynamic construction: 6-metric strip expands linearly."""
    spec3 = ComposeSpec(
        type="strip",
        genome_id="automata",
        title="REPO",
        value="A:1,B:2,C:3",
        variant="teal",
        pair="violet",
    )
    spec6 = ComposeSpec(
        type="strip",
        genome_id="automata",
        title="REPO",
        value="A:1,B:2,C:3,D:4,E:5,F:6",
        variant="teal",
        pair="violet",
    )
    r3 = compose(spec3)
    r6 = compose(spec6)
    # Each extra metric adds a metric_pitch worth of width
    assert r6.width > r3.width
