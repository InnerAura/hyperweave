"""Diagram measurement: voice resolution and content-solved card boxes.

The pure sizing layer beneath ``chrome.py``'s placement functions. Everything
here MEASURES — it maps a node's text to the width and height its card needs,
using the same per-font LUTs (via the matrix voice helpers) the defs CSS
renders with, so a solved box and its rendered strings never disagree. The
voice-class registry is the single source coupling placement classes to
paradigm voices; ``chrome.py`` and the resolver both read it.

Placement (``place_card`` and friends) lives one layer up in ``chrome.py`` and
consumes these measurements — this module never imports back, so the two form
a clean lower/upper split with no cycle.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from hyperweave.compose.matrix.cells import measure_voice, wrap_text_lines
from hyperweave.core.diagram import DiagramNode, DiagramSpec, NodeHealth, NodeRole, NodeStyle
from hyperweave.core.paradigm import DiagramNodeChassis, DiagramTopologyChassis, MatrixVoice, ParadigmDiagramConfig

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from typing import Any

    from hyperweave.compose.diagram.wiring import SolverContext
    from hyperweave.core.diagram import ResolvedEdge


def style_of(
    node: DiagramNode, spec: DiagramSpec, ch: DiagramTopologyChassis, *, default: str = NodeStyle.CARD.value
) -> str:
    """The node-anatomy cascade, shared by all eight topology solvers: an
    explicit per-node ``style`` wins, then the spec-level ``node_style``,
    then the topology chassis default, else ``default``. ``default`` is
    card everywhere except the hub compass center, whose structural
    fallback is glyph-circle (the emanation mask its ring spokes paint
    against) — the one call site that needs a different tail."""
    if node.style is not None:
        return node.style.value
    if spec.node_style is not None:
        return spec.node_style.value
    return ch.node_style or default


def node_glyph_id(node: DiagramNode, registry: Mapping[str, Any] | None) -> str:
    """The identity-slot resolution ladder: brand ``glyph`` -> semantic
    ``kind`` (core set) -> nothing. First id that RESOLVES in the merged
    registry wins; neither resolving means no mark at all (icon-or-nothing
    — an unknown slug never renders an empty group). A ``kind`` prefers its
    namespaced ``kind:<slug>`` entry so generic words a brand shadows
    (shield, star, braces) still reach the generic mark.

    Lives in the MEASUREMENT layer because both consumers need the same
    answer: ``chrome`` builds the mark from it, and the card+label solve sizes
    the label row's clearance from it — an unresolved slug must reserve
    nothing, so sizing has to run the same ladder placement does rather than
    trust the declaration. ``chrome`` re-exports it for its own callers."""
    if registry is None:
        return ""
    if node.glyph and node.glyph in registry:
        return node.glyph
    if node.kind:
        for gid in (f"kind:{node.kind}", node.kind):
            if gid in registry:
                return gid
    return ""


def node_anatomy_of(spec: DiagramSpec, ch: DiagramTopologyChassis) -> str:
    """The card-anatomy cascade (mirror of ``style_of``): a spec-level
    ``node_anatomy`` override wins over the topology chassis default. One
    resolver so the SIZING seam (``solve_node_box``), the PLACEMENT seam
    (``place_node``), and the pipeline branch selector (``solve_pipeline``)
    read the SAME value. The three used to hand-roll it and one (the pipeline
    branch gate) read chassis-only — so a portrait chassis default with a
    ``row`` spec override stuffed portrait content into landscape-split widths.
    rag-pipeline inherits the chassis ``head``; artifact-roundtrip/gateway
    override to ``row`` on the same chassis."""
    return spec.node_anatomy or ch.node_anatomy


# cls -> ParadigmDiagramConfig voice attribute. The resolver emits one CSS
# class per entry; placements reference the cls; measurement uses the same
# voice. One registry, three consumers, zero drift.
VOICE_CLASSES: tuple[tuple[str, str], ...] = (
    ("title", "title_voice"),
    ("sub", "subtitle_voice"),
    ("name", "label_voice"),
    ("dname", "label_voice"),
    ("ndesc", "desc_voice"),
    ("hname", "hero_name_voice"),
    ("hdesc", "hero_desc_voice"),
    ("nlbl", "card_label_voice"),
    ("nval", "card_value_voice"),
    ("hlbl", "hero_label_voice"),
    ("hval", "hero_value_voice"),
    ("mname", "muted_name_voice"),
    ("mdesc", "desc_voice"),
    ("op", "op_voice"),
    ("elbl", "edge_label_voice"),
    ("msg", "edge_label_voice"),
    ("key", "legend_voice"),
    ("tag", "tag_voice"),
    ("short", "short_voice"),
    ("hubshort", "hub_short_voice"),
    ("clbl", "circle_label_voice"),
    ("ft", "foot_voice"),
    ("cap", "caption_voice"),
    ("ann", "annotation_voice"),
    ("lane", "lane_header_voice"),
    ("rlabel", "lane_header_voice"),
    ("zoneh", "lane_header_voice"),
    ("zoneha", "lane_header_voice"),
    ("cnt", "count_voice"),
    ("rcnt", "region_label_voice"),
)


def voice_for(cfg: ParadigmDiagramConfig, cls: str) -> MatrixVoice:
    for name, attr in VOICE_CLASSES:
        if name == cls:
            voice = getattr(cfg, attr)
            assert isinstance(voice, MatrixVoice)
            return voice
    raise KeyError(f"unknown diagram voice class {cls!r}")


def label_cls_for(node: DiagramNode, mono_triggers: list[str]) -> str:
    """Node labels are display-face; a run carrying arrow/operator glyphs
    Inter lacks routes to the mono desc voice (the matrix mono_triggers
    rule applied structurally)."""
    if any(t in node.label for t in mono_triggers):
        return "ndesc"
    return "name"


def role_of(node: DiagramNode) -> str:
    if node.role is NodeRole.HERO:
        return "hero"
    if node.role is NodeRole.MUTED:
        return "muted"
    return "default"


GLYPH_MARK_W = 24.0
"""Identity-mark advance: the card+glyph mark's measured width. The specimen
label-row glyphs render at 24px (cicd-gate / comparison / rag-pipeline all
scale their 24-unit marks to 1.0) — a 16px mark read tiny in the card gutter."""
HERO_GLYPH_MARK_W = 32.0
"""The nucleus mark (primer_diagram_language): hero glyph 26→32, riding
the identity block with an 18px optical gap (hero chassis label_gap 22)."""
DOT_MARK_W = 8.0
"""Accent-dot advance: the dot's measured diameter (2 x NodePlacement.dot_r)."""

HEAD_GLYPH_SIZE = 22.0
"""Sequence participant HEAD anatomy (auth-sequence): the identity glyph's
rendered size — centered above the name, a near-square head card rather
than the card/hero label-row anatomies."""
HEAD_GLYPH_GAP = 7.0
"""Vertical gap between the head glyph's bottom edge and the name's ascent."""
HEAD_PAD_X = 10.0
"""Horizontal text padding a head card's name truncates against."""


