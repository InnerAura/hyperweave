"""Frozen layout records for the diagram frame — the template seam.

Every coordinate, path ``d`` string, gradient stop, and animation timing is
precomputed by the solver package; templates do pure substitution
(compose-owns-geometry). ``NodePlacement.index`` preserves SPEC order for
projections while the ``DiagramLayout.nodes`` tuple is PAINT order (the hero
paints last on radial layouts so connector stubs are masked by the hub —
the emanation trick is data, not a template branch).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hyperweave.compose.spatial_records import LineSpec, RectSpec


@dataclass(frozen=True, slots=True)
class DiagramText:
    """One placed text run bound to a paradigm voice class."""

    x: float
    y: float
    text: str
    cls: str
    anchor: str = "start"


@dataclass(frozen=True, slots=True)
class GlyphArt:
    """Resolved glyph rendering for a node identity slot.

    Inherits the matrix glyph system wholesale: built by
    ``glyph_mark_placement`` (registry entry + tint selection, degrading
    full -> gradient -> brand -> ink), lifted into this record. ``paths``
    carries the matrix ``GlyphPath`` records (d + optional per-path fill
    for color_paths masters)."""

    paths: tuple[Any, ...] = ()
    transform: str = ""
    fill: str = ""
    opacity: float = 1.0
    fill_rule: str = ""
    gradient: str = ""
    """Glyph gradient id (uid-suffixed by the template) when the mark
    declares one and the resolved tint allows it."""
    tint: str = "ink"
    """Resolved (rendered) tint mode — recorded in the payload."""
    cx: float = 0.0
    cy: float = 0.0
    size: float = 0.0
    glyph_id: str = ""
    """The mark's anchor, size and registry id — kept so the contrast gate
    (G5) can rebuild the art at a degraded tint without re-deriving the slot."""


@dataclass(frozen=True, slots=True)
class NodePlacement:
    """One placed node: geometry + pre-truncated text runs."""

    index: int
    node_id: str
    shape: str  # rect | circle | pill
    box: RectSpec
    role: str  # default | hero | muted
    stroke_width: float
    stroke_dasharray: str  # "" | muted dash
    accent_index: int  # flow-palette slot; -1 = none/chassis accent
    label: DiagramText
    desc_lines: tuple[DiagramText, ...] = ()
    dot: tuple[float, float] | None = None
    dot_r: float = 4.0
    short: DiagramText | None = None
    tag: DiagramText | None = None
    """State-machine TERMINAL tag under the hero pill's name."""
    glyph: GlyphArt | None = None
    plate_fill: str = ""
    """Contrast-gate class treatment (G5 v3): 'none' (plateless — the mark
    sits on the paper) or a literal genome-plate hex shared by the whole
    glyph-circle class. Never varies per node within a class."""
    plate_ink: str = ""
    """Counter-ink for mono shorts riding a swapped plate — the sibling
    plate's fill, so ink-by-construction stays true on the plate."""
    cx: float = 0.0
    cy: float = 0.0
    r: float = 0.0
    """Circle geometry when shape == 'circle' (box still circumscribes)."""


@dataclass(frozen=True, slots=True)
class GradientStop:
    offset: float
    color: str
    opacity: float = 1.0


@dataclass(frozen=True, slots=True)
class GradientAnimate:
    """animateTransform on gradientTransform — transform-class CIM."""

    values: str
    keytimes: str = ""
    keysplines: str = ""
    dur: str = "2.6s"
    begin: str = ""
    calc_mode: str = ""


@dataclass(frozen=True, slots=True)
class GradientSpec:
    """One linearGradient the defs partial emits (uid-suffixed id)."""

    id_suffix: str
    x1: float
    y1: float
    x2: float
    y2: float
    stops: tuple[GradientStop, ...]
    spread: str = ""  # "" | repeat
    animate: GradientAnimate | None = None


@dataclass(frozen=True, slots=True)
class LightLayer:
    """One stroked overlay a beam/flow edge paints above its tube."""

    kind: str  # halo | core | filament
    gradient_ref: str  # GradientSpec.id_suffix
    width: float
    opacity: float = 1.0
    blur: bool = False


@dataclass(frozen=True, slots=True)
class ConnectorPlacement:
    """One edge: the path plus its resolved motion/track treatment."""

    index: int
    path_d: str
    source_index: int
    target_index: int
    accent_index: int  # -1 -> chassis accent
    motion: str  # concrete post-ladder: dash | particle | beam | flow
    track: str  # static | dash-march | none (none = motion IS the stroke)
    ant_delay: str = ""
    semantic_dash: str = ""
    """Meaning-bearing dasharray (sequence return, muted) — overrides the
    track pattern; P3: its presence already resolved the track static."""
    static_dash: str = ""
    """The dasharray a static-track stroke stamps ('' = solid): the
    semantic dash, or the default dash for inert edges."""
    label: DiagramText | None = None
    light_layers: tuple[LightLayer, ...] = ()
    length: float = 0.0
    lane: int = 0
    """0 single; +1/-1 reciprocal parallel lanes (offset applied in path_d)."""
    inert: bool = False


@dataclass(frozen=True, slots=True)
class ParticlePlacement:
    """One animateMotion rider over a connector's path."""

    connector_index: int
    accent_index: int
    r: float
    dur: str
    begin: str = ""
    opacity_values: str = "0;.85;.85;0"
    opacity_keytimes: str = "0;.12;.88;1"
    keypoints: str = ""
    keytimes_motion: str = ""
    calc_mode: str = ""


@dataclass(frozen=True, slots=True)
class DiagramHeader:
    title: DiagramText | None = None
    subtitle: DiagramText | None = None


@dataclass(frozen=True, slots=True)
class RenderedMotion:
    """Requested vs rendered — recorded in the payload so a fallback or a
    track resolution never silently diverges from what the caller asked."""

    edge_motion: tuple[str, ...]
    track: tuple[str, ...]
    glyph_tint: tuple[str, ...]
    performance: str  # paint-ok | composite-only
    fallback_applied: bool
    glyph_backing: tuple[str, ...] = ()
    """Per-node contrast-gate outcome (G5): '' (no mark) | default |
    exempt-ink | plate-light | plate-dark | tint-<mode>."""


@dataclass(frozen=True, slots=True)
class DiagramLayout:
    """The frozen solve — everything a template stamps, nothing it computes."""

    width: int
    height: int
    display_w: int
    display_h: int
    layout_slug: str
    aspect: str
    header: DiagramHeader
    nodes: tuple[NodePlacement, ...]
    connectors: tuple[ConnectorPlacement, ...]
    particles: tuple[ParticlePlacement, ...]
    gradients: tuple[GradientSpec, ...] = ()
    operators: tuple[DiagramText, ...] = ()
    lifelines: tuple[LineSpec, ...] = ()
    activations: tuple[RectSpec, ...] = ()
    legend: DiagramText | None = None
    initial_dot: tuple[float, float] | None = None
    initial_dot_r: float = 4.0
    initial_stub: LineSpec | None = None
    footer: DiagramText | None = None
    palette_slots: int = 0
    entrance: str = "none"
    rendered: RenderedMotion = field(
        default_factory=lambda: RenderedMotion(
            edge_motion=(), track=(), glyph_tint=(), performance="composite-only", fallback_applied=False
        )
    )
