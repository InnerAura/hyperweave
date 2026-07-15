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
    stroke_w: float = 0.0
    """Stroke-icon channel: >0 paints paths as strokes (core glyph set)."""
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
    accent_index: int = -1
    """This node's flow-palette slot when ``tint == "hue"`` (-1 otherwise) —
    the index the template's ``-fl{i}``/``-flp{i}`` class binds to."""


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
    term_box: RectSpec | None = None
    """Terminal double-ring aspect: the hairline accent rect floating just
    outside a final state's card (agent-task-lifecycle's done)."""
    dot_r: float = 4.0
    dot_shape: str = "disc"
    card_accent: bool = False
    """Lanes convergence-hub accent (the obi-engine specimen): the card
    border and the category mark take the signal stroke at NORMAL card size
    — the ONE accent in the swimlane, never a hero enlargement."""
    """disc | ring | diamond | square — the lanes category-by-SHAPE mark
    (obi-engine, morphology idiom). 'disc' (a plain filled circle) is the
    default so every OTHER topology's ``dot`` renders byte-identically to
    before this field existed."""
    dot_path: str = ""
    """Precomputed drawn-geometry ``d`` string for a non-circle dot_shape
    (diamond/square); '' for disc/ring, which stamp as a plain ``<circle>``."""
    health: str = ""
    """'' | outdated | vulnerable — the dependency-audit health channel
    (DiagramNode.health passed through). A SEPARATE mark from dot/dot_shape
    above (lanes category morphology, leading-corner, ink-toned): the health
    dot lives at the trailing corner, state-palette colored, and the two
    systems compose independently on the same card."""
    health_dot: tuple[float, float] | None = None
    """Precomputed health-dot center (card.x+w-inset_x, card.y+inset_y —
    engine ``health:`` block); None when health == ''."""
    short: DiagramText | None = None
    tag: DiagramText | None = None
    """State-machine TERMINAL tag under the hero pill's name."""
    glyph: GlyphArt | None = None
    cx: float = 0.0
    cy: float = 0.0
    r: float = 0.0
    """Circle geometry when shape == 'circle' (box still circumscribes)."""
    embed_box: RectSpec | None = None
    """sec 12.1: where the nested inner artifact's svg stamps (display box,
    card-content coordinates). The template pairs it with embed_markup."""
    chip_boxes: tuple[RectSpec, ...] = ()
    """Chip-row pill rects (chrome vocabulary; empty when no chips)."""
    chip_texts: tuple[DiagramText, ...] = ()
    label_accent: bool = False
    """Title carries the accent hue — the hub/axial accent-zone only (the
    hub DESTINATIONS binding). Everywhere else titles stay ink
    even when the node holds an accent slot (lanes category swatches)."""


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
class BeamGradient:
    """One window of the gradient-window beam: a userSpaceOnUse
    linearGradient carrying the fixed blue/purple comet (body) or its
    accent-deep front, ``gradientTransform`` translated one run + window per
    relay cycle (transform-class CIM; geometry never moves). No
    ``spreadMethod`` (pad) + true-zero end stops keep the sweep a single
    comet, never a barber-pole (the beam references' law). Identity is held
    blue/purple across every variant, never genome-derived."""

    id_suffix: str
    x1: float
    y1: float
    x2: float
    y2: float
    stops: tuple[GradientStop, ...]
    animate: GradientAnimate
    spread: str = ""
    """spreadMethod attribute; '' omits it (SVG default pad — the specimen
    recipe). 'repeat' was the barber-pole bug."""


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
    march_dash: str = ""
    """Per-connector MARCHING dasharray override ('' falls back to the
    artifact-wide diagram_style.dash): reciprocal-lane dress (the gateway
    v4 specimen's longer 5-7 texture) — the marching-track counterpart of
    ``static_dash``, gated by ``mo.lane_dress_applies`` in wiring.py."""
    marker_d: str = ""
    """Drawn end-marker path (a chevron), stamped at the connector's target
    end. Empty when the edge carries no marker (the default everywhere). The
    connector grammar (route.py) fills it; never a ``<marker>`` element —
    markers are drawn geometry, matching the direction_device doctrine."""
    length: float = 0.0
    lane: int = 0
    """0 single; +1/-1 reciprocal parallel lanes (offset applied in path_d)."""
    inert: bool = False
    accent_wire: bool = False
    """Role-bound accent stroke (§11.4b): keeps the hue class even under the
    muted-connector default — the axial destination fan's dress."""
    relation: str = ""
    """The §3 line idiom this wire renders ('' | assert | drift | flow |
    bypass) — resolved from the edge or the solver's axis default. A
    relation's terminal is MEANING, exempt from the ornament-free default."""
    beam: tuple[BeamGradient, ...] = ()
    """The gradient-window beam paint (motion == 'beam'): exactly (body,
    front) — the blue/purple window and its narrower accent-deep comet
    front, sharing one GradientAnimate (byte-identical animate blocks, per
    the beam reference specimens). Empty on every other motion — the connector renders
    its plain track."""


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
    path_override: str = ""
    """A raw ``d``-string the rider follows directly (inline ``path=``,
    specimen-true) instead of an ``<mpath>`` reference to ``connector_index``
    — the flywheel rim orbit's continuous full-loop path, which traces every
    arc's shared radius as ONE closed curve with no counterpart connector to
    reference. '' (the common case) keeps the existing mpath-to-connector
    wiring untouched."""