def head_pad_x(nch: DiagramNodeChassis, *, hero: bool = False) -> float:
    """A head card's horizontal text pad: an EXPLICIT chassis declaration
    wins for SATELLITES (frame-engine's tiles hold a 107.25px tracked run
    inside a 123.2px card — 8px pads, tighter than the kit constant); an
    undeclared chassis keeps ``HEAD_PAD_X`` (the field's 12.0 default is
    the card-truncation pad, never a head fact). HERO heads always keep the
    kit pad — a hero chassis often declares pad_x for a DIFFERENT anatomy
    (the axial nucleus' 32px text budget), and honoring it here widened the
    fe crown past its own 164 pin, then truncated its name at placement."""
    if hero:
        return HEAD_PAD_X
    return float(nch.pad_x) if "pad_x" in nch.model_fields_set else HEAD_PAD_X


def mark_w_for(style: str, node: DiagramNode, *, hero: bool = False) -> float:
    """The MEASURED mark advance a node's label row carries (G3): the
    identity mark or nothing. Width solving and placement both read this —
    one measurement, no shims. Icon-or-nothing is total: a node with no
    ``glyph``/``kind`` reserves NO advance — its content adjusts (an empty
    reserved slot read as a centered card, the retired reservation defect).
    Column uniformity down a rank comes from the nodes CARRYING their
    specimen marks (every hand rank draws one per card), never from holding
    a phantom slot open."""
    # A card+glyph node declares its mark via EITHER a brand ``glyph`` or a
    # geometric ``kind`` — both resolve to a GLYPH_MARK_W-wide mark, so the
    # card must reserve that width or the label truncates under a kind glyph
    # solved as a narrow dot. A chassis ``glyph_w`` (the nucleus family's
    # 32) overrides at the solve seam, not here.
    del hero
    if style == NodeStyle.CARD_GLYPH.value and (node.glyph or node.kind):
        return GLYPH_MARK_W
    return 0.0


def ink_gap(nch: DiagramNodeChassis) -> float:
    """Mark INK edge to label start for the LANES bulleted anatomy (its sole
    remaining consumer — the obi-engine morphology-mark envelope). The chassis
    ``label_gap`` is specified dot-center to label-start; the ink gap
    subtracts the dot's radius so wider marks keep the same optical gap by
    measurement instead of a +4 shim. Card/hero glyph columns read the
    content-anchor pair (``glyph_inset_x``/``glyph_label_gap``) via
    ``mark_lead`` instead."""
    return nch.label_gap - DOT_MARK_W / 2


def label_desc_gap_for(nch: DiagramNodeChassis, cfg: ParadigmDiagramConfig) -> float:
    """Name-baseline to first-desc-baseline air for ANY anatomy (CARD/HERO
    via ``solve_card_box``/``chrome._slot_vertical``, HEAD via
    ``solve_head_box``/``place_head``): an explicit chassis ``label_desc_gap``
    wins (the primer_diagram_language sheet's hero families each measure a
    different generous gap — 9 for the 206x104 router hero, 12 for the
    232x112 axial nucleus, neither the paradigm default); undeclared, the
    paradigm-wide default holds. One resolver so every anatomy's
    content-solved height and its rendered baseline read the same air — the
    seam ``pad_y`` already established (``ink_gap`` for the horizontal lead,
    this for the vertical one)."""
    return cfg.label_desc_gap if nch.label_desc_gap is None else nch.label_desc_gap


def _desc_ink_w(desc: str, voice: MatrixVoice) -> float:
    """Widest desc line, honoring AUTHORED breaks — a ``\\n``-split subtitle
    measures as its longest line, never both phrases concatenated (which would
    inflate the card to a phantom one-line width)."""
    if not desc:
        return 0.0
    return max(measure_voice(line, voice) for line in desc.split("\n"))


BULLET_DESC_RIGHT_GAP = 4.0
"""Desc-run slim right gap, ALL card anatomies: a desc may run from the
text column to within this gap of the card's right edge before wrapping —
the corpus lets long descs run nearly flush (the obi-engine bullet's 37-char
desc ends ~6px off the edge; the stack sheet's longest desc runs to ~the
edge of its 163 card; the agent-loop hand file's 'tools · model · memory'
renders whole inside a card the anchor+pad_x budget would have wrapped).
The card's width MINIMUM still reserves the full ``pad_x`` right of ink
(``anchor_pads``) — this gap only forgives wrap on width-capped cards,
mirroring how the hand files spend a tight card's last pixels on ink."""


def effective_diagram_cfg(cfg: ParadigmDiagramConfig, ch: DiagramTopologyChassis) -> ParadigmDiagramConfig:
    """The topology-adjusted voice config — the ONE seam where a chassis
    voice override lands, so measurement (wrap/solve), placement (chrome),
    and the resolver's CSS emission all read the same size. The obi-engine specimen's
    node descs are JBM 10px untracked against the kit's 11/0.01em — chassis
    facts of that topology, not a new voice."""
    update: dict[str, float] = {}
    if ch.desc_voice_size and ch.desc_voice_size != cfg.desc_voice.size:
        update["size"] = ch.desc_voice_size
    if ch.desc_voice_tracking_em is not None and ch.desc_voice_tracking_em != cfg.desc_voice.tracking_em:
        update["tracking_em"] = ch.desc_voice_tracking_em
    if not update:
        return cfg
    return cfg.model_copy(update={"desc_voice": cfg.desc_voice.model_copy(update=update)})


def desc_word_w(desc: str, voice: MatrixVoice) -> float:
    """Widest UNBREAKABLE run in the desc — the minimum wrap budget that never
    single-word-truncates. Wrapping ellipsizes any word wider than its budget
    (``glyphs-core.json`` → ``glyphs-core.…``), so a card's width must clear
    the widest word BEFORE the desc wraps: reasonable subtitles grow the box,
    they never lose characters."""
    if not desc:
        return 0.0
    return max((measure_voice(w, voice) for line in desc.split("\n") for w in line.split(" ") if w), default=0.0)


def card_ink_w(
    node: DiagramNode,
    nch: DiagramNodeChassis,
    cfg: ParadigmDiagramConfig,
    mono_triggers: list[str],
    mark_w: float,
) -> float:
    """Measured ink width of a card's content group: the mark advance + gap,
    then name and desc SHARING one text column below/beside it (the specimen
    slot model — dag push's `push`/`main` both sit at the same left edge, the
    glyph in the gutter). The lead offsets BOTH runs, so the group spans
    ``lead + widest(name, desc)`` — never the wider of {lead+name, desc},
    which would flush the desc under the glyph instead of the name."""
    cls = label_cls_for(node, mono_triggers) if role_of(node) == "default" else "mname"
    voice = voice_for(cfg, cls)
    return mark_lead(mark_w, nch) + max(measure_voice(node.label, voice), _desc_ink_w(node.desc, cfg.desc_voice))


def label_row_w(
    node: DiagramNode,
    nch: DiagramNodeChassis,
    cfg: ParadigmDiagramConfig,
    mono_triggers: list[str],
    mark_w: float,
    *,
    hero: bool = False,
) -> float:
    """The [mark · gap · name] identity row's measured width. The name is
    IDENTITY — a card's width ceiling must never clip it (kit: cards size to
    content; descs wrap, chips cap, names never truncate)."""
    if hero:
        voice = cfg.hero_name_voice
    else:
        cls = label_cls_for(node, mono_triggers) if role_of(node) == "default" else "mname"
        voice = voice_for(cfg, cls)
    return mark_lead(mark_w, nch) + measure_voice(node.label, voice)


