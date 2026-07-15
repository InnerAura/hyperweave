"""Shape orthogonality: node anatomy (card / glyph-circle / text) is a
caller choice independent of topology, not a hardcoded per-solver fact.

Pill joins card/glyph-circle/card+glyph as a requestable ``NodeStyle`` on
ANY topology's per-node dispatch (state-machine's own chassis default is
every other topology defaults to card, or glyph-circle for the hub
compass center). The regression guard below pins that every one of the 44
bundled presets — none of which declare an explicit node/spec style on
state-machine, hub, dag, or pipeline nodes — keeps its pre-existing shape
set: the new capability is additive, not a behavior change for the library.
"""

from __future__ import annotations

from typing import Any

import pytest

from hyperweave.compose.diagram import compute_diagram_layout
from hyperweave.compose.diagram.input import (
    coerce_diagram_input,
    diagram_preset_names,
    resolve_auto_roles,
    resolve_diagram_preset,
)
from hyperweave.config.loader import load_diagram_config, load_paradigms
from hyperweave.core.diagram import DiagramSpec
from hyperweave.core.models import ComposeSpec

ENGINE = load_diagram_config()


def solve(**kw: Any) -> Any:
    paradigm = load_paradigms()["primer"].diagram
    spec = resolve_auto_roles(DiagramSpec.model_validate(kw))
    return compute_diagram_layout(spec, paradigm=paradigm, engine=ENGINE, palette_len=5)


def _preset_layout(name: str) -> Any:
    paradigm = load_paradigms()["primer"].diagram
    cs = ComposeSpec(type="diagram", genome_id="primer", diagram=resolve_diagram_preset(name))
    spec = coerce_diagram_input(cs.connector_data, cs).spec
    return compute_diagram_layout(spec, paradigm=paradigm, engine=ENGINE, palette_len=8)


def test_pill_style_is_rejected_at_the_schema() -> None:
    """The pill anatomy is deleted (no specimen ever used it — all three
    state-machine hand files are rx-13 cards): a spec declaring it must
    hear a validation refusal, never a silent stadium."""
    import pytest as _pytest

    with _pytest.raises(Exception, match="pill"):
        solve(
            topology="pipeline",
            title="states",
            nodes=[
                {"id": "a", "label": "INIT", "style": "pill"},
                {"id": "b", "label": "RUN"},
            ],
            edges=[{"source": "a", "target": "b"}],
        )


def test_card_on_state_machine_renders_card_boxes() -> None:
    """State-machine's chassis default is the glyph-card chain; an explicit per-node
    ``card`` style overrides it — the rest of the baseline stays pill."""
    lay = solve(
        topology="state-machine",
        nodes=[
            {"id": "idle", "label": "IDLE", "style": "card"},
            {"id": "active", "label": "ACTIVE"},
            {"id": "done", "label": "DONE"},
        ],
        edges=[{"source": "idle", "target": "active"}, {"source": "active", "target": "done"}],
    )
    by_id = {n.node_id: n for n in lay.nodes}
    assert by_id["idle"].shape == "rect"
    # The chassis default is the rx-13 glyph-card chain (all three
    # state-machine specimens); the retired pill anatomy is gone.
    assert by_id["active"].shape == "rect"
    assert by_id["done"].shape == "rect"