@dataclass(frozen=True, slots=True)
class LegendEntry:
    """One row of a legend annotation: an accent swatch plus its label."""

    swatch_x: float
    swatch_y: float
    swatch_r: float
    accent_index: int
    """Flow-palette slot for the swatch (-1 = chassis accent)."""
    text: DiagramText
    swatch_shape: str = ""
    """'' | disc | ring | diamond | square. '' is the pre-existing
    accent-colored circle (byte-identical everywhere this ships today); a
    non-empty value opts into the lanes morphology idiom — an INK-toned mark
    (never hue) mirroring NodePlacement.dot_shape, so a legend swatch draws
    the SAME mark its category's node dots carry."""
    swatch_path: str = ""
    """Precomputed ``d`` string for a non-circle swatch_shape; '' for disc/ring."""
    health: str = ""
    """'' | outdated | vulnerable — DiagramAnnotation.health passed through.
    Non-empty overrides accent_index: the swatch renders state-palette
    colored (the SAME class the card health dots use), never a flow hue."""


@dataclass(frozen=True, slots=True)
class AnnotationPlacement:
    """One placed annotation — the frozen result of the annotate pass.

    ``kind`` selects the template's rendering (callout box + leader, badge
    aside box, legend column, or a bare ``label`` — a subsumed
    edge label, chrome-free text runs). Only the fields the kind uses are
    populated; the rest keep their empty defaults so the template branches on
    presence, never on kind string equality."""

    kind: str  # label | callout | legend | aside | badge | pin
    lines: tuple[DiagramText, ...] = ()
    """Wrapped text runs (callout, aside, badge). Empty for pin."""
    leader: str = ""
    """Leader path ``d`` from the box to the anchor (callout). '' = none."""
    box: RectSpec | None = None
    """Backing rect (callout, aside, badge pill, legend panel)."""
    dot: tuple[float, float] | None = None
    """Pin dot center."""
    dot_r: float = 4.0
    entries: tuple[LegendEntry, ...] = ()
    """Legend rows (legend kind only)."""
    accent_index: int = -1
    """Chrome accent slot (-1 = chassis accent)."""
    region: str = ""
    """The region this placement was requested for (legend kind) — the §2
    region engine relocates header/footer legends into their stacked rows."""
    anchor: str = ""
    """Horizontal corner hint for a header-region legend COLUMN ('' | left —
    legend kind only): the masthead stamping step (solver.py) right-anchors
    a header legend by default (dep-audit's cited hand file) unless this
    reads 'left' (dep-audit-radial's cited hand file, flush under the
    kicker) — set once, at the same placement:left source that also picks
    the column's own relative geometry (chrome_kinds._place_legend_column),
    so the two never disagree."""
    lane_dress: bool = False
    """True ONLY for a bare ``label`` subsumed from a ``mo.lane_dress_applies``
    edge (the gateway specimen's request/response text) — the one case a
    'label'-kind text run may carry ``accent_index`` color. Every other
    label and every edge-chip stays neutral ink regardless of accent_index
    (P5 chip contract: chip text never rides the accent/flow hue)."""


@dataclass(frozen=True, slots=True)
class LaneBand:
    """A labeled region box: a lanes category band, or a state-machine
    compound enclosure (ground='enclosure' — the hairline common-region
    piece, agent-task-lifecycle's RECOVERY)."""

    box: RectSpec
    """The band's full extent (the region the lane's nodes occupy)."""
    header: DiagramText
    count: DiagramText | None = None
    """Optional member-count badge text."""
    accent_index: int = -1
    """Palette slot shared by the band, its nodes' dots, and its legend row."""
    ground: str = "panel"
    """D1 ground treatment: 'panel' draws the contained band rect;
    'typographic' dissolves it — header + count + one hairline rule, with
    grouping carried by alignment and proximity (the flagship look)."""
    rule: LineSpec | None = None
    """D2: the hairline rule under the header, spanning exactly the card
    column (typographic ground only)."""


@dataclass(frozen=True, slots=True)
class OperatorMark:
    """A stack topology's inter-layer compose operator (stack): a
    quiet ring + cross between two composing layers — drawn geometry, never
    a floating character glyph (a font's multiply sign varies weight/baseline
    across faces; a font-absent symbol can't be mono-triggered either). The
    ring reuses the card surface class; the cross rides the muted-connector
    tone, matching the plain wires it sits between."""

    cx: float
    cy: float
    r: float
    cross_d: str
    """Precomputed 'M..L.. M..L..' cross path, already sized to ``r`` —
    compose owns the geometry, the template only stamps it."""