def _hero_ink_w(node: DiagramNode, nch: DiagramNodeChassis, cfg: ParadigmDiagramConfig, mark_w: float) -> float:
    """Hero content ink width — factored so ``solve_card_w`` and
    ``solve_card_box`` share one measurement. Name and desc share the TEXT
    column (both start at group_left + lead, the specimen slot model), so
    the lead advances the widest text run, not just the name row."""
    return mark_lead(mark_w, nch) + max(
        measure_voice(node.label, cfg.hero_name_voice),
        _desc_ink_w(node.desc, cfg.hero_desc_voice),
    )


def solve_card_w(
    node: DiagramNode,
    nch: DiagramNodeChassis,
    cfg: ParadigmDiagramConfig,
    mono_triggers: list[str],
    *,
    hero: bool = False,
    min_w: float = 0.0,
    mark_w: float = DOT_MARK_W,
) -> float:
    """Content-solved card width — the pill precedent (G3):
    ``clamp(measured ink + anchor_pads, min_w, chassis ceiling)``. The
    horizontal minimum is the ASYMMETRIC snug envelope (content-anchor law):
    the ``glyph_inset_x`` anchor on the left plus the ``pad_x`` truncation
    pad on the right — the width-defining run of a snug hand card ends a
    slim gap off the right edge (the stack sheet's longest desc runs nearly
    flush; the obi bullet desc cites ~6px), never a second anchor's worth.
    A floored/pinned card left-anchors and pools the extra right, like every
    wide hand specimen. Free-policy topologies solve each card;
    aligned-policy topologies take the max over members."""
    content = _hero_ink_w(node, nch, cfg, mark_w) if hero else card_ink_w(node, nch, cfg, mono_triggers, mark_w)
    pads = anchor_pads(nch)
    want = content + pads
    # The chassis width is the design TARGET, not a content-clipping wall:
    # the ceiling stretches just enough to hold the identity row — the full
    # hero text column — and the chip row — whole (descs still wrap at the
    # chassis width). Cards whose content already fits are byte-identical.
    row_need = (content if hero else label_row_w(node, nch, cfg, mono_triggers, mark_w, hero=hero)) + pads
    if node.chips:
        # A HERO's chip row CENTERS in the crown (the observability hand
        # crown seats its 3-chip row at a symmetric ~8px, holding the 220
        # pin) — it reserves the slim truncation pads, never the anchor
        # column. A std card's row rides the glyph column (rag-pipeline /
        # service-deps), so it reserves the anchor envelope.
        chip_pads = 2 * nch.pad_x if hero else pads
        row_need = max(row_need, chip_row_w(node.chips, cfg) + chip_pads)
        want = max(want, chip_row_w(node.chips, cfg) + chip_pads)
    ceiling = max(nch.w, math.ceil(row_need / 2) * 2)
    return max(min_w, min(ceiling, math.ceil(want / 2) * 2))


# Chip-row metrics (chrome vocabulary — identical on every topology):
# pill horizontal pad, pill height, inter-pill gap, corner radius. Measured
# from the hub specimen: extract/verify/diff/query at w~66 h=26 rx=8
# (a rounded rect, NOT a full pill — rx is fixed, not h/2).
CHIP_PAD_X = 10.0
CHIP_H = 26.0
CHIP_GAP = 6.0
CHIP_RX = 8.0


def solve_chip_box(text: str, cfg: ParadigmDiagramConfig) -> tuple[float, float]:
    """The one chip-pill sizing seam (rag-pipeline/service-deps chips): a chip's
    width is its text measured in the SAME voice it RENDERS in — ``tag_voice``,
    the ``.tag`` class — plus ``CHIP_PAD_X`` each side, at ``CHIP_H``. The retired
    edge-chip path measured ``count_voice`` (the smaller member-count numeral)
    while painting ``tag_voice``, so the pill under-sized by a per-character
    margin: invisible on ``reads``, fatal on ``direct read`` (the text hit the
    pill walls). Interior card chips already measured tag_voice; both the
    interior row and the edge chip flow through here so a chip can never again
    be sized against a voice it isn't drawn in."""
    return measure_voice(text, cfg.tag_voice) + 2 * CHIP_PAD_X, CHIP_H


def chip_row_w(chips: tuple[str, ...], cfg: ParadigmDiagramConfig) -> float:
    """Packed width of a chip row — part of the card's content group."""
    if not chips:
        return 0.0
    row = sum(solve_chip_box(c, cfg)[0] for c in chips)
    return row + CHIP_GAP * (len(chips) - 1)


BARE_LABEL_FACE_CLEARANCE = 10.9
"""Minimum clearance a bare (non-chip) micro-label keeps off each of its own
run's two node faces — measured across the hand SM specimens' straight runs:
pp-state-machine.svg's start/built sit at 18.4px/face, pp-state-machine-
alt2.svg's assigned/approved at 10.9px/face (its own letter-spacing, 0.06em).
The tighter of the two is the floor: 18 would make alt2's OWN runs violate
the very law it cites (its 'assigned' ink + 2*18 exceeds the 74px run the
parity board pins), so 10.9 is the honest minimum, not the average."""

CHIP_STUB_MIN = 18.4
"""Minimum visible wire a chip PILL keeps clear on EACH side of its own run
— the same hand-SM citation pair as ``BARE_LABEL_FACE_CLEARANCE``, but the
LOOSER of the two bands (pp-state-machine.svg's 18.4px/face): a filled pill
needs more breathing room than bare ink reads legible at (alt2's tighter
10.9 governs text with no fill to read against). This is the generic floor
for any chip-bearing run with no more specific citation of its own — a
family with its own tighter measured standoff (the dag-scatter gather
trunk's 9px, ``graph._GATHER_STANDOFF``) keeps that number; this is what an
otherwise-uncited run inherits, replacing the three duplicated
``engine.connector.chip_stub_min`` Python-fallback reads (the key is never
actually set in any genome/paradigm YAML, so ``18`` was a rounded guess
standing in for this measurement, not real config)."""


def marker_reserved_stub(engine: Mapping[str, Any], base_stub: float) -> float:
    """``base_stub`` plus the connector's drawn marker length, for a stub
    whose run terminates in a rendered terminal marker (a JOIN trunk's
    arrowhead, always present — ``knot_collapse``'s join branch never
    overrides its default ``marker="arrow"``). The chevron's own draw
    length eats into a bare stub's visible thread (frontier-serving's
    'cache' seated on a bare standoff left ~1px between the pill and an
    8px chevron before this reserve existed) — a DEPART trunk (arrowless;
    the spokes carry their own chevrons) never calls this. Every chip seats
    at its run's MIDPOINT (unanimous specimen law — no run splits its stub
    unevenly), so the reserve is spent on BOTH halves of the run once,
    not sliced asymmetrically off the marker's own end."""
    return base_stub + float((engine.get("connector") or {}).get("marker_size", 11))


