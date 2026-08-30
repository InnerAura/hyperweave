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
    signal: bool = False
    """The crown identity mark rides the SIGNAL tone (``-fls``/``-flps``)
    instead of its resolved ink — decided at placement (the card+label hero
    register's id-row mark, the same accent promotion the hub nucleus glyph
    gets), so the template stamps it and never re-derives the rule."""
    comp: bool = False
    """The mark rides the COMPLEMENT tone (``-flcomp``) — the loop's
    discard-partition glyph hue (turn/cycle-turn-choreography's ``cyt1-gC``
    undo-arc on the revert card, wire-grade complement like the discard
    exit it echoes). Stroke-drawn core marks only; decided at placement."""


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
    label_lines: tuple[DiagramText, ...] = ()
    """Wrapped-NAME lines 2..n (``label_max_lines`` > 1) — same voice and
    column as ``label``, one desc-pitch apart (the corpus's two-line station
    names: turn/cycle-turn-choreography-v2 at 533/552). Empty everywhere the
    single-line name law holds."""
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
    card_dress: str = ""
    """Dedicated card-fill class suffix ('' = role dispatch): the loop
    family's terminal washes — advance terminals wear the signal wash with
    a signal-edge rim, exhausted terminals the flat page tone (the corpus
    -term / -flat finishes; chromatic gestalt is dress, never a new shape)."""
    shape_d: str = ""
    """Precomputed outline ``d`` when ``shape == 'diamond'`` (the loop
    family's decision rhombus) — the template stamps a ``<path>`` with the
    card classes instead of a rect. ``box`` still circumscribes (N/E/S/W
    vertices at the box's edge midpoints by construction), so collision and
    port math read the same record every rect reads."""


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
    track: str  # static | dash-march | ring-drift | none (none = motion IS the stroke)
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
    ink_wire: bool = False
    """Partition-pair chromatics: this wire belongs to the NEUTRAL group of a
    declared binary partition, so it strokes ``--dna-ink-primary`` instead of
    the signal ``-fls`` default — the same ink/signal pair the two zone
    headers already compile (``zoneh``/``zoneha``). The accent group needs no
    flag: its members carry an ``accent_index`` and take the flow hue, which
    resolves to the signal."""
    comp_wire: bool = False
    """Loop discard/revert dress: this wire (and its marker) strokes the
    genome's ``diagram_complement`` — wire-grade only, the anchor's law
    (edges and markers, never text or frames). Mirrors ``ink_wire``'s
    mechanics on its own ``-flcomp``/``-flcompf`` classes."""
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
    edge_index: int = -1
    """The resolved-edge index an ``edge-chip`` placement was subsumed FROM
    (-1 for every other kind) — the choreography compiler flashes a guard
    chip when its branch fires, so the chip must know its edge."""
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
    header_box: RectSpec | None = None
    """Opaque plate behind the header — the region label drawn as a CHIP.
    Required wherever the label sits ON the region's own boundary (the
    dag-mapreduce enclosure seats a 144x20 chip centred on its top edge, so
    the hairline runs behind the plate instead of through the word). None
    leaves the label as plain text, byte-identical to before."""
    dash: str = ""
    """Enclosure stroke dasharray ('' = the solid hairline every SM
    enclosure keeps). The loop scope wears the dashed region grammar
    (cycle-nested: 'dashed outline + legend plate') — band data, never a
    template branch."""
    outline: bool = False
    """Draw the frame UNFILLED. A region ``enclosure`` is a dashed outline where
    a ``band`` is a filled panel; the loop scope is a third thing — a filled box
    with a dashed rim — so the material cannot be read off the ground alone."""
    region_id: str = ""
    """The authored ``regions:`` entry this band draws ('' for a lane band, a
    swimlane or a zone header). Two readers need it: the diagnostics pass, to
    tell a region that DREW from one the grouping law suppressed, and the
    shared region pass, to recognise bands a solver already built rather than
    building them twice."""


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
class PulseOverlay:
    """One choreographed pulse rider over a connector's track: a short dash
    swept via ``stroke-dashoffset`` from parked-invisible (+dash, entirely
    before the path) to full-exit (-length, entirely after) — the turn
    register's capture vocabulary. Fires once per beat window; all windows
    live in ONE keyframes block (``anim_index``) on the shared super-period
    clock, exactly as the hand specimens author it."""

    connector_index: int
    hue: str  # A (accent) | C (complement) | N (neutral conn)
    dasharray: str
    rest_offset: float
    anim_index: int
    route_d: str = ""
    """The path the overlay rides: the connector's route trimmed at the
    arrowhead's BASE (the corpus stops the lit line there and draws the
    chevron beyond it); the full path when the edge carries no marker."""


@dataclass(frozen=True, slots=True)
class HaloFlash:
    """An arrival halo / guard flash / terminal hold / scope glow: an
    opacity-animated outline in the element's OWN hue (motion adds no hue
    roles). ``rect`` carries a box (node/chip inflated past its edges);
    ``path`` carries a rhombus outline ``d`` for diamonds."""

    shape: str  # rect | path
    hue: str  # A | C | W (deliberation) | N (conn)
    anim_index: int
    box: RectSpec | None = None
    d: str = ""


@dataclass(frozen=True, slots=True)
class ChipTint:
    """A chip lighting up: the chip's OWN markup re-stamped inside an
    opacity-animated group — ground re-drawn with the branch hue's rim,
    text re-inked in the same hue (the corpus tint groups: white chip,
    hue rim at 1.4, mono text in the hue). The box is the chip's exact
    box, never inflated — the tint IS the chip, not a halo around it."""

    box: RectSpec
    lines: tuple[DiagramText, ...]
    hue: str  # A | C | W (deliberation)
    anim_index: int


