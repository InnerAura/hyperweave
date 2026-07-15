"""Shared diagram chrome: header/footer text and node placement.

Every text run is measured (per-font LUTs via the matrix voice helpers) and
truncated/wrapped BEFORE placement — templates stamp finished strings. The
voice-class registry below is the single source coupling placement classes
to paradigm voices: the solver measures with the same family/size/weight
tuple the defs CSS renders.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram.records import DiagramHeader, DiagramText, GlyphArt, NodePlacement
from hyperweave.compose.diagram.sizing import (
    BULLET_DESC_RIGHT_GAP,
    CHIP_GAP,
    CHIP_H,
    CHIP_RX,
    DOT_MARK_W,
    GLYPH_MARK_W,
    HEAD_GLYPH_GAP,
    HEAD_GLYPH_SIZE,
    HEAD_PAD_X,
    VOICE_CLASSES,
    anchor_pads,
    card_ink_w,
    head_pad_x,
    label_cls_for,
    label_desc_gap_for,
    mark_lead,
    mark_w_for,
    node_anatomy_of,
    role_of,
    solve_card_box,
    solve_card_w,
    solve_chip_box,
    solve_node_box,
    style_of,
    voice_for,
)
from hyperweave.compose.matrix.cells import (
    glyph_mark_placement,
    measure_voice,
    resolve_glyph_mode,
    truncate_to_width,
    wrap_text_lines,
)
from hyperweave.compose.spatial_records import RectSpec
from hyperweave.core.diagram import NodeHealth, NodeRole, NodeStyle
from hyperweave.core.matrix import GlyphTint

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from hyperweave.compose.diagram.wiring import SolverContext
    from hyperweave.core.diagram import DiagramNode, DiagramSpec
    from hyperweave.core.paradigm import DiagramNodeChassis, DiagramTopologyChassis, ParadigmDiagramConfig

# Re-exported so existing call sites keep importing the voice registry, the
# measurement helpers, and the mark-width constants from ``chrome``; the
# definitions live one layer down in ``sizing`` (placement depends on
# measurement, not the reverse).
__all__ = [
    "DOT_MARK_W",
    "GLYPH_MARK_W",
    "VOICE_CLASSES",
    "card_ink_w",
    "glyph_slot_builder",
    "label_cls_for",
    "mark_w_for",
    "measure_caption",
    "measure_footer",
    "measure_masthead",
    "node_glyph_id",
    "place_card",
    "place_circle",
    "place_head",
    "place_node",
    "resolve_node_glyph",
    "role_of",
    "solve_card_box",
    "solve_card_w",
    "solve_node_box",
    "style_of",
    "voice_for",
]


def measure_masthead(
    spec: DiagramSpec, ch: DiagramTopologyChassis, cfg: ParadigmDiagramConfig, wrap_budget: float
) -> tuple[DiagramHeader, float, float]:
    """The masthead region's content, measured in REGION-LOCAL coordinates
    (sec 2: no fixed y — the region stack decides where the block lands).

    Returns ``(header, w, h)`` with every text at local (0-anchored) coords.
    The wrap law: the title wraps to TWO lines against the wrap budget
    before any ellipsis — ellipsis only when a single wrapped line still
    exceeds the budget (the region genuinely cannot hold the text). The
    measured width may EXCEED the budget only through the subtitle's own
    single-line minimum; the stack then widens the canvas rather than
    truncating chrome while canvas sits empty.
    """
    if ch.header_mode == "none" or (not spec.title and not spec.subtitle):
        return DiagramHeader(), 0.0, 0.0
    title_v = cfg.title_voice
    sub_v = cfg.subtitle_voice
    title_pitch = title_v.size + 6.0
    y = 0.0
    w = 0.0
    title_lines: list[DiagramText] = []
    if spec.title:
        lines = wrap_text_lines(spec.title, wrap_budget, title_v, max_lines=2)
        for line in lines:
            y += title_pitch
            title_lines.append(DiagramText(x=0.0, y=y, text=line, cls="title"))
            w = max(w, measure_voice(line, title_v))
    subtitle = None
    if spec.subtitle:
        sub_lines = wrap_text_lines(spec.subtitle, wrap_budget, sub_v, max_lines=2)
        first = sub_lines[0] if sub_lines else spec.subtitle
        y += sub_v.size + (8.0 if title_lines else 4.0)
        subtitle = DiagramText(x=0.0, y=y, text=first, cls="sub")
        w = max(w, measure_voice(first, sub_v))
    header = DiagramHeader(
        title=title_lines[0] if title_lines else None,
        subtitle=subtitle,
        title_lines=tuple(title_lines),
    )
    return header, w, y + 6.0


def measure_caption(spec: DiagramSpec, cfg: ParadigmDiagramConfig) -> tuple[DiagramText | None, float, float]:
    """Caption chrome (sec 3, every specimen): ONE sentence at the base —
    the host page owns the heading. Subtitle wins (it reads as prose); title
    falls back; centered by the region stack via align. Rides the dedicated
    14px-Inter ``caption_voice`` (the specimen ``-cap``), never the 11px
    subtitle or the 7px mono foot."""
    text = spec.subtitle or spec.title
    if not text:
        return None, 0.0, 0.0
    # Region slot = the caption line box (14px * ~0.96 ≈ 13.4) + a thin pad; the
    # foot band holds the SAME height it did for the retired 11px subtitle so a
    # bigger, more legible caption voice does not perturb the footer clearance.
    h = cfg.caption_voice.size + 3.0
    return (
        DiagramText(x=0.0, y=h - 3.0, text=text, cls="cap"),
        measure_voice(text, cfg.caption_voice),
        h,
    )


def measure_footer(
    spec: DiagramSpec, slug: str, ch: DiagramTopologyChassis, cfg: ParadigmDiagramConfig
) -> tuple[DiagramText | None, float, float]:
    """The footer region's brand line at REGION-LOCAL coordinates."""
    if ch.footer_h <= 0:
        return None, 0.0, 0.0
    middle = (spec.notes or slug.replace("-", " ")).upper()
    text = f"HYPERWEAVE · {middle} · INNERAURA LABS"
    h = cfg.foot_voice.size + 4.0
    return DiagramText(x=0.0, y=h - 2.0, text=text, cls="ft"), measure_voice(text, cfg.foot_voice), h