def chip_run_min(
    edges: Sequence[ResolvedEdge],
    cfg: ParadigmDiagramConfig,
    *,
    stub: float,
    vertical: bool = False,
) -> float:
    """Minimum straight-run length for the LABELED edges in ``edges`` — chip
    or bare micro-label alike: a run can never be narrower than the label it
    will carry. A chip's extent is its pill (``solve_chip_box``) plus a
    visible stub of wire on BOTH sides (specimen law — rag-pipeline keeps
    ~40px stubs). A BARE label has no pill to stub against — its floor is
    its own measured ink (the edge-label voice) plus
    ``BARE_LABEL_FACE_CLEARANCE`` each side: only ``label_style == "chip"``
    used to feed this floor, so a run sized for its chip neighbors could seat
    a plain label a hairline from its own card (a bare micro-label carried
    ZERO weight here). The layout pass fixes edge length before the
    annotation pass measures the label; this is the solver-side
    reconciliation of that double measurement.

    A ``relation: bypass`` edge is excluded from the bare-label floor: it is
    the L4 exception/privileged path (core/diagram.py, capped at one per
    diagram) that by definition routes AROUND the adjacent-node chain, never
    confined to a single rank/chain gap the way a forward or back edge is —
    artifact-roundtrip's own 'transform -> artifact' bypass edge is the
    citation (its label rides a standalone curve well outside any one gap;
    folding its ink into the uniform gap floor inflated every OTHER,
    unrelated gap in the chain to hold a label that was never confined to
    begin with)."""
    chip_vals = [
        (CHIP_H if vertical else solve_chip_box(e.label, cfg)[0]) + 2 * stub
        for e in edges
        if e.label and e.label_style == "chip"
    ]
    # A bare label's ALONG-RUN extent mirrors the chip split: its measured
    # width on a horizontal run, one text block's height (the same
    # ascent+descent block every card/desc measurement in this module
    # shares) on a vertical one — never CHIP_H, a pill-specific constant a
    # bare label never draws.
    bare_h = cfg.edge_label_voice.size * (cfg.text_ascent_ratio + cfg.text_descent_ratio)
    bare_vals = [
        (bare_h if vertical else measure_voice(e.label, cfg.edge_label_voice)) + 2 * BARE_LABEL_FACE_CLEARANCE
        for e in edges
        if e.label and e.label_style != "chip" and e.relation != "bypass"
    ]
    return max(chip_vals + bare_vals, default=0.0)


def anchor_pads(nch: DiagramNodeChassis) -> float:
    """The card anatomy's horizontal MINIMUM: the ``glyph_inset_x`` content
    anchor on the left plus the ``pad_x`` truncation pad on the right — the
    asymmetric snug envelope every width solve and text budget shares (a
    min-width card can then never wrap or clip its own width-defining
    run)."""
    return nch.glyph_inset_x + nch.pad_x


def mark_lead(mark_w: float, nch: DiagramNodeChassis) -> float:
    """The glyph-mark indent the label+desc text column starts at: the mark's
    advance plus the chassis ``glyph_label_gap`` (content-anchor law: 24+14
    puts the text column at card+60 over the ``glyph_inset_x`` 22 anchor —
    primer_diagram_language providers, pp-dag-serving-v2), or 0 when there is
    no mark. The LABEL budget always subtracts this (text sits to the RIGHT of
    the glyph); the DESC budget and the box-growth guard must subtract it too —
    otherwise a desc is measured against the FULL card width, judged to fit on
    one line, never wrapped, then rendered indented and bleeding past the
    card's right edge (the overflow bug). One place, so the label and desc
    budgets can never disagree again."""
    return (mark_w + nch.glyph_label_gap) if mark_w else 0.0


