"""LAW 1 — the universal canvas/presence post-pass.

Every topology flows through ONE law in ``finish_layout``: the canvas is the
content bbox plus the chrome bands (margin_x each side, header_h above,
footer_h below), with the content translated so the bbox sits exactly inside
those bands. Solvers keep owning ARRANGEMENT (where things sit relative to
each other); this pass owns PRESENCE (where the arrangement sits on the
canvas) — so a fixed-banner solver can never strand its content top-left
with dead space right and below, a ring solver can never bill the artifact
for an unoccupied arc, and a card whose solved desc outgrew a chassis height
constant can never be clipped at the canvas edge. Per-solver canvas formulas
stop being load-bearing the moment this pass runs; the render-review defect
class ("content huddles in a corner of a too-big canvas" / "content clipped
at the bottom") is closed structurally, not per-solver.

The transform is a pure translation — arrangement geometry is untouched, so
every within-layout invariant (alignment groups, quantized angles, clearance
gaps) survives byte-for-byte relative to itself. Path strings translate via
a command-aware rewriter (M/L/H/V/C/S/Q/T translate every coordinate pair;
A translates only its endpoint, radii/flags pass through); ``transform=``
strings translate their leading ``translate(x,y)`` term.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram.paths import fmt

if TYPE_CHECKING:
    from hyperweave.compose.diagram.records import DiagramText, LaneBand, NodePlacement, OperatorMark
    from hyperweave.compose.diagram.wiring import EdgeGeo
    from hyperweave.compose.spatial_records import LineSpec, RectSpec

_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_CMD = re.compile(r"([MLHVCSQTAZmlhvcsqtaz])([^MLHVCSQTAZmlhvcsqtaz]*)")
_TRANSLATE = re.compile(r"translate\(\s*([-+]?[\d.]+)\s*[, ]\s*([-+]?[\d.]+)\s*\)")

# Per-command coordinate arity and which slots are (x, y) pairs. A is special:
# (rx ry x-rot large-arc sweep x y) — only the final pair translates.
_PAIRWISE = {"M": 2, "L": 2, "C": 6, "S": 4, "Q": 4, "T": 2}


def translate_path(d: str, dx: float, dy: float) -> str:
    """Translate an ABSOLUTE-command SVG path string by (dx, dy).

    The compositor emits absolute commands only (fmt-built); a relative
    command (lowercase) passes through untouched by construction — relative
    geometry is translation-invariant anyway.
    """
    if not d or (dx == 0.0 and dy == 0.0):
        return d
    out: list[str] = []
    for m in _CMD.finditer(d):
        cmd, body = m.group(1), m.group(2)
        nums = [float(n) for n in _NUM.findall(body)]
        if cmd in _PAIRWISE and nums:
            # Every coordinate in these commands alternates x,y — arity only
            # matters for validity, not for translation.
            shifted = [n + (dx if i % 2 == 0 else dy) for i, n in enumerate(nums)]
            pairs = [f"{fmt(shifted[i])},{fmt(shifted[i + 1])}" for i in range(0, len(shifted) - 1, 2)]
            out.append(cmd + " " + " ".join(pairs))
        elif cmd == "H" and nums:
            out.append("H " + " ".join(fmt(n + dx) for n in nums))
        elif cmd == "V" and nums:
            out.append("V " + " ".join(fmt(n + dy) for n in nums))
        elif cmd == "A" and nums:
            # Match the emitters' exact shape (`A rx,ry rot laf sf x,y`) so a
            # translated path is byte-comparable with a freshly emitted one.
            vals = []
            for i in range(0, len(nums) - len(nums) % 7, 7):
                rx, ry, rot, laf, sf, ex, ey = nums[i : i + 7]
                vals.append(f"{fmt(rx)},{fmt(ry)} {fmt(rot)} {int(laf)} {int(sf)} {fmt(ex + dx)},{fmt(ey + dy)}")
            out.append("A " + " ".join(vals))
        elif cmd in ("Z", "z"):
            out.append("Z")
        else:
            out.append(cmd + body.strip())
    return " ".join(part for part in out if part).strip()


def translate_transform(transform: str, dx: float, dy: float) -> str:
    """Offset the leading translate() term of a transform string."""
    if not transform or (dx == 0.0 and dy == 0.0):
        return transform

    def _shift(m: re.Match[str]) -> str:
        return f"translate({fmt(float(m.group(1)) + dx)},{fmt(float(m.group(2)) + dy)})"

    shifted, n = _TRANSLATE.subn(_shift, transform, count=1)
    if n:
        return shifted
    return f"translate({fmt(dx)},{fmt(dy)}) {transform}"


def _t_text(t: DiagramText, dx: float, dy: float) -> DiagramText:
    return replace(t, x=t.x + dx, y=t.y + dy)


def _t_text_opt(t: DiagramText | None, dx: float, dy: float) -> DiagramText | None:
    return None if t is None else _t_text(t, dx, dy)


def _t_rect(r: RectSpec, dx: float, dy: float) -> RectSpec:
    return replace(r, x=r.x + dx, y=r.y + dy)


def _t_line(line: LineSpec, dx: float, dy: float) -> LineSpec:
    return replace(line, x1=line.x1 + dx, y1=line.y1 + dy, x2=line.x2 + dx, y2=line.y2 + dy)


def _t_node(n: NodePlacement, dx: float, dy: float) -> NodePlacement:
    return replace(
        n,
        box=_t_rect(n.box, dx, dy),
        label=_t_text(n.label, dx, dy),
        desc_lines=tuple(_t_text(t, dx, dy) for t in n.desc_lines),
        dot=(n.dot[0] + dx, n.dot[1] + dy) if n.dot is not None else None,
        term_box=_t_rect(n.term_box, dx, dy) if n.term_box is not None else None,
        dot_path=translate_path(n.dot_path, dx, dy),
        health_dot=(n.health_dot[0] + dx, n.health_dot[1] + dy) if n.health_dot is not None else None,
        short=_t_text_opt(n.short, dx, dy),
        tag=_t_text_opt(n.tag, dx, dy),
        # cx/cy are the contrast gate's rebuild anchor (G5) — they must move
        # WITH the transform, or a dark-face tint rebuild re-anchors the mark
        # at its pre-shift position (glyphs floating above their cards).
        glyph=(
            replace(
                n.glyph,
                transform=translate_transform(n.glyph.transform, dx, dy),
                cx=n.glyph.cx + dx,
                cy=n.glyph.cy + dy,
            )
            if n.glyph
            else None
        ),
        cx=n.cx + dx if n.shape == "circle" else n.cx,
        cy=n.cy + dy if n.shape == "circle" else n.cy,
        embed_box=_t_rect(n.embed_box, dx, dy) if n.embed_box is not None else None,
        chip_boxes=tuple(_t_rect(b, dx, dy) for b in n.chip_boxes),
        chip_texts=tuple(_t_text(t2, dx, dy) for t2 in n.chip_texts),
    )


def _t_geo(g: EdgeGeo, dx: float, dy: float) -> EdgeGeo:
    return replace(
        g,
        d=translate_path(g.d, dx, dy),
        sx=g.sx + dx,
        sy=g.sy + dy,
        tx=g.tx + dx,
        ty=g.ty + dy,
        arc=(g.arc[0] + dx, g.arc[1] + dy, g.arc[2], g.arc[3], g.arc[4]) if g.arc is not None else None,
        label_pos=(g.label_pos[0] + dx, g.label_pos[1] + dy) if g.label_pos is not None else None,
        polyline=tuple((px + dx, py + dy) for px, py in g.polyline),
    )


def _t_operator(o: OperatorMark, dx: float, dy: float) -> OperatorMark:
    return replace(o, cx=o.cx + dx, cy=o.cy + dy, cross_d=translate_path(o.cross_d, dx, dy))


def _t_band(band: LaneBand, dx: float, dy: float) -> LaneBand:
    return replace(
        band,
        box=_t_rect(band.box, dx, dy),
        header=_t_text(band.header, dx, dy),
        count=_t_text_opt(band.count, dx, dy),
        rule=_t_line(band.rule, dx, dy) if band.rule is not None else None,
    )


def content_extents(
    nodes: list[NodePlacement],
    geos: list[EdgeGeo],
    lane_bands: tuple[Any, ...],
    lifelines: tuple[Any, ...],
    activations: tuple[Any, ...],
    initial_dot: tuple[float, float] | None,
    initial_stub: Any,
) -> tuple[float, float, float, float] | None:
    """The content bbox — node boxes, connector polylines, band boxes + rules,
    lifelines, activation bars, the SM initial dot/stub. Text runs live inside
    their boxes by the card solvers' contract; labels the annotate pass places
    later are chrome and grow the canvas separately."""
    xs: list[float] = []
    ys: list[float] = []
    for n in nodes:
        xs += [n.box.x, n.box.x + n.box.w]
        ys += [n.box.y, n.box.y + n.box.h]
        if n.term_box is not None:
            xs += [n.term_box.x, n.term_box.x + n.term_box.w]
            ys += [n.term_box.y, n.term_box.y + n.term_box.h]
        if n.tag is not None:
            ys.append(n.tag.y + 4.0)
    for g in geos:
        pts = g.polyline or ((g.sx, g.sy), (g.tx, g.ty))
        for px, py in pts:
            xs.append(px)
            ys.append(py)
    for band in lane_bands:
        xs += [band.box.x, band.box.x + band.box.w]
        ys += [band.box.y, band.box.y + band.box.h]
    for line in lifelines:
        xs += [line.x1, line.x2]
        ys += [line.y1, line.y2]
    for act in activations:
        xs += [act.x, act.x + act.w]
        ys += [act.y, act.y + act.h]
    if initial_dot is not None:
        xs += [initial_dot[0] - 5.0, initial_dot[0] + 5.0]
        ys += [initial_dot[1] - 5.0, initial_dot[1] + 5.0]
    if initial_stub is not None:
        xs += [initial_stub.x1, initial_stub.x2]
        ys += [initial_stub.y1, initial_stub.y2]
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def shift_content(
    *,
    nodes: list[NodePlacement],
    geos: list[EdgeGeo],
    lane_bands: tuple[Any, ...],
    lifelines: tuple[Any, ...],
    activations: tuple[Any, ...],
    operators: tuple[Any, ...],
    legend: Any,
    initial_dot: tuple[float, float] | None,
    initial_stub: Any,
    dx: float,
    dy: float,
) -> tuple[
    list[NodePlacement],
    list[EdgeGeo],
    tuple[Any, ...],
    tuple[Any, ...],
    tuple[Any, ...],
    tuple[Any, ...],
    Any,
    tuple[float, float] | None,
    Any,
]:
    """Translate every content item by (dx, dy) — the §2 region engine's
    normalize/place primitive (arrangement untouched, presence moved)."""
    if abs(dx) < 0.01 and abs(dy) < 0.01:
        return (nodes, geos, lane_bands, lifelines, activations, operators, legend, initial_dot, initial_stub)
    return (
        [_t_node(n, dx, dy) for n in nodes],
        [_t_geo(g, dx, dy) for g in geos],
        tuple(_t_band(b, dx, dy) for b in lane_bands),
        tuple(_t_line(line, dx, dy) for line in lifelines),
        tuple(_t_rect(a, dx, dy) for a in activations),
        tuple(_t_operator(o, dx, dy) for o in operators),
        _t_text_opt(legend, dx, dy),
        (initial_dot[0] + dx, initial_dot[1] + dy) if initial_dot is not None else None,
        _t_line(initial_stub, dx, dy) if initial_stub is not None else None,
    )


# The prior chrome law lived here as ``recenter_content`` — a second,
# header_h/footer_h-driven implementation of the canvas-hugs-content rule
# that ``finish_layout`` + ``regions.stack_regions`` superseded. It survived
# uncalled while the per-topology header_h/footer_h numbers it consumed kept
# READING as live tuning; deleted so nobody calibrates a dead parameter
# again. ``content_extents``/``shift_content`` above remain the live seam.