def resolve_node_glyph(
    glyph_id: str,
    registry: Mapping[str, Any] | None,
    tint: GlyphTint,
    *,
    cx: float,
    cy: float,
    size: float,
    accent_index: int = -1,
) -> GlyphArt | None:
    """The node identity slot, riding the matrix glyph system wholesale:
    ``glyph_mark_placement`` builds the mark (registry entry + tint
    selection, degrading full -> gradient -> brand -> hue -> ink); the
    resolved mode lands on ``GlyphArt.tint`` for the payload's rendered
    record. ``accent_index`` (-1 = none) is this node's flow-palette slot
    (``ctx.node_accents[index]`` — Semantic Chromatics: ``node.accent`` or
    the spine cycle assignment) — a generic stroke-only mark with no
    color_paths/gradient/brand_color takes this hue instead of ink; see
    ``resolve_glyph_mode`` for the canon citation."""
    if not glyph_id or registry is None:
        return None
    entry = registry.get(glyph_id)
    box = RectSpec(x=cx - size / 2, y=cy - size / 2, w=size, h=size)
    mark = glyph_mark_placement(
        entry,
        glyph_id=glyph_id,
        kind_row=-1,
        col=-1,
        box=box,
        cx=cx,
        cy=cy,
        size=size,
        tint=tint,
        accent_index=accent_index,
    )
    return GlyphArt(
        paths=mark.glyph_paths,
        transform=mark.glyph_transform,
        fill=mark.glyph_fill,
        opacity=mark.glyph_opacity,
        fill_rule=mark.glyph_fill_rule,
        gradient=mark.glyph_gradient,
        stroke_w=mark.glyph_stroke_w,
        tint=resolve_glyph_mode(entry or {}, tint, has_flow_hue=accent_index >= 0),
        cx=cx,
        cy=cy,
        size=size,
        glyph_id=glyph_id,
        accent_index=mark.glyph_accent_index,
    )


def node_glyph_id(node: DiagramNode, registry: Mapping[str, Any] | None) -> str:
    """The identity-slot resolution ladder: brand ``glyph`` -> semantic
    ``kind`` (core set) -> nothing. First id that RESOLVES in the merged
    registry wins; neither resolving means no mark at all (icon-or-nothing
    — an unknown slug never renders an empty group). A ``kind`` prefers its
    namespaced ``kind:<slug>`` entry so generic words a brand shadows
    (shield, star, braces) still reach the generic mark."""
    if registry is None:
        return ""
    if node.glyph and node.glyph in registry:
        return node.glyph
    if node.kind:
        for gid in (f"kind:{node.kind}", node.kind):
            if gid in registry:
                return gid
    return ""


def glyph_slot_builder(
    glyph_id: str,
    registry: Mapping[str, Any] | None,
    tint: GlyphTint,
    size: float = 16.0,
    accent_index: int = -1,
) -> Callable[[float, float], GlyphArt | None]:
    """Deferred mark construction for the card+glyph anatomy: ``place_card``
    calls the builder with the dot slot's final center (label-line aligned),
    so anchoring lives in ONE place instead of every solver call site."""

    def build(cx: float, cy: float) -> GlyphArt | None:
        return resolve_node_glyph(glyph_id, registry, tint, cx=cx, cy=cy, size=size, accent_index=accent_index)

    return build


def place_head(
    *,
    index: int,
    node: DiagramNode,
    x: float,
    y: float,
    w: float,
    h: float,
    rx: float,
    cfg: ParadigmDiagramConfig,
    accent_index: int,
    glyph_builder: Callable[[float, float], GlyphArt | None] | None,
    max_desc_lines: int = 0,
    desc_pitch: float = 16.0,
    with_chips: bool = False,
    pad_x: float = HEAD_PAD_X,
    pad_y: float | None = None,
    glyph_gap: float = HEAD_GLYPH_GAP,
    label_desc_gap: float | None = None,
) -> NodePlacement:
    """Sequence participant HEAD anatomy (auth-sequence): a compact near-square
    identity card — an identity glyph centered ABOVE the name, the name
    centered below — distinct from the card/hero label-row anatomies (dot +
    left label, or hero name+desc) every other topology renders. The
    protagonist differs only in ring/plate (the template's role-driven
    bg_cls) and an accent-tinted glyph; every head shares this one stacked
    layout. The glyph block + name line metric-center in the card (G2) when
    ``pad_y`` is undeclared (``None``, the kit default — icon-or-nothing
    centers the name alone); a declared ``pad_y`` (the hub compass hero)
    anchors the stack at that FIXED top pad instead, so a chassis pin taller
    than the snug stack widens ``glyph_gap`` rather than the pad — falling
    back to centering if the declared pad would overflow the box.
    ``label_desc_gap`` is the caller's resolved value (``sizing.
    label_desc_gap_for``, mirroring ``solve_head_box``) — undeclared
    (``None``) keeps the paradigm-wide default, exactly as before this
    param existed."""
    role = role_of(node)
    box = RectSpec(x=x, y=y, w=w, h=h, rx=rx)
    name_cls = "hname" if role == "hero" else "name"
    voice = voice_for(cfg, name_cls)
    desc_voice = cfg.hero_desc_voice if role == "hero" else cfg.desc_voice
    desc_cls = "hdesc" if role == "hero" else "ndesc"
    name_text = truncate_to_width(node.label, w - 2 * pad_x, voice)
    ar, dr = cfg.text_ascent_ratio, cfg.text_descent_ratio
    ldg = cfg.label_desc_gap if label_desc_gap is None else label_desc_gap
    name_h = voice.size * (ar + dr)
    lines = wrap_text_lines(node.desc, w - 2 * pad_x, desc_voice, max_lines=max_desc_lines) if max_desc_lines else []
    text_block_h = name_h
    if lines:
        text_block_h += ldg + desc_voice.size * (ar + dr) + (len(lines) - 1) * desc_pitch
    if with_chips and node.chips:
        # Chip-row on the portrait column — same pills, centered on the
        # card axis, measured into the block exactly as solve_head_box sizes.
        # Auto-dispatched portrait CARDS host chips; the sequence participant
        # head (explicit anatomy) is a fixed glyph-above-name token with no
        # chip surface — the idiom sweep pins that distinction.
        text_block_h += ldg + CHIP_H
    glyph_art: GlyphArt | None = None
    if glyph_builder is not None:
        block_h = HEAD_GLYPH_SIZE + glyph_gap + text_block_h
        top = y + pad_y if pad_y is not None and 2 * pad_y + block_h <= h else y + (h - block_h) / 2
        glyph_cy = top + HEAD_GLYPH_SIZE / 2
        glyph_art = glyph_builder(x + w / 2, glyph_cy)
        name_top = top + HEAD_GLYPH_SIZE + glyph_gap
    else:
        top = y + (h - text_block_h) / 2
        name_top = top
    if glyph_art is not None and role == "hero" and not glyph_art.gradient:
        # The protagonist's identity mark carries the SAME accent as its
        # ring and lifeline (auth-sequence: seq-gia vs seq-gi) — every other
        # head keeps the ink glyph.
        glyph_art = replace(glyph_art, fill="var(--dna-signal)")
    name_baseline = name_top + voice.size * ar
    label = DiagramText(x=x + w / 2, y=name_baseline, text=name_text, cls=name_cls, anchor="middle")
    first_desc = name_baseline + voice.size * dr + ldg + desc_voice.size * ar
    desc_lines = tuple(
        DiagramText(x=x + w / 2, y=first_desc + i * desc_pitch, text=line, cls=desc_cls, anchor="middle")
        for i, line in enumerate(lines)
    )
    head_chips: tuple[tuple[RectSpec, ...], tuple[DiagramText, ...]] = ((), ())
    if with_chips and node.chips:
        text_bottom = (
            first_desc + (len(lines) - 1) * desc_pitch + desc_voice.size * dr
            if lines
            else name_baseline + voice.size * dr
        )
        head_chips = _chip_row(node.chips, cfg, text_bottom + ldg, center=x + w / 2)
    return NodePlacement(
        index=index,
        node_id=node.id,
        shape="rect",
        box=box,
        role=role,
        stroke_width=1.5 if role == "hero" else 1.0,
        stroke_dasharray="",
        accent_index=accent_index,
        label=label,
        desc_lines=desc_lines,
        glyph=glyph_art,
        chip_boxes=head_chips[0],
        chip_texts=head_chips[1],
    )