def solve_card_box(
    node: DiagramNode,
    nch: DiagramNodeChassis,
    ch: DiagramTopologyChassis,
    cfg: ParadigmDiagramConfig,
    mono_triggers: list[str],
    *,
    hero: bool = False,
    min_w: float = 0.0,
    mark_w: float = DOT_MARK_W,
    h_floor: float | None = None,
    bullet_lead: float = 0.0,
) -> tuple[float, float, tuple[str, ...]]:
    """Content-solved card box (G3 extension): width as ``solve_card_w`` with
    the ``w_max`` ceiling, plus a HEIGHT that fits the desc wrapped to that
    width. Returns ``(w, h, wrapped_lines)``.

    Height inverts ``_text_block``'s metric-centered layout: the fitting box
    is ``label_block + label_desc_gap + n_lines*desc_block + (n-1)*pitch +
    2*min_pad_y``, floored at the chassis ``h`` (so cards that already fit
    render byte-identically) and clamped to ``h_max`` when set (then the
    ``_text_block`` drop rule stays the honest overflow valve). Wrapping uses
    the solved width, so the returned lines are what actually renders."""
    # Citations ride the CEILING (snug-width ruling): the chassis archetype,
    # w_max, and the per-preset width pin all bound growth without ever
    # inflating a card past its own ink.
    w_ceiling = max(nch.w, ch.w_max, ch.card_min_w)
    # A hero must never solve NARROWER than a regular spoke: its chassis width is
    # a floor tuned for a short archetype, not a ceiling. Let it grow to the node
    # ceiling so a glyph + name never truncates in a family whose spokes are wider
    # than its hero card (convergence/stack heroes vs their 168px spokes).
    if hero:
        w_ceiling = max(w_ceiling, ch.node.w, ch.w_max, ch.hero_min_w)
    if bullet_lead:
        # Bulleted-card anatomy (obi-engine): the leading category mark IS
        # the identity slot — the card+glyph reservation never applies (a
        # reserved-empty glyph column would double-indent every lane card).
        mark_w = 0.0
    content = _hero_ink_w(node, nch, cfg, mark_w) if hero else card_ink_w(node, nch, cfg, mono_triggers, mark_w)
    if bullet_lead:
        # The label row alone indents past the leading category mark — the
        # desc stays flush, so only the label's row need grows by the lead.
        # The bulleted envelope keeps its own pad_x anchor (its specimen's
        # asymmetric column), never the card-glyph anchor inset.
        content = max(content, bullet_lead + label_row_w(node, nch, cfg, mono_triggers, 0.0))
    pads = 2 * nch.pad_x if bullet_lead else anchor_pads(nch)
    want_w = content + pads
    # Never-clip rule: the ceiling stretches to hold the identity row whole —
    # and for heroes the whole TEXT COLUMN (name and desc share it under the
    # slot model, so a wide hero desc stretches the crown too).
    row_need = (content if hero else label_row_w(node, nch, cfg, mono_triggers, mark_w, hero=hero)) + pads
    if bullet_lead and not hero:
        row_need = max(row_need, bullet_lead + label_row_w(node, nch, cfg, mono_triggers, 0.0) + pads)
    w_ceiling = max(w_ceiling, math.ceil(row_need / 2) * 2)
    # Snug-width ruling (owner, 2026-07-14): a card's width is its OWN
    # content + the anchor envelope, full stop. Hand-file width citations
    # (crown pins, ``card_min_w``/``hero_min_w``, the retired dominance
    # floor) are SANITY CEILINGS — they may bound growth, never inflate a
    # card past its ink (extract carried +54px and the artifact crowns +87
    # of pure pin inflation, all pooling right of the anchored text). The
    # only remaining width FLOOR is ``min_w`` itself, which callers use
    # exclusively for content-derived aligned shares (a rank/ring re-solve
    # at its widest sibling's own solve).
    w = max(min_w, min(w_ceiling, math.ceil(want_w / 2) * 2))
    label_voice = (
        cfg.hero_name_voice
        if hero
        else voice_for(cfg, label_cls_for(node, mono_triggers) if role_of(node) == "default" else "mname")
    )
    desc_voice = cfg.hero_desc_voice if hero else cfg.desc_voice
    # Never-truncate rule (kit): the box clears the desc's widest unbreakable
    # word before wrapping — growth, not ellipsis, absorbs long tokens. The desc
    # renders at the glyph LEAD indent, so both the growth guard and the wrap
    # budget must account for it (the overflow bug lived in this omission).
    # Only the LABEL-ROW default card indents its desc by the glyph lead; a hero
    # renders its desc on its own centered line (full width), and a bulleted card
    # uses its own envelope — both keep lead 0.
    # The desc shares the TEXT column on heroes too (the slot model): its
    # wrap budget subtracts the mark lead for every non-bullet anatomy — the
    # old hero exemption measured hero descs against the full card width, so
    # an anchored crown's desc ran past the right gutter (the axial crown's
    # one-line payload string, caught by the render sweep).
    lead = 0.0 if bullet_lead else mark_lead(mark_w, nch)
    word_need = math.ceil((desc_word_w(node.desc, desc_voice) + pads + lead) / 2) * 2
    w = max(w, word_need)
    # Descs wrap against the slim-gap envelope (anchor column to
    # BULLET_DESC_RIGHT_GAP off the edge — see that constant's citations),
    # so a width-capped card spends its last pixels on ink like the hand
    # files do instead of wrapping at the width-minimum's own pad.
    desc_budget = (
        (w - nch.pad_x - BULLET_DESC_RIGHT_GAP)
        if bullet_lead
        else (w - nch.glyph_inset_x - lead - BULLET_DESC_RIGHT_GAP)
    )
    lines = wrap_text_lines(node.desc, desc_budget, desc_voice, max_lines=nch.max_desc_lines)
    ar, dr = cfg.text_ascent_ratio, cfg.text_descent_ratio
    ldg = label_desc_gap_for(nch, cfg)
    block = label_voice.size * (ar + dr)
    if lines:
        block += ldg + desc_voice.size * (ar + dr) + (len(lines) - 1) * nch.desc_line_pitch
    if node.chips:
        # Chip-row: one row of inline pills beneath the desc. Chips are
        # CONTENT — the row stretches the ceiling exactly like the identity
        # row does (a clamped ceiling rendered the row overflowing the card).
        # Chip metrics ride the tag voice + fixed pill pads (chrome
        # vocabulary — identical on every topology). A hero row CENTERS in
        # the crown at the slim pads (the observability hand crown's ~8px
        # symmetric seat); a std row rides the glyph column, reserving the
        # anchor envelope.
        chip_pads = 2 * nch.pad_x if hero else anchor_pads(nch)
        row_w = math.ceil((chip_row_w(node.chips, cfg) + chip_pads) / 2) * 2
        w_ceiling = max(w_ceiling, row_w)
        w = max(w, row_w)
        block += ldg + CHIP_H
    if node.embed_dims:
        # sec 12.1: the container reserves its inner artifact's display box
        # beneath the text block (same growth contract as the chip row).
        ew, eh = node.embed_dims
        embed_w = math.ceil((ew + 2 * nch.pad_x) / 2) * 2
        w_ceiling = max(w_ceiling, embed_w)
        w = max(w, embed_w)
        block += ldg + eh
    pad_y = cfg.min_pad_y if nch.pad_y is None else nch.pad_y
    want_h = block + 2 * pad_y
    # ``h_floor`` swaps the chassis archetype height for a content-driven one
    # (the hub nucleus: 92 for two specimen rows, 120 for three — the chassis
    # ``h`` encodes the tallest archetype, not a floor for sparser content).
    h = max(nch.h if h_floor is None else h_floor, want_h)
    if ch.h_max and not node.chips and not node.embed_dims:
        h = min(h, ch.h_max)

    def at_width(width: float) -> tuple[float, tuple[str, ...]]:
        """Re-wrap the desc at a candidate width and re-solve the height. Only
        the desc block moves — the chip/embed rows below are width-independent
        additions, already folded into ``block`` above."""
        budget = (
            (width - nch.pad_x - BULLET_DESC_RIGHT_GAP)
            if bullet_lead
            else (width - nch.glyph_inset_x - lead - BULLET_DESC_RIGHT_GAP)
        )
        runs = wrap_text_lines(node.desc, budget, desc_voice, max_lines=nch.max_desc_lines)
        blk = label_voice.size * (ar + dr)
        if runs:
            blk += ldg + desc_voice.size * (ar + dr) + (len(runs) - 1) * nch.desc_line_pitch
        if node.chips:
            blk += ldg + CHIP_H
        if node.embed_dims:
            blk += ldg + node.embed_dims[1]
        got = max(nch.h if h_floor is None else h_floor, blk + 2 * pad_y)
        if ch.h_max and not node.chips and not node.embed_dims:
            got = min(got, ch.h_max)
        return got, tuple(runs)

    # The no-sliver ruling belongs to every label-row CARD.  Portrait/head
    # anatomy never reaches this function, so deliberately tall tiles remain
    # exempt by construction.  Existing stack/pipeline movement is an explicit
    # consequence of the ruling and is reported/rebaselined by the parity pass;
    # it must not be hidden by keeping the guard anatomy-specific.
    return apply_sliver_guard((w, h, tuple(lines)), ceiling=w_ceiling, resolve=at_width)


def hero_height_floor(ch: DiagramTopologyChassis) -> float:
    """The hero HEIGHT floor to pass as ``solve_card_box``'s ``h_floor``: an
    explicit ``hero.h`` citation holds (the crown archetype a specimen
    measured); undeclared, the hero content-solves PURE (0.0, no floor) —
    a glyph row participates in content height exactly like a markless
    label row does, and sibling-height dominance for a hero has no specimen
    justifying it yet (width dominance does — a short-content hero must
    still read as the family's crown; height doesn't carry that reading)."""
    return ch.hero.h if "h" in ch.hero_declared else 0.0


def hero_plate_w(ch: DiagramTopologyChassis) -> float:
    """The crown's WIDTH floor for a plate anatomy (card+label's hero
    register): an explicit ``hero.w`` citation holds, undeclared solves pure.
    The width twin of ``hero_height_floor``, reading the same
    ``hero_declared`` explicitness carrier — a preset that measured its
    specimen's crown gets that plate; a crown nobody measured stays snug."""
    return ch.hero.w if "w" in ch.hero_declared else 0.0


