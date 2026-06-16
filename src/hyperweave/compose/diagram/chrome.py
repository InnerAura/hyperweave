"""Shared diagram chrome: header/footer text and node placement.

Every text run is measured (per-font LUTs via the matrix voice helpers) and
truncated/wrapped BEFORE placement — templates stamp finished strings. The
voice-class registry below is the single source coupling placement classes
to paradigm voices: the solver measures with the same family/size/weight
tuple the defs CSS renders.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram.records import DiagramHeader, DiagramText, GlyphArt, NodePlacement
from hyperweave.compose.matrix.cells import (
    glyph_mark_placement,
    measure_voice,
    resolve_glyph_mode,
    truncate_to_width,
    wrap_text_lines,
)
from hyperweave.compose.spatial_records import RectSpec
from hyperweave.core.diagram import DiagramNode, DiagramSpec, NodeRole, NodeStyle
from hyperweave.core.matrix import GlyphTint
from hyperweave.core.paradigm import DiagramNodeChassis, DiagramTopologyChassis, MatrixVoice, ParadigmDiagramConfig

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

# cls -> ParadigmDiagramConfig voice attribute. The resolver emits one CSS
# class per entry; placements reference the cls; measurement uses the same
# voice. One registry, three consumers, zero drift.
VOICE_CLASSES: tuple[tuple[str, str], ...] = (
    ("title", "title_voice"),
    ("sub", "subtitle_voice"),
    ("name", "label_voice"),
    ("ndesc", "desc_voice"),
    ("hname", "hero_name_voice"),
    ("hdesc", "hero_desc_voice"),
    ("mname", "muted_name_voice"),
    ("mdesc", "desc_voice"),
    ("op", "op_voice"),
    ("elbl", "edge_label_voice"),
    ("key", "legend_voice"),
    ("tag", "tag_voice"),
    ("short", "short_voice"),
    ("hubshort", "hub_short_voice"),
    ("clbl", "circle_label_voice"),
    ("ft", "foot_voice"),
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


def build_header(
    spec: DiagramSpec, ch: DiagramTopologyChassis, cfg: ParadigmDiagramConfig, width: float
) -> DiagramHeader:
    """Title/subtitle per the chassis header mode; empty text collapses to
    an empty header (the band itself is chassis geometry)."""
    if ch.header_mode == "none" or (not spec.title and not spec.subtitle):
        return DiagramHeader()
    if ch.header_mode == "center":
        x, anchor = width / 2, "middle"
    else:
        x, anchor = ch.margin_x, "start"
    title = None
    subtitle = None
    if spec.title:
        text = truncate_to_width(spec.title, width - 2 * ch.margin_x, cfg.title_voice)
        title = DiagramText(x=x, y=34.0, text=text, cls="title", anchor=anchor)
    if spec.subtitle:
        text = truncate_to_width(spec.subtitle, width - 2 * ch.margin_x, cfg.subtitle_voice)
        subtitle = DiagramText(x=x, y=54.0, text=text, cls="sub", anchor=anchor)
    return DiagramHeader(title=title, subtitle=subtitle)


def build_footer(
    spec: DiagramSpec, slug: str, ch: DiagramTopologyChassis, cfg: ParadigmDiagramConfig, height: float
) -> DiagramText | None:
    """The brand line: HYPERWEAVE · {notes | LAYOUT} · INNERAURA LABS."""
    if ch.footer_h <= 0:
        return None
    middle = (spec.notes or slug.replace("-", " ")).upper()
    return DiagramText(
        x=ch.margin_x,
        y=height - ch.footer_dy,
        text=f"HYPERWEAVE · {middle} · INNERAURA LABS",
        cls="ft",
    )


def _role_of(node: DiagramNode) -> str:
    if node.role is NodeRole.HERO:
        return "hero"
    if node.role is NodeRole.MUTED:
        return "muted"
    return "default"


def resolve_node_glyph(
    glyph_id: str,
    registry: Mapping[str, Any] | None,
    tint: GlyphTint,
    *,
    cx: float,
    cy: float,
    size: float,
) -> GlyphArt | None:
    """The node identity slot, riding the matrix glyph system wholesale:
    ``glyph_mark_placement`` builds the mark (registry entry + tint
    selection, degrading full -> gradient -> brand -> ink); the resolved
    mode lands on ``GlyphArt.tint`` for the payload's rendered record."""
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
    )
    return GlyphArt(
        paths=mark.glyph_paths,
        transform=mark.glyph_transform,
        fill=mark.glyph_fill,
        opacity=mark.glyph_opacity,
        fill_rule=mark.glyph_fill_rule,
        gradient=mark.glyph_gradient,
        tint=resolve_glyph_mode(entry or {}, tint),
        cx=cx,
        cy=cy,
        size=size,
        glyph_id=glyph_id,
    )