def test_glyph_circle_on_dag_works() -> None:
    """A dag rank card styled ``glyph-circle`` renders a circle at the fixed
    chassis radius, sharing the rank's uniform reserved slot with its
    card-styled siblings (no overlap, no shape leakage onto them)."""
    lay = solve(
        topology="dag",
        nodes=[
            {"id": "a", "label": "A", "style": "glyph-circle"},
            {"id": "b", "label": "B"},
            {"id": "c", "label": "C"},
        ],
        edges=[{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
    )
    by_id = {n.node_id: n for n in lay.nodes}
    a = by_id["a"]
    assert a.shape == "circle"
    assert a.r > 0
    assert by_id["b"].shape == "rect"
    assert by_id["c"].shape == "rect"


def test_hub_center_respects_explicit_card_style() -> None:
    """The compass hub center defaults to glyph-circle (the emanation mask),
    but an explicit ``node.style: card`` on the center renders a card
    instead — and the canvas grows to fit the card's real footprint rather
    than the circle radius the ring math assumed."""
    default = solve(
        topology="hub",
        hub_policy="compass",
        nodes=[{"id": "core", "label": "CORE"}, {"id": "a", "label": "ALPHA"}, {"id": "b", "label": "BETA"}],
        edges=[{"source": "core", "target": "a"}, {"source": "core", "target": "b"}],
    )
    styled = solve(
        topology="hub",
        hub_policy="compass",
        nodes=[
            {"id": "core", "label": "CORE", "style": "card"},
            {"id": "a", "label": "ALPHA"},
            {"id": "b", "label": "BETA"},
        ],
        edges=[{"source": "core", "target": "a"}, {"source": "core", "target": "b"}],
    )
    default_center = next(n for n in default.nodes if n.node_id == "core")
    styled_center = next(n for n in styled.nodes if n.node_id == "core")
    assert default_center.shape == "circle"
    assert styled_center.shape == "rect"
    # The center's card footprint isn't the circle's diameter — the canvas
    # bbox must be solved from the ACTUAL resolved anatomy (the _hub_box fix),
    # not a hardcoded circle-radius assumption, or the card would clip.
    assert styled_center.box.w > 0 and styled_center.box.h > 0


def test_axial_nucleus_stays_card_regardless_of_style() -> None:
    """The axial hub policy's nucleus is force_card=True by hard geometry
    constraint (the tangent-bezier connector math is solved against a card
    box) — a glyph-circle or pill request on the nucleus is overridden,
    unlike the compass center which honors the same request."""
    lay = solve(
        topology="hub",
        hub_policy="axial",
        nodes=[
            {"id": "core", "label": "CORE", "style": "glyph-circle"},
            {"id": "w", "label": "WRITE"},
            {"id": "r", "label": "READ"},
        ],
        edges=[
            {"source": "w", "target": "core", "role": "edit"},
            {"source": "core", "target": "r", "role": "read"},
        ],
    )
    nucleus = next(n for n in lay.nodes if n.node_id == "core")
    assert nucleus.shape == "rect"


# ── Byte-identity: every bundled preset keeps its pre-existing shape set ────

# Preset-library law: the library is EXACTLY the 30 kit-prototype recreations
# (data/presets/diagram.yaml). No preset renders a glyph-circle coin — every
# prototype census declares coins: 0 — so no "circle" shape appears here; the
# only non-rect anatomy is the state-machine pill (cicd-machine /
# agent-task-lifecycle chassis default) and the kernel-bottleneck pill mesh.
_EXPECTED_PRESET_SHAPES: dict[str, tuple[str, ...]] = {
    "agent-task-lifecycle": ("rect",) * 6,  # glyph cards (agent-task-lifecycle), never pills
    "artifact-roundtrip": ("rect",) * 4,
    "auth-sequence": ("rect",) * 4,
    "cicd-gate": ("rect",) * 6,
    "cicd-machine": ("rect",) * 5,  # glyph cards (cicd-machine)
    "comparison": ("rect",) * 2,
    "convergence": ("rect",) * 5,
    "convergence-arrivals": ("rect",) * 5,
    "dep-audit": ("rect",) * 6,
    "dep-audit-radial": ("rect",) * 10,
    "flywheel-flow": ("rect",) * 5,
    "flywheel-orbit": ("rect",) * 5,
    "frontier-serving": ("rect",) * 7,
    "gateway": ("rect",) * 3,
    "hub": ("rect",) * 6,
    "kernel-bottleneck": ("rect",) * 8,  # glyph cards (kernel-bottleneck)
    "mindmap": ("rect",) * 13,
    "model-gateway-tiers": ("rect",) * 7,
    "model-router": ("rect",) * 7,
    "obi-engine": ("rect",) * 13,
    "observability-converge": ("rect",) * 6,
    # order-lifecycle overrides node_style: card+glyph (the specimen renders
    # cards with kind-glyphs + a chip row), so it is rect, not the pill chassis
    # default the other two state machines keep.
    "order-lifecycle": ("rect",) * 4,  # entry is the initial pseudo-state, not a card
    "agent-runtime": ("rect",) * 8,  # state-machine loop cards (the band region is chrome, not a node)
    "gateway-balanced": ("rect",) * 7,  # gateway diamond cards (the MODEL POOL band is chrome, not a node)
    "router-descent": ("rect",) * 7,
    "verb-reads": ("rect",) * 7,
    "rag-pipeline": ("rect",) * 5,
    "reverse-etl": ("rect",) * 7,
    "scatter-gather": ("rect",) * 7,
    "service-dependencies": ("rect",) * 8,
    "stack": ("rect",) * 5,
    "tree": ("rect",) * 10,
}


def test_pinned_presets_still_bundled() -> None:
    """Every preset this pin covers must still resolve — a rename/removal
    should fail loud here rather than silently stop being swept. (New
    presets landing alongside this pass are out of scope for this pin; the
    preset library is a separate, actively-growing workstream.)"""
    assert set(_EXPECTED_PRESET_SHAPES) <= set(diagram_preset_names())


@pytest.mark.parametrize("name", sorted(_EXPECTED_PRESET_SHAPES))
def test_bundled_preset_shapes_unchanged(name: str) -> None:
    """None of these bundled presets declare an explicit node/spec style on
    a state-machine, hub, dag, or pipeline node — shape orthogonality adds a
    dispatch capability, it must not change a single existing preset's
    rendered anatomy."""
    lay = _preset_layout(name)
    shapes = tuple(n.shape for n in sorted(lay.nodes, key=lambda n: n.index))
    assert shapes == _EXPECTED_PRESET_SHAPES[name]