def solve_head_box(
    node: DiagramNode,
    nch: DiagramNodeChassis,
    *,
    cfg: ParadigmDiagramConfig,
    min_w: float,
    hero: bool,
) -> tuple[float, float, tuple[str, ...]]:
    """The stacked portrait card (rag-pipeline / tree / flywheel-orbit): an
    identity glyph centered above the name, desc lines beneath, everything
    on the card's center axis. Width fits the widest run + head pads; height
    fits the stacked block, floored at the chassis (so specimen-true chassis
    dims render exactly when content fits). The glyph-to-name gap and the
    outer vertical pad read ``nch.head_glyph_gap``/``nch.head_pad_y`` when a
    chassis declares them (the hub compass hero); undeclared (``None``)
    keeps the kit constants byte-identical for every other head archetype.
    The name-to-desc air reads ``label_desc_gap_for(nch, cfg)`` — the same
    resolver ``solve_card_box`` uses — so a head-anatomy family (tree,
    dep-audit) can cite its own gap instead of being pinned to the paradigm
    default regardless of what its chassis declares (the prior citation
    dead-end: a preset's own ``label_desc_gap`` was silently ignored here)."""
    name_voice = cfg.hero_name_voice if hero else cfg.label_voice
    desc_voice = cfg.hero_desc_voice if hero else cfg.desc_voice
    pad = head_pad_x(nch, hero=hero)
    ldg = label_desc_gap_for(nch, cfg)
    name_w = measure_voice(node.label, name_voice)
    w = max(min_w, nch.w, math.ceil((name_w + 2 * pad) / 2) * 2)
    if hero and node.desc:
        # The crown widens to its widest AUTHORED desc line (tree's root);
        # standard heads keep wrapping at name width (dep-audit's rows).
        w = max(w, math.ceil((_desc_ink_w(node.desc, desc_voice) + 2 * pad) / 2) * 2)
    # Never-truncate rule (kit): the portrait clears the desc's widest
    # unbreakable word before wrapping (``glyphs-core.json`` grows the stage).
    w = max(w, math.ceil((desc_word_w(node.desc, desc_voice) + 2 * pad) / 2) * 2)
    lines = wrap_text_lines(node.desc, w - 2 * pad, desc_voice, max_lines=nch.max_desc_lines)
    if lines:
        widest = max(measure_voice(line, desc_voice) for line in lines)
        w = max(w, math.ceil((widest + 2 * pad) / 2) * 2)
    ar, dr = cfg.text_ascent_ratio, cfg.text_descent_ratio
    block = name_voice.size * (ar + dr)
    glyph_gap = HEAD_GLYPH_GAP if nch.head_glyph_gap is None else nch.head_glyph_gap
    if node.glyph or node.kind:
        block += HEAD_GLYPH_SIZE + glyph_gap
    if lines:
        block += ldg + desc_voice.size * (ar + dr) + (len(lines) - 1) * nch.desc_line_pitch
    if node.chips:
        # Chip-row on the portrait column: pills centered beneath the desc,
        # measured exactly as the label-row card measures them — the head
        # anatomy hosts every card piece or the piece isn't a lego.
        w = max(w, math.ceil((chip_row_w(node.chips, cfg) + 2 * pad) / 2) * 2)
        block += ldg + CHIP_H
    head_pad_y = cfg.min_pad_y if nch.head_pad_y is None else nch.head_pad_y
    h = max(nch.h, block + 2 * head_pad_y)
    return w, h, tuple(lines)


# ── card+label anatomy ───────────────────────────────────────────────────────
# Slot rhythm measured from the bilateral-wings specimen (hub-bilateral.svg):
# its 3-line card (188x114) and its three 2-line cards (188/188/196 x 92) agree
# on every constant below, so the rhythm is the anatomy's, not one card's.
#   label baseline  card.y + 26        first value  card.y + 50
#   value pitch     22                 bottom air   20
# => h = 50 + (n-1)*22 + 20 — 3 lines gives 114, 2 lines gives 92, both exact.
CARD_LABEL_PAD_X = 20.0
CARD_LABEL_LABEL_DY = 26.0
CARD_LABEL_VALUE_DY = 50.0
CARD_LABEL_VALUE_PITCH = 22.0
CARD_LABEL_PAD_BOTTOM = 20.0

CARD_LABEL_MARK = 20.0
"""Corner-annotation mark size (the specimen's 24-unit kind glyphs at 0.85)."""
CARD_LABEL_MARK_INSET_R = 36.0
"""Mark LEFT edge from the card's right edge (specimen hw:spatial-notes:
'translate(card right edge - 36, card top + 12)') — so the mark's own right
gutter is 36 - 20 = 16."""
CARD_LABEL_MARK_INSET_Y = 12.0
CARD_LABEL_MARK_GAP = 12.0
"""Minimum air between the label run and the corner mark. The mark never opens
a content column — it only forbids the LABEL row from running underneath it."""

HEALTH_DOT_ENVELOPE = 18.0
"""How far the health channel's corner dot reaches in from the card's right
edge: ``dot_inset_x`` 13 + ``dot_r`` 5 (diagram-frame.yaml ``health:``, the
values ``apply_health_dot`` places with)."""
CARD_LABEL_MARK_HEALTH_GAP = 6.0
"""Air between the corner mark and the health dot when BOTH resolve on one
card. The two channels share the top-right corner (dot centre ``w-13``, mark
envelope reaching ``w-16``) and overlap by 2x6px unless the anatomy-owned mark
yields — the generic health channel never moves."""


CROWN_DOMINANCE_MAX = 2.8
"""System-wide balance law: the crown register holds only while the crown's
area stays within this multiple of its STANDARD siblings' median box — the
band the anatomy's own specimen draws (hand file 2.34, the shipped preset's
documented copy amendment 2.65). Past it, a center-seat hero falls back to
the standard register with hero dress: a 28px display stack beside light
satellites dwarfs them (the review board measured 3.2-4.0 on the compass
and axial hubs). A spec-PINNED crown (explicit ``chassis.hero.w``) is the
author's own citation and keeps its register — the render battery reports
its ratio instead of the engine silently overriding a declared plate."""