def _text_block(
    cfg: ParadigmDiagramConfig,
    *,
    box_y: float,
    box_h: float,
    label_size: float,
    desc_size: float,
    desc_lines: int,
    desc_pitch: float,
    label_desc_gap: float,
    extra_h: float = 0.0,
) -> tuple[float, float, int]:
    """Metric-centered vertical layout for a node's text block (G2).

    Returns (label_baseline, first_desc_baseline, kept_desc_lines). The
    block — label line + gap + desc lines (+ ``extra_h``: the chip row a
    chipped card appends, so the WHOLE group centers) — is measured with
    line metrics and centered in the box; desc lines DROP (never clip)
    until every baseline + descender clears the box minus ``min_pad_y``.
    ``label_desc_gap`` is the caller's resolved value (``sizing.
    label_desc_gap_for``) — a chassis override or the paradigm default —
    so this centering agrees with ``solve_card_box``'s content-solved
    height, which measures the same gap."""
    ar, dr = cfg.text_ascent_ratio, cfg.text_descent_ratio
    avail = box_h - 2 * cfg.min_pad_y
    kept = desc_lines
    while True:
        block = label_size * (ar + dr) + extra_h
        if kept:
            block += label_desc_gap + desc_size * (ar + dr) + (kept - 1) * desc_pitch
        # Epsilon guards the exact-fit card: solve_card_box computes the same
        # sum in a different operation order, so a height solved to fit can
        # land ~1e-14 over and silently drop the desc it was sized for.
        if block <= avail + 1e-6 or kept == 0:
            break
        kept -= 1
    top = box_y + (box_h - block) / 2
    label_baseline = top + label_size * ar
    first_desc_baseline = label_baseline + label_size * dr + label_desc_gap + desc_size * ar
    assert label_baseline + label_size * dr <= box_y + box_h - cfg.min_pad_y + 0.51, "label clips its card"
    if kept:
        last = first_desc_baseline + (kept - 1) * desc_pitch
        assert last + desc_size * dr <= box_y + box_h - cfg.min_pad_y + 0.51, "desc clips its card"
    return label_baseline, first_desc_baseline, kept


def _slot_vertical(
    cfg: ParadigmDiagramConfig,
    *,
    box_y: float,
    box_h: float,
    label_size: float,
    desc_size: float,
    desc_lines: int,
    desc_pitch: float,
    label_desc_gap: float,
    trailing_rows: tuple[float, ...] = (),
) -> tuple[float, float, int, tuple[float, ...], float]:
    """Vertical slot rhythm for a card (the specimen slot model).

    Returns ``(label_baseline, first_desc_baseline, kept_desc,
    trailing_tops, id_block_cy)``.

    No trailing rows (chips/embed): the identity block (label + descs)
    metric-centers in the box — byte-identical to ``_text_block``. WITH
    trailing rows: the identity block TOP-anchors and the trailing rows
    BOTTOM-anchor, the card's vertical slack beyond snug content distributed
    evenly across three gaps — the top pad, the identity→trailing gap, and the
    bottom pad. The specimen law: a tall card spreads its slack (comparison
    hero's 79px splits ~evenly top/gap/bottom), never crams content into the
    vertical middle with the chips glued 6px under the desc.

    ``label_desc_gap`` is the caller's resolved value (``sizing.
    label_desc_gap_for``), shared with ``_text_block`` and this function's
    own trailing-row math so every gap in the card reads one chassis-tuned
    air, never a mix of the override and the paradigm default.

    ``id_block_cy`` is the vertical center of the identity block (label +
    kept descs) — where the glyph mark rides, so it stays on the name row
    instead of floating to the card center on a chip-bottomed card."""
    ar, dr = cfg.text_ascent_ratio, cfg.text_descent_ratio
    if not trailing_rows:
        lb, db, kept = _text_block(
            cfg,
            box_y=box_y,
            box_h=box_h,
            label_size=label_size,
            desc_size=desc_size,
            desc_lines=desc_lines,
            desc_pitch=desc_pitch,
            label_desc_gap=label_desc_gap,
        )
        label_top = lb - label_size * ar
        last_desc_bottom = (db + (kept - 1) * desc_pitch + desc_size * dr) if kept else (lb + label_size * dr)
        return lb, db, kept, (), (label_top + last_desc_bottom) / 2
    trailing_content_h = sum(trailing_rows) + label_desc_gap * (len(trailing_rows) - 1)
    kept = desc_lines
    while True:
        id_h = label_size * (ar + dr)
        if kept:
            id_h += label_desc_gap + desc_size * (ar + dr) + (kept - 1) * desc_pitch
        snug = 2 * cfg.min_pad_y + id_h + label_desc_gap + trailing_content_h
        if snug <= box_h + 1e-6 or kept == 0:
            break
        kept -= 1
    third = max(0.0, box_h - snug) / 3.0
    pad = cfg.min_pad_y + third
    label_base = box_y + pad + label_size * ar
    first_desc_base = label_base + label_size * dr + label_desc_gap + desc_size * ar
    trailing_first_top = box_y + box_h - pad - trailing_content_h
    tops: list[float] = []
    cursor = trailing_first_top
    for i, row_h in enumerate(trailing_rows):
        tops.append(cursor)
        cursor += row_h + label_desc_gap
        _ = i
    label_top = label_base - label_size * ar
    last_desc_bottom = (
        (first_desc_base + (kept - 1) * desc_pitch + desc_size * dr) if kept else label_base + label_size * dr
    )
    return label_base, first_desc_base, kept, tuple(tops), (label_top + last_desc_bottom) / 2