@dataclass(frozen=True, slots=True)
class GatherPoint:
    """The gather-fan ornament: a quiet ring + accent core marking a
    structural one-to-many junction — >=2 live edges leaving the focal node
    from ONE shared point (the router trunk, the axial gather). Radii and
    pulse timing are chrome constants (diagram_style), not geometry."""

    x: float
    y: float
    clip_shape: str = ""
    """'' (mid-air trunk knot — draws the full ring) | 'rect' | 'circle': the
    boundary figure of the node the seat sits on. A seat ON a node's
    boundary needs the ring geometrically clipped to the boundary's outside
    (paint order alone only hides the inward half on an opaque card, never a
    bare-ring circle node or a containerless text satellite)."""
    clip_path_d: str = ""
    """Precomputed single-path evenodd clip data (empty when clip_shape ==
    ''): the canvas-frame subpath, then the node's own boundary-figure
    subpath (rect/rounded-rect corners, or a two-arc circle). SVG unions
    multiple sibling shapes inside one <clipPath> — it never subtracts — so
    an inverse clip must be ONE path, two subpaths, one evenodd fill-rule;
    compose owns that geometry, the template only stamps ``d``."""


@dataclass(frozen=True, slots=True)
class WireLegendEntry:
    """One row of the sequence call/return mini-legend (auth-sequence,
    top-right chrome): a short drawn wire stub + its terminal marker + label
    — the connector vocabulary itself as its own legend swatch (a circular
    swatch would lie about what a call/return actually looks like). ``accent``
    selects the SAME hue class a real message of that kind renders (accent
    for return, the muted/neutral class for call — the template computes
    the exact same ternary the connector loop uses); ``drift`` mirrors the
    live return-message dash-drift animation so the preview reads in motion
    too. Independent of ``connectors`` (decorative, never an edge) so it
    never perturbs the payload's per-edge ``RenderedMotion``."""

    stub_d: str
    marker_d: str
    accent: bool
    drift: bool
    label: DiagramText


@dataclass(frozen=True, slots=True)
class TimeAxis:
    """The sequence time-axis micro-furniture (auth-sequence): a short arrow
    at the left margin plus a 'time' label, roughly mid-trace — orienting a
    reader unfamiliar with the top-down replay convention."""

    stub_d: str
    marker_d: str
    label: DiagramText


@dataclass(frozen=True, slots=True)
class DiagramHeader:
    """Masthead texts with FINAL canvas coordinates (region-stacked — §2:
    no fixed y anywhere in chrome). ``title_lines`` carries the wrapped
    title (wrap-before-truncate); ``title`` mirrors the first line
    for back-compat readers."""

    title: DiagramText | None = None
    subtitle: DiagramText | None = None
    title_lines: tuple[DiagramText, ...] = ()


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
    plateless | exempt-ink | tint-<mode>. 'default' is a card/pill mark that
    reads on its own card surface; 'plateless' is a bare circle mark reading
    directly on the paper — neither shape ever repaints a backing."""
    warnings: tuple[str, ...] = ()
    """Normalization warnings (e.g. cyclic-dag promotion). Surfaced on the
    payload's ``rendered.warnings`` ONLY when non-empty (byte-stability) and
    on the caller's stderr. Empty for the common path."""


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
    operators: tuple[OperatorMark, ...] = ()
    lifelines: tuple[LineSpec, ...] = ()
    activations: tuple[RectSpec, ...] = ()
    hero_lifeline_index: int = -1
    """Index into ``lifelines`` the protagonist owns (sequence only); -1 when
    the spec declares no hero. Drives the accent-tinted dashed lifeline."""
    hero_activation_index: int = -1
    """Index into ``activations`` the protagonist owns (sequence only); -1
    when no hero, or the hero never touches a message."""
    time_axis: TimeAxis | None = None
    """Sequence time-axis micro-furniture; None on every other topology."""
    wire_legend: tuple[WireLegendEntry, ...] = ()
    """Sequence call/return mini-legend rows; empty when the trace has no
    return message, or on every other topology."""
    annotations: tuple[AnnotationPlacement, ...] = ()
    """Placed caller annotations (the annotate pass fills these; empty until
    that slice lands)."""
    lane_bands: tuple[LaneBand, ...] = ()
    """Lanes-topology category bands (the lanes solver fills these)."""
    gathers: tuple[GatherPoint, ...] = ()
    """Gather-fan ornaments at structural one-to-many junctions."""
    legend: DiagramText | None = None
    initial_dot: tuple[float, float] | None = None
    initial_dot_r: float = 4.0
    initial_stub: LineSpec | None = None
    regions: tuple[Any, ...] = ()
    """§2 region map (RegionBox tuple) — the artifact's public anatomy:
    serialized to <g data-hw-region> groups and the payload region map."""
    footer: DiagramText | None = None
    palette_slots: int = 0
    entrance: str = "none"
    rendered: RenderedMotion = field(
        default_factory=lambda: RenderedMotion(
            edge_motion=(), track=(), glyph_tint=(), performance="composite-only", fallback_applied=False
        )
    )