def crown_within_band(ctx: SolverContext, node: DiagramNode, index: int) -> bool:
    """Whether a card+label hero may take the CROWN register here: True when
    the spec pins the crown (author's ruling), when there are no standard
    siblings to dwarf, or when the solved crown stays inside
    ``CROWN_DOMINANCE_MAX`` of the siblings' median box. One function read
    by BOTH the sizing seam and the placement seam, so the two can never
    disagree about which register renders. Siblings are measured
    ``hero=False`` (their standard boxes are the comparison mass — and a
    second hero can then never recurse back through its own band check)."""
    if bool(((ctx.spec.chassis or {}).get("hero") or {}).get("w")):
        return True
    ch = ctx.ch
    crown_w, crown_h, _ = solve_card_label_box(
        node,
        ch.hero,
        ch,
        ctx.cfg,
        hero=True,
        has_mark=bool(node_glyph_id(node, ctx.glyph_registry)),
        health_dot=node.health is not NodeHealth.OK,
    )
    sibs = [
        solve_node_box(ctx, sib, i, hero=False)[:2]
        for i, sib in enumerate(ctx.spec.nodes)
        if i != index and sib.role is not NodeRole.HERO
    ]
    if not sibs:
        return True
    med_w = sorted(w for w, _ in sibs)[len(sibs) // 2]
    med_h = sorted(h for _, h in sibs)[len(sibs) // 2]
    if med_w <= 0 or med_h <= 0:
        return True
    return (crown_w * crown_h) / (med_w * med_h) <= CROWN_DOMINANCE_MAX


def card_label_mark_inset_r(*, health_dot: bool) -> float:
    """The mark's LEFT-edge inset from the card's right edge. The specimen's 36
    — unless the health dot occupies the corner, in which case the mark shifts
    left exactly far enough that its envelope clears the dot envelope plus the
    optical gap (20 + 18 + 6 = 44). One resolver so the box solve's label-row
    clearance and the placement's mark seat can never disagree."""
    if not health_dot:
        return CARD_LABEL_MARK_INSET_R
    return CARD_LABEL_MARK + HEALTH_DOT_ENVELOPE + CARD_LABEL_MARK_HEALTH_GAP


# Hero register (the crown, 220x184): identity ROW over a centered display
# stack. h = 86 + (n-1)*33 + 32 — 3 display lines gives 184, exact.
CARD_LABEL_HERO_LABEL_DY = 40.0
CARD_LABEL_HERO_VALUE_DY = 86.0
CARD_LABEL_HERO_PITCH = 33.0
CARD_LABEL_HERO_PAD_BOTTOM = 32.0
CARD_LABEL_HERO_MARK = 14.0
"""The crown's identity mark (specimen: an r7 ring with an r2.2 core)."""
CARD_LABEL_HERO_MARK_GAP = 6.0


def card_label_voices(cfg: ParadigmDiagramConfig, *, hero: bool) -> tuple[MatrixVoice, MatrixVoice]:
    """(label, value) voices for the card+label anatomy's two registers. One
    resolver so the box solve, the placement, and the emitted CSS class can
    never disagree about which voice a run is measured in."""
    if hero:
        return cfg.hero_label_voice, cfg.hero_value_voice
    return cfg.card_label_voice, cfg.card_value_voice


def card_label_text(node: DiagramNode, *, hero: bool = False) -> str:
    """The label run as rendered. Case is a REGISTER fact, not a style: the
    standard label is a tracked kicker and uppercases (the specimen's ``CPU``
    at .14em — wide tracking is the small-caps convention); the crown's
    identity row is a signature line and keeps its authored case (the same
    specimen's ``apple silicon`` at .06em). Two voices, two conventions.

    Uppercasing happens in PYTHON, never via CSS ``text-transform`` — no
    rasterizer is obliged to honour it, and the measured string must be the
    stamped string or the box solve is measuring different text than renders."""
    return node.label if hero else node.label.upper()


def solve_card_label_box(
    node: DiagramNode,
    nch: DiagramNodeChassis,
    ch: DiagramTopologyChassis,
    cfg: ParadigmDiagramConfig,
    *,
    hero: bool = False,
    min_w: float = 0.0,
    has_mark: bool = False,
    health_dot: bool = False,
) -> tuple[float, float, tuple[str, ...]]:
    """Content-solved box for the card+label anatomy. Returns ``(w, h,
    value_lines)``.

    Width is the widest VALUE run plus the anatomy's symmetric pad, floored by
    the label row's own need — and, when a corner mark is present, by the
    clearance that keeps the label from running under it. The mark never
    contributes a content column: values start at the same x whether or not one
    resolves (a reserved left column is what makes an anatomy card+glyph).

    Height is pure rhythm: the value count times the specimen's pitch. Values
    never truncate AND never re-wrap: a value is a datum, so the width solve
    covers the widest authored line's full ink and only authored ``\\n``
    breaks the stack (pinned by the never-rewrap test). The wrap call below
    is the honesty backstop that keeps returned lines ≡ rendered lines, and
    the sliver guard's re-solve rides it."""
    label_voice, value_voice = card_label_voices(cfg, hero=hero)
    pad_x = CARD_LABEL_PAD_X
    label_w = measure_voice(card_label_text(node, hero=hero), label_voice)
    if hero:
        # The crown's identity row is a CENTERED group (mark + gap + text), so
        # both its halves ride inside the same symmetric envelope.
        mark_run = (CARD_LABEL_HERO_MARK + CARD_LABEL_HERO_MARK_GAP) if has_mark else 0.0
        row_need = 2 * pad_x + mark_run + label_w
    elif has_mark:
        # Label left-anchored at pad_x; the mark's left edge sits at
        # ``w - card_label_mark_inset_r(...)`` (the specimen's 36, or the
        # health-cleared 44), so the row needs the label to end one gap
        # before it.
        row_need = pad_x + label_w + CARD_LABEL_MARK_GAP + card_label_mark_inset_r(health_dot=health_dot)
    else:
        row_need = 2 * pad_x + label_w
    # Citations bound growth, never inflate (snug-width ruling — the same law
    # ``solve_card_box`` follows); ``min_w`` is the one true floor, carrying a
    # solver's content-derived aligned share.
    w_ceiling = max(nch.w, ch.w_max, ch.card_min_w)
    if hero:
        w_ceiling = max(w_ceiling, ch.node.w, ch.hero_min_w)
    want_w = max(row_need, 2 * pad_x + _desc_ink_w(node.desc, value_voice))
    # Never-truncate: clear the widest unbreakable word before wrapping.
    want_w = max(want_w, desc_word_w(node.desc, value_voice) + 2 * pad_x)
    w_ceiling = max(w_ceiling, math.ceil(max(row_need, want_w) / 2) * 2)
    # The CROWN is a plate: its width states RANK, not content extent, so an
    # EXPLICITLY CITED hero width is a floor here — the specimen's own crown
    # holds 220 around a 180 display stack, 40px of deliberate slack. The
    # citation must be the preset's, never the paradigm's default (the
    # ``hero_declared`` law ``hero_height_floor`` reads): an uncited crown that
    # inflated to the family archetype would eat the bilateral cell's width
    # budget and crowd its own wings. Satellites stay snug always.
    floor = max(min_w, hero_plate_w(ch) if hero else 0.0)
    w = max(floor, min(w_ceiling, math.ceil(want_w / 2) * 2))

    first_dy = CARD_LABEL_HERO_VALUE_DY if hero else CARD_LABEL_VALUE_DY
    pitch = CARD_LABEL_HERO_PITCH if hero else CARD_LABEL_VALUE_PITCH
    pad_bottom = CARD_LABEL_HERO_PAD_BOTTOM if hero else CARD_LABEL_PAD_BOTTOM
    label_dy = CARD_LABEL_HERO_LABEL_DY if hero else CARD_LABEL_LABEL_DY

    def at_width(width: float) -> tuple[float, tuple[str, ...]]:
        runs = tuple(wrap_text_lines(node.desc, width - 2 * pad_x, value_voice, max_lines=max(1, nch.max_desc_lines)))
        # A valueless card is just its label line — the same bottom air,
        # measured from the label baseline instead of the value stack.
        block = first_dy + (len(runs) - 1) * pitch + pad_bottom if runs else label_dy + pad_bottom
        # Height is the anatomy's OWN rhythm, snug: a paradigm archetype h
        # is the LEGACY card's citation and never floors this register (the
        # comparison cell's 380x160 panel archetype squared a 92-rhythm card
        # into 68px of dead bottom via the sliver guard). Only a
        # spec-DECLARED hero height pins — the author's own citation
        # (``hero_declared``, the same law every other crown floor reads).
        floor_h = hero_height_floor(ch) if hero else 0.0
        return max(block, floor_h), runs

    h, lines = at_width(w)
    return apply_sliver_guard((w, h, lines), ceiling=w_ceiling, resolve=at_width)


SLIVER_GUARD_PASSES = 4
"""Iteration cap for the wrap guard. Widening lets wrapped lines rejoin, which
shortens the stack, so width and height converge — but a card whose ceiling is
too tight can oscillate, and an unbounded loop in a layout solver is never
worth the last pixel."""


def apply_sliver_guard(
    box: tuple[float, float, tuple[str, ...]],
    *,
    ceiling: float,
    resolve: Callable[[float], tuple[float, tuple[str, ...]]],
) -> tuple[float, float, tuple[str, ...]]:
    """A card may never become a SLIVER: if its text wraps into something
    taller than it is wide, the box widens instead of stacking (owner ruling —
    the wrap guard). ``resolve`` re-solves height and lines at a candidate
    width; the box is returned untouched when it already reads landscape, so a
    card that never tripped the guard stays byte-identical.

    The portrait HEAD anatomy is exempt BY CONSTRUCTION — it is deliberately
    taller than wide (frame-engine-hub's 124x124 tiles, tree rows) — so this
    guard is only ever reached from the label-row and card+label families."""
    w, h, lines = box
    for _ in range(SLIVER_GUARD_PASSES):
        if h <= w or w >= ceiling:
            break
        w = min(ceiling, math.ceil(h / 2) * 2)
        h, lines = resolve(w)
    return w, h, lines


def solve_node_box(
    ctx: SolverContext,
    node: DiagramNode,
    index: int,
    *,
    hero: bool | None = None,
    chassis: DiagramNodeChassis | None = None,
    chassis_class: str = "",
    topo_chassis: DiagramTopologyChassis | None = None,
    min_w: float | None = None,
    circle_r: float | None = None,
    default_style: str = NodeStyle.CARD.value,
    force_card: bool = False,
    h_floor: float | None = None,
    bullet_lead: float = 0.0,
) -> tuple[float, float, tuple[str, ...]]:
    """The positions-only solver seam's SIZING half: every
    topology's per-node content-solved box collapses to this one call, so a
    solver can no longer under-feed ``solve_card_box`` with
    a mismatched chassis, hero flag, or mark advance — the three truncation
    bugs this release shared were exactly that class of bug, at ~10 call
    sites. Internally derives style (``style_of``), hero (``node.role``),
    the node chassis (``ch.hero`` for a hero, ``ch.node`` otherwise;
    ``chassis_class="node2"`` selects the ring-2/depth-tier class — tree's
    deepest row, tree-radial's outer ring — the one POSITIONAL chassis
    choice a solver still owns), the mark advance (``mark_w_for``), and the
    snug width (``min_w`` only carries a solver's content-derived aligned
    share; width citations act as ceilings, never floors).

    ``hero`` is a caller override for the two sites whose CURRENT behavior
    is deliberately not role-derived (preserved verbatim, not silently
    fixed — see the seam-conversion report): the hub compass center always
    sizes hero-chassis regardless of its resolved role, and axial's nucleus
    floor intentionally under-sizes as a plain satellite. ``circle_r``
    overrides the hero/default radius pick for a topology whose glyph-circle
    anatomy reads a different chassis field (the hub center's
    ``hero_circle_r_hub``) or never scales for a hero at all (dag/state-
    machine's rank/pill circles). ``topo_chassis`` overrides the topology
    chassis fed to ``solve_card_box`` (axial's widened per-axis ``w_max``
    clone) while the node chassis stays the plain default.

    Dispatches GLYPH_CIRCLE -> its chassis diameter (no content measurement),
    else CARD/CARD+GLYPH/TEXT -> ``solve_card_box``. ``force_card`` skips style
    dispatch entirely (lanes, and linear's stack/comparison/tree never
    branch on a node's declared style — they always measure/render a card,
    so the box must match ``place_node``'s matching ``force_card``, never a
    pill/circle box under a card render). Returns ``(w, h,
    wrapped_desc_lines)`` — lines is always ``()`` for pill/circle."""
    ch = ctx.ch
    # ``style`` is the TRUE resolved anatomy regardless of ``force_card`` —
    # mark_w_for still needs it to tell card+glyph from plain card (a forced
    # card render can still carry a glyph mark); only the SHAPE dispatch
    # below (pill / glyph-circle vs the default card box) is suppressed.
    style = style_of(node, ctx.spec, ch, default=default_style)
    is_hero = (node.role is NodeRole.HERO) if hero is None else hero
    if chassis is not None:
        nch = chassis
    elif chassis_class == "node2":
        nch = ch.node2
    else:
        nch = ch.hero if is_hero else ch.node
    if not force_card and style == NodeStyle.GLYPH_CIRCLE.value:
        r = circle_r if circle_r is not None else (ch.hero_circle_r if is_hero else ch.circle_r)
        return 2 * r, 2 * r, ()
    # Snug-width ruling: the only width FLOOR is a caller's content-derived
    # aligned share (``min_w`` — a rank/ring re-solve at its widest
    # sibling's own solve). Crowns solve alone; every hand-file width
    # citation (``hero.w``/``hero_min_w``/``card_min_w``) bounds growth as
    # a CEILING inside ``solve_card_box``, never inflating a card past its
    # own ink.
    resolved_min_w = 0.0 if is_hero else (min_w or 0.0)
    if style == NodeStyle.CARD_LABEL.value:
        # card+label owns its own rhythm end to end (label kicker over a value
        # stack), so it never consults ``node_anatomy``. ``force_card`` is a
        # rectangular-SILHOUETTE constraint used by lanes/axial/convergence;
        # card+label already is a rectangular card, so suppressing its internal
        # anatomy here silently changed the caller's explicit style and could
        # make placement overflow a box measured as the legacy card.
        # The CROWN register is a seat fact bounded by a balance law, never a
        # bare role fact: only a center seat (``ch.crown_register``) restacks
        # the hero as an identity row over a display block, and only while
        # the crown stays inside the specimen's dominance band of its
        # standard siblings (``crown_within_band``) — past it, the hero
        # keeps the standard register with its hero chassis floors (rx, min
        # height) as the dress.
        return solve_card_label_box(
            node,
            nch,
            ch,
            ctx.cfg,
            hero=is_hero and ch.crown_register and crown_within_band(ctx, node, index),
            min_w=resolved_min_w,
            has_mark=bool(node_glyph_id(node, ctx.glyph_registry)),
            health_dot=node.health is not NodeHealth.OK,
        )
    effective_anatomy = node_anatomy_of(ctx.spec, ch)
    if (
        not force_card
        and effective_anatomy == "head"
        and style in (NodeStyle.CARD.value, NodeStyle.CARD_GLYPH.value)
        and not node.embed_dims
    ):
        # Chips ride the portrait column too (centered beneath the desc) —
        # a chips-bearing stage must not fall through to the label-row card
        # while its siblings render portrait (the one-off row card read as a
        # different species inside a head pipeline). A HEAD crown keeps its
        # family frame (the tree-radial hub's 104 portrait archetype).
        head_min = max(resolved_min_w, nch.w) if is_hero else resolved_min_w
        return solve_head_box(node, nch, cfg=ctx.cfg, min_w=head_min, hero=is_hero)
    # Hero enlargement is CONTENT-carried (name/desc/chips at hero voices):
    # the specimens disagree on a chassis floor (cicd-gate crowns its
    # deploy at 210x112 while kernel-bottleneck keeps a near-uniform 150x60 hero),
    # so the chassis hero block supplies voices and ceilings, never a width
    # floor — a ring-only hero at sibling size is a legal figure.
    topo = topo_chassis if topo_chassis is not None else ch
    mw = mark_w_for(style, node)
    if mw and nch.glyph_w:
        mw = nch.glyph_w
    return solve_card_box(
        node,
        nch,
        topo,
        ctx.cfg,
        ctx.mono_triggers,
        hero=is_hero,
        min_w=resolved_min_w,
        mark_w=mw,
        h_floor=h_floor,
        bullet_lead=bullet_lead,
    )