def _embed_box(node: DiagramNode, x: float, w: float, top: float, pad_x: float) -> RectSpec | None:
    """sec 12.1: the inner artifact's display box, centered on the card axis
    beneath the text/chip block (a mini-canvas centers; it never keys to the
    shared text edge). If the card came back narrower than the display dims
    (a proportional-width solver), the embed rescales to fit — aspect held,
    never an overflow."""
    if not node.embed_dims:
        return None
    ew, eh = node.embed_dims
    avail = w - 2 * pad_x
    if ew > avail > 0:
        s = avail / ew
        ew, eh = ew * s, eh * s
    return RectSpec(x=x + (w - ew) / 2, y=top, w=ew, h=eh)


def _chip_row(
    chips: tuple[str, ...],
    cfg: ParadigmDiagramConfig,
    row_top: float,
    *,
    left: float | None = None,
    center: float | None = None,
) -> tuple[tuple[RectSpec, ...], tuple[DiagramText, ...]]:
    """Chip-row (chrome vocabulary): one row of inline pills. Metrics
    mirror solve_card_box's row math so the solved height already holds
    them. Plain cards left-align to the shared content edge; heroes center
    on the card axis — same pills, same voice, either anchor."""
    widths = [solve_chip_box(chip, cfg)[0] for chip in chips]
    row_w = sum(widths) + CHIP_GAP * (len(chips) - 1)
    cxp = (center - row_w / 2) if center is not None else (left or 0.0)
    boxes: list[RectSpec] = []
    texts: list[DiagramText] = []
    for chip, cw in zip(chips, widths, strict=True):
        boxes.append(RectSpec(x=cxp, y=row_top, w=cw, h=CHIP_H, rx=CHIP_RX))
        texts.append(
            DiagramText(
                x=cxp + cw / 2,
                y=row_top + CHIP_H / 2 + cfg.tag_voice.size * cfg.text_ascent_ratio / 2,
                text=chip,
                cls="tag",
                anchor="middle",
            )
        )
        cxp += cw + CHIP_GAP
    return tuple(boxes), tuple(texts)