@dataclass(frozen=True, slots=True)
class MeterStrip:
    """The meter kit piece: a declared segment gauge riding a return edge's
    chip — a quiet backing plate, a register-tinted lead mark, and a row of
    base segments spanning the chip's own width, seated beneath the chip
    (the three meter specimens: plate 33 tall rx 11 at 4px under the chip,
    segments 13 tall rx 4 at plate top + 10). The layout carries the STATIC
    gauge — every face draws it; the register's choreography fills it
    (``ChoreographyPlan.meter_fills``)."""

    edge_index: int
    plate: RectSpec
    boxes: tuple[RectSpec, ...]
    glyph: GlyphArt | None = None
    hue: str = "M"
    """The lead mark's stroke class: A (accent — the accumulator's gain),
    C (complement — the budget's drain), M (muted ink — the neutral lap
    count). A CLASS, not an attribute: the complement token has no root
    custom property, so an attribute var() would silently paint nothing
    (the var-in-attribute trap)."""


@dataclass(frozen=True, slots=True)
class MeterFill:
    """One animated fill segment over a meter base box — the register's
    performance layer, carrying its arrow of time in the keyframes
    (``anim_index``). ``rest_opacity`` is the reduced-motion resting state:
    a budget gauge rests FULL (nothing spent), a lap counter and an
    accumulator rest empty."""

    box: RectSpec
    anim_index: int
    rest_opacity: float = 0.0


@dataclass(frozen=True, slots=True)
class KeyframeBlock:
    """One precomputed ``@keyframes`` body — percentage stops as a finished
    string ('every animation timing precomputed by the solver package;
    templates do pure substitution'). ``prop`` names the single animated
    property (stroke-dashoffset | opacity), CIM-legal by construction."""

    prop: str
    body: str


@dataclass(frozen=True, slots=True)
class ChoreographyPlan:
    """The compiled register: the diagram's semantic claim performed in time.
    ``beats`` is the payload's beat table ([start, end] seconds per element
    key) — the engine-generated counterpart of the hand specimens' own
    ``beats.table``, so keyframe agreement is testable at ±0.1s."""

    register: str
    super_period_s: float
    acts: tuple[str, ...]
    legs_s: dict[str, float]
    beats: dict[str, tuple[tuple[float, float], ...]]
    pulses: tuple[PulseOverlay, ...]
    halos: tuple[HaloFlash, ...]
    keyframes: tuple[KeyframeBlock, ...]
    halo_stroke: float = 2.0
    meter_fills: tuple[MeterFill, ...] = ()
    """The meter registers' fill layer over ``DiagramLayout.meters`` —
    empty for turn/drift, so existing plans stay byte-identical."""
    trails: tuple[PulseOverlay, ...] = ()
    """The lit route (the expression corpus's one language): per turn, each
    leg's trail draws on in the accent and holds to the turn's clear."""
    marker_fades: dict[int, int] = field(default_factory=dict)
    """connector_index -> anim_index: the arrowhead pops when its leg
    completes and hides at the clear."""
    marker_hues: dict[int, str] = field(default_factory=dict)
    """connector_index -> hue class letter: the popping arrowhead rides its
    leg's own hue, exactly like the trail beneath it."""
    trail_stroke: float = 2.6
    pulse_stroke: float = 4.5
    """The comet head riding the drawing tip: ONE rounded-cap stroke whose
    glowing tail comes from the bloom filter, extracted from the flywheel
    hand asset (owner ruling 2026-08-30) — the 3-layer animation-delay
    stack it replaces smeared the head temporally and tore on bezier
    acceleration."""
    comet_bloom: tuple[tuple[float, float], ...] = ((2.5, 0.8), (6.0, 0.4))
    """(stdDeviation, flood-opacity) per bloom pass of the comet fuse filter
    — the hand asset's tight-core + wide-wash pair. The performance register
    (``performance=composite-only``) drops the filter and keeps the bare
    stroke."""
    tints: tuple[ChipTint, ...] = ()
    """Chips lighting up as their leg fires — the corpus's tint groups."""


@dataclass(frozen=True, slots=True)
class RenderedMotion:
    """Requested vs rendered — recorded in the payload so a fallback or a
    track resolution never silently diverges from what the caller asked."""

    edge_motion: tuple[str, ...]
    track: tuple[str, ...]
    glyph_tint: tuple[str, ...]
    performance: str  # paint-ok | composite-only
    fallback_applied: bool
    motion_register: str = ""
    """The resolved choreography register ('' pre-resolution; 'drift' |
    'turn' once the compose seam decides) — additive default keeps every
    existing payload byte-identical."""
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
    meters: tuple[MeterStrip, ...] = ()
    """Meter kit pieces (loop family, ``edge.meter``) — derived on the
    frozen layout from each metered return's placed chip (the choreography
    precedent), so they ride no solve-time normalization channel."""
    chip_visible_run: float = 0.0
    """The spec's own chip-density citation, carried for the battery (0 =
    the enrolled 30px/one-third law)."""
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
    choreography: ChoreographyPlan | None = None
    """The compiled motion register (turn today; enumerate is the next
    wave's seam). None = the plain drift face — every pre-existing layout
    stays byte-identical."""
    rendered: RenderedMotion = field(
        default_factory=lambda: RenderedMotion(
            edge_motion=(), track=(), glyph_tint=(), performance="composite-only", fallback_applied=False
        )
    )