def glyph_slot_builder(
    glyph_id: str,
    registry: Mapping[str, Any] | None,
    tint: GlyphTint,
    size: float = 16.0,
) -> Callable[[float, float], GlyphArt | None]:
    """Deferred mark construction for the card+glyph anatomy: ``place_card``
    calls the builder with the dot slot's final center (label-line aligned),
    so anchoring lives in ONE place instead of every solver call site."""

    def build(cx: float, cy: float) -> GlyphArt | None:
        return resolve_node_glyph(glyph_id, registry, tint, cx=cx, cy=cy, size=size)

    return build


GLYPH_MARK_W = 16.0
"""Identity-mark advance: the card+glyph mark's measured width."""
DOT_MARK_W = 8.0
"""Accent-dot advance: the dot's measured diameter (2 x NodePlacement.dot_r)."""


def mark_w_for(style: str, node: DiagramNode) -> float:
    """The MEASURED mark advance a node's label row carries (G3): the
    identity mark, the accent dot, or nothing (muted and hero rows carry
    no dot). Width solving and placement both read this — one measurement,
    no shims."""
    if style == NodeStyle.CARD_GLYPH.value and node.glyph:
        return GLYPH_MARK_W
    if node.role is NodeRole.HERO or node.role is NodeRole.MUTED:
        return 0.0
    return DOT_MARK_W


def _ink_gap(nch: DiagramNodeChassis) -> float:
    """Mark INK edge to label start. The chassis ``label_gap`` is specified
    dot-center to label-start; the ink gap subtracts the dot's radius so
    wider marks (the 16px glyph) keep the same optical gap by measurement
    instead of a +4 shim."""
    return nch.label_gap - DOT_MARK_W / 2


def card_ink_w(
    node: DiagramNode,
    nch: DiagramNodeChassis,
    cfg: ParadigmDiagramConfig,
    mono_triggers: list[str],
    mark_w: float,
) -> float:
    """Measured ink width of a card's content group: the mark advance +
    gap + label on one row, the desc on the rows below, group-left aligned."""
    label_cls = label_cls_for(node, mono_triggers) if _role_of(node) == "default" else "mname"
    lead = (mark_w + _ink_gap(nch)) if mark_w else 0.0
    label_row = lead + measure_voice(node.label, voice_for(cfg, label_cls))
    desc_row = measure_voice(node.desc, cfg.desc_voice) if node.desc else 0.0
    return max(label_row, desc_row)


def solve_card_w(
    node: DiagramNode,
    nch: DiagramNodeChassis,
    cfg: ParadigmDiagramConfig,
    mono_triggers: list[str],
    *,
    hero: bool = False,
    min_w: float = 120.0,
    mark_w: float = DOT_MARK_W,
) -> float:
    """Content-solved card width — the pill precedent (G3):
    ``clamp(measured ink + 2 x pad, min_w, chassis ceiling)``. Pads are
    symmetric to ink (place_card centers the group). Free-policy topologies
    solve each card; aligned-policy topologies take the max over members."""
    if hero:
        lead = (mark_w + _ink_gap(nch)) if mark_w else 0.0
        content = max(
            lead + measure_voice(node.label, cfg.hero_name_voice),
            measure_voice(node.desc, cfg.hero_desc_voice) if node.desc else 0.0,
        )
    else:
        content = card_ink_w(node, nch, cfg, mono_triggers, mark_w)
    want = content + 2 * nch.pad_x
    return max(min_w, min(nch.w, math.ceil(want / 2) * 2))