def place_card(
    *,
    index: int,
    node: DiagramNode,
    x: float,
    y: float,
    nch: DiagramNodeChassis,
    cfg: ParadigmDiagramConfig,
    accent_index: int,
    mono_triggers: list[str],
    muted_dash: str,
    w_override: float = 0.0,
    h_override: float = 0.0,
    glyph_builder: Callable[[float, float], GlyphArt | None] | None = None,
    bullet_lead: float = 0.0,
    left_align: bool = False,
) -> NodePlacement:
    """A rectangular card: glyph column + left-aligned label/desc (default,
    muted — muted quiets the voices), hero or standard.
    ``glyph_builder`` (the card+glyph anatomy) is called with the mark's
    final center — the dot slot, optically aligned to the LABEL line, never
    the card center — so the identity mark can't collide with desc rows and
    call sites can't mis-anchor it. Vertical placement is metric-centered
    (G2): the text block measures its line boxes and centers in the card;
    content always fits — desc lines drop before anything clips.
    ``h_override`` (0 = chassis ``h``, byte-identical to pre-G3-extension
    output) takes the solved height from ``solve_card_box`` so a wrapped desc
    renders in-card instead of dropping."""
    role = role_of(node)
    w = w_override or nch.w
    h = h_override or nch.h
    box = RectSpec(x=x, y=y, w=w, h=h, rx=nch.rx)
    label_desc_gap = label_desc_gap_for(nch, cfg)
    if role == "hero":
        # The hero slot model: a glyph column, then name + subtitle sharing ONE
        # left text edge (the desc keys to the name, never the glyph gutter),
        # chips BOTTOM-anchored in the glyph column, and the glyph riding the
        # identity BLOCK center so a chip-bottomed crown keeps its mark on the
        # name. The block LEFT-ANCHORS at the chassis ``glyph_inset_x``
        # (content-anchor law) — pp-convergence-flow's 280x120 crown seats its
        # glyph at card+18.8 / text at card+56 with the slack pooled right,
        # and pp-gateway-refined's single-row crown measures the same
        # (~21/57); per-hero centering made the text column a function of the
        # crown's own slack instead of a chassis fact.
        hero_mark_w = (nch.glyph_w or GLYPH_MARK_W) if glyph_builder is not None else 0.0
        hero_lead = mark_lead(hero_mark_w, nch)
        # Name and desc share the text column: both budgets subtract the
        # lead, and the desc may run to the slim gap (the std-card law) —
        # mirrors solve_card_box exactly.
        desc_max_w = w - nch.glyph_inset_x - hero_lead - BULLET_DESC_RIGHT_GAP
        name_budget = w - anchor_pads(nch) - hero_lead
        lines = wrap_text_lines(node.desc, desc_max_w, cfg.hero_desc_voice, max_lines=nch.max_desc_lines)
        trailing_rows = ((CHIP_H,) if node.chips else ()) + ((node.embed_dims[1],) if node.embed_dims else ())
        label_base, desc_base, kept, trailing_tops, glyph_cy = _slot_vertical(
            cfg,
            box_y=y,
            box_h=h,
            label_size=cfg.hero_name_voice.size,
            desc_size=cfg.hero_desc_voice.size,
            desc_lines=len(lines),
            desc_pitch=nch.desc_line_pitch,
            label_desc_gap=label_desc_gap,
            trailing_rows=trailing_rows,
        )
        name_text = truncate_to_width(node.label, name_budget, cfg.hero_name_voice)
        # Name AND desc share the text column (text_left = group_left +
        # lead); chips ride the glyph column (group_left). The column is a
        # chassis fact: anchored at ``glyph_inset_x``, never re-derived from
        # this crown's own ink.
        group_left = x + nch.glyph_inset_x
        text_left = group_left + hero_lead
        glyph_art = glyph_builder(group_left + hero_mark_w / 2, glyph_cy) if glyph_builder is not None else None
        if glyph_art is not None and not glyph_art.gradient and glyph_art.tint == GlyphTint.INK:
            # The nucleus glyph carries the ACCENT on both faces
            # (the language specimen's hero-glyph class) — brand/full tints keep their color.
            glyph_art = replace(glyph_art, fill="var(--dna-signal)")
        label = DiagramText(x=text_left, y=label_base, text=name_text, cls="hname", anchor="start")
        desc_lines = tuple(
            DiagramText(x=text_left, y=desc_base + i * nch.desc_line_pitch, text=line, cls="hdesc", anchor="start")
            for i, line in enumerate(lines[:kept])
        )
        hero_chips: tuple[tuple[RectSpec, ...], tuple[DiagramText, ...]] = ((), ())
        ti = 0
        if node.chips:
            # The crown's chip row CENTERS on the card axis (the
            # observability hand crown seats its row at a symmetric ~8px) —
            # unlike a std card's row, which rides the glyph column.
            hero_chips = _chip_row(node.chips, cfg, trailing_tops[ti], center=x + w / 2)
            ti += 1
        embed_top = trailing_tops[ti] if node.embed_dims else 0.0
        hero_embed = _embed_box(node, x, w, embed_top, nch.pad_x) if node.embed_dims else None
        return NodePlacement(
            index=index,
            node_id=node.id,
            shape="rect",
            embed_box=hero_embed,
            chip_boxes=hero_chips[0],
            chip_texts=hero_chips[1],
            box=box,
            role=role,
            stroke_width=1.5,
            stroke_dasharray="",
            accent_index=accent_index,
            label=label,
            desc_lines=desc_lines,
            glyph=glyph_art,
        )
    # Icon-or-nothing: the identity slot carries the provided glyph, or a
    # Semantic Chromatics: the accent lives on the TITLE (prototype binding),
    # not a bullet dot — the diagram frame emits no default decoration dots.
    # A glyph still takes the mark slot; an accented, glyph-less card carries
    # its accent through the title text, so there is no lead space to reserve.
    mark_w = (nch.glyph_w or GLYPH_MARK_W) if glyph_builder is not None else 0.0
    lead = mark_lead(mark_w, nch)
    label_cls = label_cls_for(node, mono_triggers) if role == "default" else "mname"
    label_voice = voice_for(cfg, label_cls)
    # Bulleted cards wrap descs against the specimen's asymmetric envelope
    # (content-left to a slim right gap) — mirrors solve_card_box exactly. The
    # default desc is indented by the glyph lead, so its wrap budget subtracts it
    # (the term the box was sized against — the overflow fix, both sides agree).
    desc_budget = (
        (w - nch.pad_x - BULLET_DESC_RIGHT_GAP)
        if bullet_lead
        else (w - nch.glyph_inset_x - lead - BULLET_DESC_RIGHT_GAP)
    )
    lines = wrap_text_lines(node.desc, desc_budget, cfg.desc_voice, max_lines=nch.max_desc_lines)
    trailing_rows = ((CHIP_H,) if node.chips else ()) + ((node.embed_dims[1],) if node.embed_dims else ())
    label_base, desc_base, kept, trailing_tops, glyph_cy = _slot_vertical(
        cfg,
        box_y=y,
        box_h=h,
        label_size=label_voice.size,
        desc_size=cfg.desc_voice.size,
        desc_lines=len(lines),
        desc_pitch=nch.desc_line_pitch,
        label_desc_gap=label_desc_gap,
        trailing_rows=trailing_rows,
    )
    # The bulleted anatomy keeps its own symmetric pad_x envelope for the
    # label budget (its band widths were clamped against it) — the anchor
    # envelope governs card/card+glyph anatomies only.
    label_budget = (w - 2 * nch.pad_x - bullet_lead) if bullet_lead else (w - anchor_pads(nch) - lead)
    label_text = truncate_to_width(node.label, label_budget, label_voice)
    kept_lines = lines[:kept]
    # Content-anchor law: name and desc share ONE text column (specimen slot
    # model) — the desc indents to group_left + lead, right under the name,
    # never flush under the glyph — and the column is a CHASSIS fact, seated
    # at ``glyph_inset_x`` with slack pooling right (primer_diagram_language's
    # providers: glyph card+22 / text card+60, uniform down the whole column;
    # pp-dag-serving-v2/pp-gateway-refined measure the same). The retired
    # per-card centering made the column a function of sibling text variance:
    # near-identical cards aligned differently and pinned-wide cards read
    # bloated on both flanks. ``bullet_lead`` (the lanes bulleted-card
    # anatomy, the obi-engine specimen) keeps its own envelope: the group
    # hugs ``pad_x`` and only the label indents past the category mark.
    group_left = x + (nch.pad_x if left_align else nch.glyph_inset_x)
    # The identity mark rides the identity-BLOCK center (name + descs), not the
    # cap line: on a chip-bottomed card the block top-anchors, so the glyph
    # stays with the name instead of floating to the geometric card center.
    glyph_art = glyph_builder(group_left + mark_w / 2, glyph_cy) if glyph_builder is not None else None
    label = DiagramText(x=group_left + lead + bullet_lead, y=label_base, text=label_text, cls=label_cls)
    desc_cls = "ndesc" if role == "default" else "mdesc"
    desc_lines = tuple(
        DiagramText(x=group_left + lead, y=desc_base + i * nch.desc_line_pitch, text=line, cls=desc_cls)
        for i, line in enumerate(kept_lines)
    )
    # Chip-row (chrome vocabulary): one row of inline pills BOTTOM-anchored
    # in the card (the slot model — chips read as metadata beneath the identity,
    # not glued to the desc), left-aligned to the glyph column. embed follows.
    chip_boxes: tuple[RectSpec, ...] = ()
    chip_texts: tuple[DiagramText, ...] = ()
    ti = 0
    if node.chips:
        chip_boxes, chip_texts = _chip_row(node.chips, cfg, trailing_tops[ti], left=group_left)
        ti += 1
    embed_top = trailing_tops[ti] if node.embed_dims else 0.0
    plain_embed = _embed_box(node, x, w, embed_top, nch.pad_x) if node.embed_dims else None
    return NodePlacement(
        index=index,
        node_id=node.id,
        shape="rect",
        embed_box=plain_embed,
        chip_boxes=chip_boxes,
        chip_texts=chip_texts,
        box=box,
        role=role,
        stroke_width=1.0,
        stroke_dasharray=muted_dash if role == "muted" else "",
        accent_index=accent_index,
        label=label,
        desc_lines=desc_lines,
        dot=None,
        glyph=glyph_art,
    )


def measure_text_block(cfg: ParadigmDiagramConfig, node: DiagramNode) -> tuple[float, float, list[str]]:
    """The typographic satellite's (w, h, desc_lines): name in the name voice
    + AUTHORED desc lines (\\n splits; the block never re-wraps — the caller
    composed those lines) in the desc voice at the name→desc pitch."""
    lines = [ln for ln in (node.desc or "").split("\n") if ln.strip()]
    name_w = measure_voice(node.label, cfg.label_voice)
    w = max([name_w, *(measure_voice(ln, cfg.desc_voice) for ln in lines)], default=name_w)
    name_h = cfg.label_voice.size * (cfg.text_ascent_ratio + cfg.text_descent_ratio)
    line_h = cfg.desc_voice.size * (cfg.text_ascent_ratio + cfg.text_descent_ratio)
    h = name_h + (5.0 + line_h + (len(lines) - 1) * 19.0 if lines else 0.0)
    return w, h, lines


def place_text_block(
    *,
    index: int,
    node: DiagramNode,
    cx: float,
    cy: float,
    cfg: ParadigmDiagramConfig,
    accent_index: int,
) -> NodePlacement:
    """A containerless typographic node (hub-panel-02-orchestrator):
    containers earn their existence — the satellite's type IS the node. The
    block (name over authored desc lines, start-anchored on one left edge)
    centres on (cx, cy); its bbox still anchors connectors and collision, so
    a spoke kisses the TEXT's own extent, never a phantom card."""
    w, h, lines = measure_text_block(cfg, node)
    pad = 8.0  # the block's breathing bbox — clears the min_pad_y clip law + collision
    box = RectSpec(x=cx - w / 2 - pad, y=cy - h / 2 - pad, w=w + 2 * pad, h=h + 2 * pad)
    left = box.x + pad
    name_base = box.y + pad + cfg.label_voice.size * cfg.text_ascent_ratio
    # Containerless names read in INK (hub-panel-02-orchestrator: #1E293B
    # names, #647588 descs — accent lives in the hero card alone; the earlier
    # dname reading over-spent the chromatic budget on four figures).
    label = DiagramText(x=left, y=name_base, text=node.label, cls="name", anchor="start")
    first_desc = (
        name_base + cfg.label_voice.size * cfg.text_descent_ratio + 5.0 + cfg.desc_voice.size * cfg.text_ascent_ratio
    )
    desc_lines = tuple(
        DiagramText(x=left, y=first_desc + q * 19.0, text=ln, cls="ndesc", anchor="start") for q, ln in enumerate(lines)
    )
    return NodePlacement(
        index=index,
        node_id=node.id,
        shape="text",
        box=box,
        role=role_of(node),
        stroke_width=0.0,
        stroke_dasharray="",
        accent_index=accent_index,
        label=label,
        desc_lines=desc_lines,
    )