def _text_block(
    cfg: ParadigmDiagramConfig,
    *,
    box_y: float,
    box_h: float,
    label_size: float,
    desc_size: float,
    desc_lines: int,
    desc_pitch: float,
) -> tuple[float, float, int]:
    """Metric-centered vertical layout for a node's text block (G2).

    Returns (label_baseline, first_desc_baseline, kept_desc_lines). The
    block — label line + gap + desc lines — is measured with line metrics
    and centered in the box; desc lines DROP (never clip) until every
    baseline + descender clears the box minus ``min_pad_y``."""
    ar, dr = cfg.text_ascent_ratio, cfg.text_descent_ratio
    avail = box_h - 2 * cfg.min_pad_y
    kept = desc_lines
    while True:
        block = label_size * (ar + dr)
        if kept:
            block += cfg.label_desc_gap + desc_size * (ar + dr) + (kept - 1) * desc_pitch
        if block <= avail or kept == 0:
            break
        kept -= 1
    top = box_y + (box_h - block) / 2
    label_baseline = top + label_size * ar
    first_desc_baseline = label_baseline + label_size * dr + cfg.label_desc_gap + desc_size * ar
    assert label_baseline + label_size * dr <= box_y + box_h - cfg.min_pad_y + 0.51, "label clips its card"
    if kept:
        last = first_desc_baseline + (kept - 1) * desc_pitch
        assert last + desc_size * dr <= box_y + box_h - cfg.min_pad_y + 0.51, "desc clips its card"
    return label_baseline, first_desc_baseline, kept


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
    glyph_builder: Callable[[float, float], GlyphArt | None] | None = None,
) -> NodePlacement:
    """A rectangular card: dot + left-aligned label/desc (default, muted —
    muted drops the dot and quiets the voices), or centered hero text.
    ``glyph_builder`` (the card+glyph anatomy) is called with the mark's
    final center — the dot slot, optically aligned to the LABEL line, never
    the card center — so the identity mark can't collide with desc rows and
    call sites can't mis-anchor it. Vertical placement is metric-centered
    (G2): the text block measures its line boxes and centers in the card;
    content always fits — desc lines drop before anything clips."""
    role = _role_of(node)
    w = w_override or nch.w
    box = RectSpec(x=x, y=y, w=w, h=nch.h, rx=nch.rx)
    if role == "hero":
        cx = x + w / 2
        max_w = w - 2 * nch.pad_x
        lines = wrap_text_lines(node.desc, max_w, cfg.hero_desc_voice, max_lines=nch.max_desc_lines)
        label_base, desc_base, kept = _text_block(
            cfg,
            box_y=y,
            box_h=nch.h,
            label_size=cfg.hero_name_voice.size,
            desc_size=cfg.hero_desc_voice.size,
            desc_lines=len(lines),
            desc_pitch=nch.desc_line_pitch,
        )
        # A hero MAY carry an identity mark (card+glyph, V3): the centered
        # group becomes [mark · gap · name]; the ring stays — they coexist.
        hero_mark_w = GLYPH_MARK_W if glyph_builder is not None else 0.0
        hero_lead = (hero_mark_w + _ink_gap(nch)) if hero_mark_w else 0.0
        name_text = truncate_to_width(node.label, max_w - hero_lead, cfg.hero_name_voice)
        glyph_art = None
        if glyph_builder is not None:
            name_w = measure_voice(name_text, cfg.hero_name_voice)
            group_left = cx - (hero_lead + name_w) / 2
            mark_cy = label_base - cfg.dot_align_ratio * cfg.hero_name_voice.size
            glyph_art = glyph_builder(group_left + hero_mark_w / 2, mark_cy)
            label_x = group_left + hero_lead + name_w / 2
        else:
            label_x = cx
        label = DiagramText(x=label_x, y=label_base, text=name_text, cls="hname", anchor="middle")
        desc_lines = tuple(
            DiagramText(x=cx, y=desc_base + i * nch.desc_line_pitch, text=line, cls="hdesc", anchor="middle")
            for i, line in enumerate(lines[:kept])
        )
        return NodePlacement(
            index=index,
            node_id=node.id,
            shape="rect",
            box=box,
            role=role,
            stroke_width=1.5,
            stroke_dasharray="",
            accent_index=accent_index,
            label=label,
            desc_lines=desc_lines,
            glyph=glyph_art,
        )
    has_dot = role == "default" and glyph_builder is None
    mark_w = GLYPH_MARK_W if glyph_builder is not None else (DOT_MARK_W if has_dot else 0.0)
    lead = (mark_w + _ink_gap(nch)) if mark_w else 0.0
    label_cls = label_cls_for(node, mono_triggers) if role == "default" else "mname"
    label_voice = voice_for(cfg, label_cls)
    lines = wrap_text_lines(node.desc, w - 2 * nch.pad_x, cfg.desc_voice, max_lines=nch.max_desc_lines)
    label_base, desc_base, kept = _text_block(
        cfg,
        box_y=y,
        box_h=nch.h,
        label_size=label_voice.size,
        desc_size=cfg.desc_voice.size,
        desc_lines=len(lines),
        desc_pitch=nch.desc_line_pitch,
    )
    # The measured content group — mark advance + gap + label on the label
    # row, desc rows beneath, group-left aligned — centers in the card so
    # slack splits evenly (pads symmetric to ink, G3).
    label_text = truncate_to_width(node.label, w - 2 * nch.pad_x - lead, label_voice)
    label_w = measure_voice(label_text, label_voice)
    kept_lines = lines[:kept]
    desc_w = max((measure_voice(line, cfg.desc_voice) for line in kept_lines), default=0.0)
    group_w = max(lead + label_w, desc_w)
    group_left = x + (w - group_w) / 2
    mark_cy = label_base - cfg.dot_align_ratio * label_voice.size
    glyph_art = glyph_builder(group_left + mark_w / 2, mark_cy) if glyph_builder is not None else None
    label = DiagramText(x=group_left + lead, y=label_base, text=label_text, cls=label_cls)
    desc_cls = "ndesc" if role == "default" else "mdesc"
    desc_lines = tuple(
        DiagramText(x=group_left, y=desc_base + i * nch.desc_line_pitch, text=line, cls=desc_cls)
        for i, line in enumerate(kept_lines)
    )
    return NodePlacement(
        index=index,
        node_id=node.id,
        shape="rect",
        box=box,
        role=role,
        stroke_width=1.0,
        stroke_dasharray=muted_dash if role == "muted" else "",
        accent_index=accent_index if has_dot else -1,
        label=label,
        desc_lines=desc_lines,
        dot=(group_left + mark_w / 2, mark_cy) if has_dot else None,
        glyph=glyph_art,
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
    role = _role_of(node)
    box = RectSpec(x=cx - r, y=cy - r, w=2 * r, h=2 * r, rx=r)
    glyph_art = resolve_node_glyph(node.glyph, registry, glyph_selection, cx=cx, cy=cy, size=r * 0.9)
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
    rdx = (cx - ring_center[0]) if ring_center else 0.0
    rdy = (cy - ring_center[1]) if ring_center else 0.0
    rdist = math.hypot(rdx, rdy)
    if rdist > 1e-6:
        ux, uy = rdx / rdist, rdy / rdist
        size = cfg.circle_label_voice.size
        vcenter = size * (cfg.text_ascent_ratio - cfg.text_descent_ratio) / 2
        ax, ay = cx + ux * (r + gap), cy + uy * (r + gap)
        if abs(ux) <= 0.38:  # top / bottom — centered over the spoke
            lx, anchor = cx, "middle"
            ly = ay if uy < 0 else ay + size * cfg.text_ascent_ratio
            desc_dxy = (0.0, 14.0 if uy >= 0 else -14.0)
        else:  # sides + diagonals — outboard, text grows away from the ring
            anchor = "start" if ux > 0 else "end"
            lx, ly = ax, ay + vcenter
            desc_dxy = (0.0, 14.0)
    label = DiagramText(
        x=lx,
        y=ly,
        text=truncate_to_width(node.label, 3.2 * r, cfg.circle_label_voice),
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


def place_pill(
    *,
    index: int,
    node: DiagramNode,
    cx: float,
    cy: float,
    nch: DiagramNodeChassis,
    ch: DiagramTopologyChassis,
    cfg: ParadigmDiagramConfig,
    accent_index: int,
    tag: str = "",
) -> NodePlacement:
    """A state pill (rx = h/2): a state is a condition, not a component.
    Width is content-solved — the one measured node width in the family."""
    role = _role_of(node)
    text_w = measure_voice(node.label, cfg.label_voice)
    w = max(nch.w, ch.pill_min_w, math.ceil((text_w + 2 * ch.pill_pad_x) / 10) * 10)
    x, y = cx - w / 2, cy - nch.h / 2
    box = RectSpec(x=x, y=y, w=w, h=nch.h, rx=nch.h / 2)
    tagged = bool(tag)
    ar, dr = cfg.text_ascent_ratio, cfg.text_descent_ratio
    name_size = cfg.label_voice.size
    if tagged:
        # Metric-centered name+tag pair (G2): no chassis dy guesses.
        tag_size = cfg.tag_voice.size
        block = name_size * (ar + dr) + cfg.label_desc_gap / 2 + tag_size * (ar + dr)
        top = cy - block / 2
        name_base = top + name_size * ar
        tag_base = name_base + name_size * dr + cfg.label_desc_gap / 2 + tag_size * ar
    else:
        name_base = cy + name_size * (ar - dr) / 2
        tag_base = 0.0
    label = DiagramText(
        x=cx,
        y=name_base,
        text=truncate_to_width(node.label, w - 2 * ch.pill_pad_x, cfg.label_voice),
        cls="name",
        anchor="middle",
    )
    tag_text = DiagramText(x=cx, y=tag_base, text=tag, cls="tag", anchor="middle") if tagged else None
    return NodePlacement(
        index=index,
        node_id=node.id,
        shape="pill",
        box=box,
        role=role,
        stroke_width=1.5 if role == "hero" else 1.0,
        stroke_dasharray="",
        accent_index=-1,
        label=label,
        tag=tag_text,
    )