def place_circle(
    *,
    index: int,
    node: DiagramNode,
    cx: float,
    cy: float,
    r: float,
    cfg: ParadigmDiagramConfig,
    ch: DiagramTopologyChassis,
    accent_index: int,
    hub: bool = False,
    registry: Mapping[str, Any] | None = None,
    glyph_selection: GlyphTint = GlyphTint.INK,
    ring_center: tuple[float, float] | None = None,
) -> NodePlacement:
    """A glyph-circle: identity mark (or mono short text) inside, the label
    outside. ``ring_center`` (a topology with a ring STROKE through its
    nodes, e.g. flywheel) places the label RADIALLY outboard — along the
    spoke from ring-center through the node, a uniform clearance beyond the
    node edge, with text growing away from the ring (right-anchored at 9
    o'clock, left at 3, centered top/bottom). Absent it, the label sits
    directly below (columns, hubs, the canon bp/fw/h2 anatomy)."""
    role = role_of(node)
    box = RectSpec(x=cx - r, y=cy - r, w=2 * r, h=2 * r, rx=r)
    glyph_art = resolve_node_glyph(
        node_glyph_id(node, registry), registry, glyph_selection, cx=cx, cy=cy, size=r * 0.9, accent_index=accent_index
    )
    short: DiagramText | None = None
    desc_lines: tuple[DiagramText, ...] = ()
    inside_w = 1.7 * r  # usable text width across the circle's middle band
    hub_inside = (
        hub
        and glyph_art is None
        and bool(node.label)
        and measure_voice(node.label, cfg.circle_label_voice) <= inside_w
        and (not node.short or measure_voice(node.short, voice_for(cfg, "hubshort")) <= inside_w)
        and (not node.desc or measure_voice(node.desc, cfg.desc_voice) <= inside_w)
    )
    if hub_inside:
        # The hub has no outboard direction (K-radial-general): stack short
        # / name / desc INSIDE the circle, centered. Spokes start at the
        # boundary (the emanation mask), so inside text never crosses one;
        # no gap placement, no outside label.
        specs = [
            *(((node.short, "hubshort"),) if node.short else ()),
            (node.label, "clbl"),
            *(((node.desc, "ndesc"),) if node.desc else ()),
        ]
        # Center the block on the actual per-line metrics — the short voice
        # (bold, larger) is taller than the name, so a name-sized line box
        # would float the stack high. Stack ascent+descent boxes + a small
        # gap, centered on the node's vertical center.
        ar, dr = cfg.text_ascent_ratio, cfg.text_descent_ratio
        sizes = [voice_for(cfg, cls).size for _, cls in specs]
        line_gap = 3.0
        total_h = sum(s * (ar + dr) for s in sizes) + line_gap * (len(specs) - 1)
        stacked: list[DiagramText] = []
        y_top = cy - total_h / 2
        for (txt, cls), s in zip(specs, sizes, strict=True):
            baseline = y_top + s * ar
            stacked.append(
                DiagramText(
                    x=cx,
                    y=baseline,
                    text=truncate_to_width(txt, inside_w, voice_for(cfg, cls)),
                    cls=cls,
                    anchor="middle",
                )
            )
            y_top = baseline + s * dr + line_gap
        name_idx = 1 if node.short else 0
        short = stacked[0] if node.short else None
        label = stacked[name_idx]
        desc_lines = (stacked[-1],) if node.desc else ()
        return NodePlacement(
            index=index,
            node_id=node.id,
            shape="circle",
            box=box,
            role=role,
            stroke_width=1.5 if role == "hero" else 1.0,
            stroke_dasharray="",
            accent_index=accent_index,
            label=label,
            desc_lines=desc_lines,
            short=short,
            glyph=glyph_art,
            cx=cx,
            cy=cy,
            r=r,
        )
    if node.short and glyph_art is None:
        short_cls = "hubshort" if hub else "short"
        short = DiagramText(x=cx, y=cy + (6.0 if hub else 4.0), text=node.short, cls=short_cls, anchor="middle")
    gap = ch.circle_label_dy
    lx, ly, anchor, desc_dxy = cx, cy + r + gap, "middle", (0.0, 14.0)
    above = False
    rdx = (cx - ring_center[0]) if ring_center else 0.0
    rdy = (cy - ring_center[1]) if ring_center else 0.0
    rdist = math.hypot(rdx, rdy)
    if rdist > 1e-6:
        ux, uy = rdx / rdist, rdy / rdist
        size = cfg.circle_label_voice.size
        vcenter = size * (cfg.text_ascent_ratio - cfg.text_descent_ratio) / 2
        ax, ay = cx + ux * (r + gap), cy + uy * (r + gap)
        # top/bottom vs sides split (diagram-data-hub-circles-pp.svg): its
        # 5-satellite ring holds reasoning/policies 36deg off the vertical
        # pole with centered BELOW labels (top/bottom) and genomes/registries
        # 72deg off with lateral labels (sides) — the boundary sits strictly
        # between sin(36deg)=0.588 and sin(72deg)=0.951; 0.809 (=sin(54deg),
        # this specimen's own angle-midpoint) is the only citable value.
        if abs(ux) <= 0.809:  # top / bottom — centered over the spoke
            lx, anchor = cx, "middle"
            ly = ay if uy < 0 else ay + size * cfg.text_ascent_ratio
            desc_dxy = (0.0, 14.0 if uy >= 0 else -14.0)
            above = uy < 0
        else:  # sides + diagonals — outboard, text grows away from the ring
            anchor = "start" if ux > 0 else "end"
            lx, ly = ax, ay + vcenter
            desc_dxy = (0.0, 14.0)
    # Multi-line annotation stack (the medallion faces: the agent-loop-ring
    # and flywheel-circles specimens): when the chassis grants desc
    # room (max_desc_lines > 1) the desc WRAPS and the block stacks name →
    # desc lines at the specimen pitch (name→desc 18, desc→desc 16); an
    # ABOVE-node block keeps that reading order and grows upward so its
    # bottom line stays one gap off the silhouette. Single-line chassis keep
    # the legacy +14 seat byte-identically.
    max_lines = max(1, int(ch.node.max_desc_lines))
    if node.desc and max_lines > 1:
        # Wrap budget derived from the specimen (diagram-agent-loop-ring-pp.svg):
        # its longest one-line run, "build agents and workflows" (26 chars,
        # JetBrains Mono 11), holds on ONE line at r44 — 174.35px in our
        # desc_voice metrics (~172px on the hand SVG) / 44 ~= 3.97. The old
        # 3.6 factor broke that run to a second line, pushing a 2-line
        # specimen desc to 3.
        wrapped = wrap_text_lines(node.desc, 3.97 * r, cfg.desc_voice, max_lines=max_lines)
        name_gap, pitch = 18.0, 16.0
        if above:
            ly -= name_gap + pitch * (len(wrapped) - 1)
        # The medallion faces name their stages in the DISPLAY voice over
        # mono descs (agent-loop-ring: "1. Pair" is Inter 600 15 — alr-name —
        # while the desc lines stay JBM 11). One anatomy, wherever the
        # multi-line medallion home applies.
        # Outboard names never truncate (kit: the name is identity) — the
        # block lives OUTSIDE the circle and the canvas grows to hold it.
        label = DiagramText(
            x=lx,
            y=ly,
            text=node.label,
            cls="name",
            anchor=anchor,
        )
        desc_lines = tuple(
            DiagramText(x=lx, y=ly + name_gap + q * pitch, text=line, cls="ndesc", anchor=anchor)
            for q, line in enumerate(wrapped)
        )
        return NodePlacement(
            index=index,
            node_id=node.id,
            shape="circle",
            box=box,
            role=role,
            stroke_width=1.5 if role == "hero" else 1.0,
            stroke_dasharray="",
            accent_index=accent_index,
            label=label,
            desc_lines=desc_lines,
            short=short,
            glyph=glyph_art,
            cx=cx,
            cy=cy,
            r=r,
        )
    # Outboard names never truncate (kit law) — the canvas grows instead.
    label = DiagramText(
        x=lx,
        y=ly,
        text=node.label,
        cls="clbl",
        anchor=anchor,
    )
    if node.desc:
        desc_lines = (
            DiagramText(
                x=lx + desc_dxy[0],
                y=ly + desc_dxy[1],
                text=truncate_to_width(node.desc, 3.6 * r, cfg.desc_voice),
                cls="ndesc",
                anchor=anchor,
            ),
        )
    return NodePlacement(
        index=index,
        node_id=node.id,
        shape="circle",
        box=box,
        role=role,
        stroke_width=1.5 if role == "hero" else 1.0,
        stroke_dasharray="",
        accent_index=accent_index,
        label=label,
        desc_lines=desc_lines,
        short=short,
        glyph=glyph_art,
        cx=cx,
        cy=cy,
        r=r,
    )


def _muted_dash(ctx: SolverContext) -> str:
    """The one muted-role dash token every topology's placements share —
    duplicated verbatim across every solver module before this seam."""
    return str(ctx.engine["track"]["muted_dash"])


def _seam_glyph_builder(
    ctx: SolverContext,
    index: int,
    node: DiagramNode,
    *,
    unconditional: bool = False,
    size: float = GLYPH_MARK_W,
) -> Callable[[float, float], GlyphArt | None] | None:
    """The card+glyph identity-mark builder every topology's ``_card_art``
    duplicated verbatim: a declared glyph (brand or kind) takes the mark
    slot when the node's resolved anatomy is card+glyph. ``unconditional``
    is the two anatomies that show a declared glyph regardless of style —
    the sequence head (never a caller-selected ``node_style``) and the
    axial nucleus (always a card, so a glyph-circle request still rides it
    as a mark rather than losing it)."""
    if not unconditional and style_of(node, ctx.spec, ctx.ch) != NodeStyle.CARD_GLYPH.value:
        return None
    gid = node_glyph_id(node, ctx.glyph_registry)
    if not gid:
        return None
    return glyph_slot_builder(gid, ctx.glyph_registry, ctx.glyph_selections[index], size, ctx.node_accents[index])


def apply_health_dot(ctx: SolverContext, node: DiagramNode, placement: NodePlacement) -> NodePlacement:
    """Bolt the dependency-audit health-channel dot onto an already-placed
    card (``dataclasses.replace`` — the lanes.py ``dot``-field pattern):
    card-corner status dot, state-palette colored, orthogonal to identity
    accent (NodePlacement.health's own docstring has the full contract).
    ``node.health == OK`` (the default) is a no-op so every health-less
    call site renders byte-identical to before this feature existed — a
    caller wraps its own ``place_node(...)`` result through this rather than
    threading health through the seam's eight anatomy branches."""
    if node.health == NodeHealth.OK:
        return placement
    cfg = ctx.engine.get("health") or {}
    inset_x = float(cfg.get("dot_inset_x", 13))
    inset_y = float(cfg.get("dot_inset_y", 13))
    b = placement.box
    return replace(placement, health=node.health.value, health_dot=(b.x + b.w - inset_x, b.y + inset_y))


def place_node(
    ctx: SolverContext,
    node: DiagramNode,
    index: int,
    cx: float,
    cy: float,
    *,
    w: float,
    h: float,
    hero: bool | None = None,
    chassis: DiagramNodeChassis | None = None,
    chassis_class: str = "",
    tag: str = "",
    hub: bool | None = None,
    ring_center: tuple[float, float] | None = None,
    force_card: bool = False,
    glyph_unconditional: bool = False,
    glyph_size: float = GLYPH_MARK_W,
    default_style: str = NodeStyle.CARD.value,
    anatomy: str = "auto",
    rx: float = 0.0,
    x: float | None = None,
    y: float | None = None,
    bullet_lead: float = 0.0,
    left_align: bool = False,
) -> NodePlacement:
    """The positions-only solver seam's PLACEMENT half:
    every topology's per-node dispatch to ``place_card``/``place_circle``/
    ``place_head`` collapses to this one call, centered at
    ``(cx, cy)`` — the mandated contract for the card/head anatomies, which
    place a rect's top-left corner (``cx - w/2, cy - h/2``). ``x``/``y`` are
    an EXACT escape hatch for a solver that computed top-left directly
    (a row cursor, a column position): ``cx - w/2`` is not always
    bit-identical to the original ``x`` in floating point (subtraction does
    not always invert addition exactly at double precision), so a caller
    with an exact top-left passes it via ``x``/``y`` and this seam uses it
    VERBATIM for the card/head box instead of re-deriving it from ``cx``.
    ``cx``/``cy`` stay REQUIRED — pill/circle dispatch always needs a true
    center, and every caller already has one (even a cursor-based solver's
    own ``cx = x + w/2`` for its pill/circle branch, computed the same way
    the pre-seam code always did).

    Internally derives style (``style_of``), hero (``node.role``, unless a
    caller override — the same two preserved-verbatim exceptions
    ``solve_node_box`` documents), the node chassis, and the mark/glyph
    builder (``_seam_glyph_builder``) — one glyph resolution, not eight
    ``_card_art`` copies. ``accent_index``, ``mono_triggers``, and
    ``muted_dash`` are ALWAYS ``ctx.node_accents[index]``/``ctx.mono_
    triggers``/the one muted-dash token — zero variance across every call
    site this seam replaced, so they are never caller-supplied.

    Positional hints a solver legitimately owns: ``tag`` (state-machine's
    TERMINAL chip), ``hub``/
    ``ring_center`` (compass/radial glyph-circle dressing), ``force_card`` +
    ``glyph_unconditional`` (axial's nucleus is ALWAYS a card with an
    unconditional glyph, regardless of its declared style — a hard geometry
    constraint, not a style preference), ``anatomy="head"`` + ``rx``
    (sequence's participant head, the one anatomy outside the style
    cascade)."""
    ch = ctx.ch
    is_hero = (node.role is NodeRole.HERO) if hero is None else hero
    if chassis is not None:
        nch = chassis
    elif chassis_class == "node2":
        nch = ch.node2
    else:
        nch = ch.hero if is_hero else ch.node
    # ``style`` stays the TRUE resolved anatomy under ``force_card`` too —
    # ``_seam_glyph_builder`` below already uses it to decide glyph presence
    # (a forced card can still carry a card+glyph mark); only the SHAPE
    # dispatch below is suppressed to the default card render.
    style = style_of(node, ctx.spec, ch, default=default_style)
    auto_head = False
    if (
        anatomy == "auto"
        and not force_card
        and node_anatomy_of(ctx.spec, ch) == "head"
        and style in (NodeStyle.CARD.value, NodeStyle.CARD_GLYPH.value)
        and not node.embed_dims
    ):
        # Chassis-declared stacked portrait anatomy (rag-pipeline stages,
        # tree rows, flywheel-orbit phases) — glyph above, name + desc below.
        # Chips ride the portrait column (centered row) — a chips-bearing
        # stage stays the same species as its siblings, matching
        # ``solve_node_box``'s head dispatch so sizing and placement agree.
        # The EXPLICIT anatomy="head" caller (the sequence participant head)
        # stays a fixed chip-free token — the idiom sweep pins that.
        anatomy = "head"
        auto_head = True
        glyph_size = HEAD_GLYPH_SIZE
    if nch.glyph_w and glyph_size == GLYPH_MARK_W:
        # Chassis mark override (the axial nucleus' 32); explicit caller
        # sizes still win.
        glyph_size = nch.glyph_w
    builder = _seam_glyph_builder(ctx, index, node, unconditional=glyph_unconditional, size=glyph_size)
    left = cx - w / 2 if x is None else x
    top = cy - h / 2 if y is None else y
    if anatomy == "head":
        return place_head(
            index=index,
            node=node,
            x=left,
            y=top,
            w=w,
            h=h,
            rx=rx if rx else nch.rx,
            cfg=ctx.cfg,
            accent_index=ctx.node_accents[index],
            glyph_builder=builder,
            max_desc_lines=nch.max_desc_lines,
            desc_pitch=nch.desc_line_pitch,
            with_chips=auto_head,
            pad_x=head_pad_x(nch, hero=is_hero),
            pad_y=nch.head_pad_y,
            glyph_gap=HEAD_GLYPH_GAP if nch.head_glyph_gap is None else nch.head_glyph_gap,
            label_desc_gap=label_desc_gap_for(nch, ctx.cfg),
        )
    if not force_card and style == NodeStyle.GLYPH_CIRCLE.value:
        is_hub = is_hero if hub is None else hub
        return place_circle(
            index=index,
            node=node,
            cx=cx,
            cy=cy,
            r=w / 2,
            cfg=ctx.cfg,
            ch=ch,
            accent_index=ctx.node_accents[index],
            hub=is_hub,
            registry=ctx.glyph_registry,
            glyph_selection=ctx.glyph_selections[index],
            ring_center=ring_center,
        )
    if not force_card and style == NodeStyle.TEXT.value:
        return place_text_block(index=index, node=node, cx=cx, cy=cy, cfg=ctx.cfg, accent_index=ctx.node_accents[index])
    return place_card(
        index=index,
        node=node,
        x=left,
        y=top,
        nch=nch,
        cfg=ctx.cfg,
        accent_index=ctx.node_accents[index],
        mono_triggers=ctx.mono_triggers,
        muted_dash=_muted_dash(ctx),
        w_override=w,
        h_override=h,
        glyph_builder=builder,
        bullet_lead=bullet_lead,
        left_align=left_align,
    )
