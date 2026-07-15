"""Free-text annotation placement — the language's slot grammar.

The primer diagram language (primer_diagram_language.html) gives text exactly THREE
homes: a micro-label beside its wire (edge labels — annotate.py's
subsumption), a chip inside its card (node chips — chrome), and the CAPTION
BAND — centred at the canvas bottom in the caption voice. Free-zone parking
(a block seated wherever collision happens to clear) is retired: it was
collision-correct but slot-incoherent — text read as floating debris beside
the composition. Node- and point-anchored free text
(callout, pin, aside) therefore seats in the caption band: bottom-centred,
stacked, canvas grown to hold it (``solver.finish_layout``'s content-union).
The pin's floating dot is gone with the zones — a dot with no wire is not a
kit piece. Badges keep the below-anchor pill (the kernel-bottleneck chip-of-
air idiom). The rules that never break: no overlap survives, no authored
string truncates.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram import chrome_kinds as ck
from hyperweave.compose.diagram.paths import fmt
from hyperweave.compose.diagram.records import AnnotationPlacement, DiagramText
from hyperweave.compose.diagram.sizing import voice_for
from hyperweave.compose.matrix.cells import measure_voice, wrap_text_lines
from hyperweave.compose.spatial_records import RectSpec

if TYPE_CHECKING:
    from hyperweave.compose.diagram.collide import Obstacle
    from hyperweave.core.diagram_annotations import DiagramAnnotation
    from hyperweave.core.paradigm import MatrixVoice

_ELLIPSIS = "…"

# A pin dot clears its anchor card edge by this much: the annotation layer paints
# BENEATH the cards, so a dot sitting on the boundary would be masked by the card
# fill. A paint-order safety epsilon, not an aesthetic knob.
_TIE_GAP = 2.0

# Zone order = the specimen priority. Notes sit BELOW or ABOVE their anchor
# (scatter-gather's "one response" is below the convergence chip); the sides
# come next; the four diagonals are last — the compass-hub case, where every
# cardinal direction carries a spoke and only the quadrants between them are
# clear (spec-boundary's callout lands SE of the ComposeSpec hub).
_ZONE_ORDER = ("below", "above", "right", "left", "se", "sw", "ne", "nw")

# place_aside_near's seat-widening ladder: a seat blocked by a THIN obstacle
# dead-centred on its own standoff axis (a compass hub's spoke shares the
# hub's x for a below/above seat, its y for a left/right one) usually clears
# a short slide off that axis rather than needing a whole different zone —
# same 'try candidates outward in steps' shape as collide.py's push ladder,
# scoped to keep the note in its chosen row/column. 10 steps of 12px reaches
# 120px, past the ~91px a compass hub's spoke needed with room to spare
# (genome-consumers/'the seed lights everything').
_SEAT_SLIDE_STEP = 12.0
_SEAT_SLIDE_MAX = 120.0

# A growth-mode note (every near seat and slide blocked) draws a leader once
# it lands farther than this from its anchor — adjacency lost is a claim the
# layer can't make silently (AMENDMENT to place_aside_near's near-seat
# default, 'no leader — the adjacency IS the tie': a note stranded 300+px
# from its anchor with no tie at all read as no-man's-land, not felt-
# adjacent). Below this a growth nudge still reads as tied by proximity and
# stays leaderless, same spirit as the generic connector.leader_gap a
# callout's point leader uses.
_GROWTH_LEADER_MIN = 40.0


def _overlaps(a: RectSpec, b: RectSpec) -> bool:
    """True when two rects share positive area (edge-touching is clear)."""
    ix = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
    iy = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
    return ix > 0.01 and iy > 0.01


def _clear(box: RectSpec, obstacles: list[Obstacle], *, exclude_node: int = -1) -> bool:
    """True when ``box`` overlaps no obstacle. The anchor node (``exclude_node``)
    is skipped: a callout sits at standoff from its OWN card and a pin dot rides
    that card's boundary — neither is a foreign collision, exactly as a subsumed
    edge label excludes its own incident nodes."""
    for o in obstacles:
        if o.kind == "node" and o.ref == exclude_node:
            continue
        if _overlaps(box, o.box):
            return False
    return True


def _wire_padded(obstacles: list[Obstacle], pad: float) -> list[Obstacle]:
    """``obstacles`` with every EDGE-kind box inflated by ``pad`` on every
    side. The generic edge-obstacle pad (annotate.py's ``_static_obstacles``:
    stroke_width + 2, ~3.5px) is sized for a label/chip that's SUPPOSED to
    hug its own wire; a near-anchor SEAT has no such relation to a FOREIGN
    wire and read 'clear' 9.5px off a spoke it passed within visible
    distance of (event-fan-radial's bus->analytics case — the note read as
    seated beside the wire, not just near the hub). Node/furniture
    obstacles pass through unchanged."""
    return [
        replace(o, box=RectSpec(x=o.box.x - pad, y=o.box.y - pad, w=o.box.w + 2 * pad, h=o.box.h + 2 * pad))
        if o.kind == "edge"
        else o
        for o in obstacles
    ]


def _slide_seat(box: RectSpec, *, along_x: bool, step: float, max_slide: float) -> list[RectSpec]:
    """Nudge ``box`` sideways (``along_x``, the below/above seats) or
    vertically (the left/right seats) in ``step`` increments up to
    ``max_slide``, alternating +/- so a seat centred on a symmetric
    obstacle (a spoke straight through its own standoff axis) clears on the
    shorter side first."""
    out: list[RectSpec] = []
    steps = int(max_slide // step)
    for k in range(1, steps + 1):
        d = k * step
        if along_x:
            out.append(replace(box, x=box.x + d))
            out.append(replace(box, x=box.x - d))
        else:
            out.append(replace(box, y=box.y + d))
            out.append(replace(box, y=box.y - d))
    return out


def wrap_full(text: str, max_w: float, voice: MatrixVoice) -> tuple[str, ...]:
    """Word-wrap with ENOUGH lines that the greedy wrapper never reaches its
    ellipsis cap — an annotation renders every authored word or it does not
    render (the no-truncation law). The line budget is the width-quotient plus
    slack; a guard widens it if a long word still forces an ellipsis."""
    est = max(1, math.ceil(measure_voice(text, voice) / max(1.0, max_w)) + 1)
    lines = wrap_text_lines(text, max_w, voice, max_lines=est)
    while lines and _ELLIPSIS in lines[-1] and est < 16:
        est += 1
        lines = wrap_text_lines(text, max_w, voice, max_lines=est)
    return tuple(lines)


def _block(lines: tuple[str, ...], voice: MatrixVoice, style: ck.ChromeStyle) -> tuple[float, float]:
    """(width, height) of the padded text block bounding ``lines``."""
    bw = ck.text_w(lines, voice) + 2 * style.box_pad_x
    bh = ck.block_h(len(lines), voice, style) + 2 * style.box_pad_y
    return bw, bh


def _zone_box(zone: str, a: RectSpec, bw: float, bh: float, s: float) -> RectSpec:
    """The block's box in ``zone`` relative to anchor rect ``a``, standoff ``s``.
    Cardinal zones centre the block on the anchor's edge midpoint; diagonal
    zones tuck it into the corner quadrant at a reduced standoff."""
    acx, acy = a.x + a.w / 2, a.y + a.h / 2
    if zone == "below":
        return RectSpec(x=acx - bw / 2, y=a.y + a.h + s, w=bw, h=bh)
    if zone == "above":
        return RectSpec(x=acx - bw / 2, y=a.y - s - bh, w=bw, h=bh)
    if zone == "right":
        return RectSpec(x=a.x + a.w + s, y=acy - bh / 2, w=bw, h=bh)
    if zone == "left":
        return RectSpec(x=a.x - s - bw, y=acy - bh / 2, w=bw, h=bh)
    d = s * 0.7
    if zone == "se":
        return RectSpec(x=a.x + a.w + d, y=a.y + a.h + d, w=bw, h=bh)
    if zone == "sw":
        return RectSpec(x=a.x - d - bw, y=a.y + a.h + d, w=bw, h=bh)
    if zone == "ne":
        return RectSpec(x=a.x + a.w + d, y=a.y - d - bh, w=bw, h=bh)
    return RectSpec(x=a.x - d - bw, y=a.y - d - bh, w=bw, h=bh)  # nw


def _middle_runs(
    lines: tuple[str, ...], box: RectSpec, voice: MatrixVoice, style: ck.ChromeStyle, cls: str
) -> tuple[DiagramText, ...]:
    """Text runs middle-anchored on the block's centre-x, stacked from its top —
    the specimen ``-ml`` idiom (a note reads centred on its point, not bleeding
    right from a start anchor)."""
    return ck.stack_runs(
        lines,
        x=box.x + box.w / 2,
        top_y=box.y + style.box_pad_y,
        voice=voice,
        cls=cls,
        anchor="middle",
        style=style,
    )


def _zone_order(hint: str) -> tuple[str, ...]:
    """Zones to try — a caller ``placement`` hint (if it names a zone) is tried
    FIRST, then the specimen default order; the collision search still runs."""
    if hint in _ZONE_ORDER:
        return (hint, *(o for o in _ZONE_ORDER if o != hint))
    return _ZONE_ORDER


def _content_bounds(obstacles: list[Obstacle], canvas: RectSpec) -> tuple[float, float, float, float]:
    """The union bbox of node obstacles (the cards), clamped to at least the
    canvas — the reference for the CAPTION BAND, which reads 'below every-
    thing' as 'at or below the canvas' even when content falls short of it
    (a short diagram must not seat its callout mid-canvas). ``_growth_block``
    does NOT use this — see ``_tight_content_bounds`` for why."""
    x0, y0, x1, y1 = 0.0, 0.0, canvas.w, canvas.h
    for o in obstacles:
        if o.kind != "node":
            continue
        x0, y0 = min(x0, o.box.x), min(y0, o.box.y)
        x1, y1 = max(x1, o.box.x + o.box.w), max(y1, o.box.y + o.box.h)
    return x0, y0, x1, y1


def _tight_content_bounds(obstacles: list[Obstacle]) -> tuple[float, float, float, float] | None:
    """The TRUE union bbox of node obstacles — no canvas floor or ceiling.

    ``_content_bounds``'s canvas clamp is correct for the caption band (it
    must never seat above the canvas edge just because content is short) but
    wrong for ``_growth_block``'s 'just beyond content, near the anchor'
    seat: seeding the min/max at (0, 0)-(canvas.w, canvas.h) means content
    that starts well inside the canvas (a compass hub's topmost node 53px
    down) still reports a content top of 0 — the note then jumps to the
    canvas edge, 300+px from its anchor, instead of hugging the real
    boundary (genome-consumers/'the seed lights everything'). None when
    there are no node obstacles at all (the caller falls back to the
    canvas)."""
    xs0 = [o.box.x for o in obstacles if o.kind == "node"]
    if not xs0:
        return None
    ys0 = [o.box.y for o in obstacles if o.kind == "node"]
    xs1 = [o.box.x + o.box.w for o in obstacles if o.kind == "node"]
    ys1 = [o.box.y + o.box.h for o in obstacles if o.kind == "node"]
    return min(xs0), min(ys0), max(xs1), max(ys1)


def _caption_band_block(
    ann: DiagramAnnotation,
    kind: str,
    anchor_cx: float,
    canvas: RectSpec,
    obstacles: list[Obstacle],
    cfg: Any,
    style: ck.ChromeStyle,
) -> AnnotationPlacement:
    """The caption-band home: the block seats below all content (stacking
    under any block already there) in the ANNOTATION voice, centred on its
    ANCHOR's x clamped into the canvas — a node-anchored note reads as tied
    to its node and a point-anchored one honors the authored fraction,
    instead of every free text collapsing to the content bbox's middle (the
    compose-pipeline callout drifted 14px right of its anchor because a wide
    hero at the row's end pulled that middle). ``finish_layout``'s
    content-union grows the canvas. One y-home for every node/point-anchored
    free-text kind — slot-coherent by construction, never parked in whatever
    gap cleared collision."""
    voice = voice_for(cfg, "ann")
    lines = wrap_full(ann.text, style.callout_max_w - 2 * style.box_pad_x, voice)
    bw, bh = _block(lines, voice, style)
    accent = -1 if ann.accent is None else ann.accent
    _, _, _, y1 = _content_bounds(obstacles, canvas)
    half = bw / 2
    cx = canvas.w / 2 if 2 * half >= canvas.w else min(max(anchor_cx, half), canvas.w - half)
    box = RectSpec(x=cx - bw / 2, y=y1 + style.standoff, w=bw, h=bh)
    while not _clear(box, obstacles):
        box = RectSpec(x=box.x, y=box.y + bh + style.standoff / 2, w=bw, h=bh)
    runs = _middle_runs(lines, box, voice, style, "ann")
    return AnnotationPlacement(kind=kind, lines=runs, box=box, accent_index=accent)


def place_callout(
    ann: DiagramAnnotation,
    anchor: RectSpec,
    canvas: RectSpec,
    obstacles: list[Obstacle],
    cfg: Any,
    style: ck.ChromeStyle,
    *,
    anchor_ref: int,
) -> AnnotationPlacement:
    """Slot grammar: a node-anchored note seats in the caption band, centred
    under its anchor card."""
    del anchor_ref
    return _caption_band_block(ann, "callout", anchor.x + anchor.w / 2, canvas, obstacles, cfg, style)


def place_callout_at_point(
    ann: DiagramAnnotation,
    ax: float,
    ay: float,
    canvas: RectSpec,
    obstacles: list[Obstacle],
    cfg: Any,
    style: ck.ChromeStyle,
) -> AnnotationPlacement:
    """A callout anchored to a bare canvas point (region/at): the block seats
    in the caption band centred on the authored point's x — the horizontal
    fraction is honored, the band supplies the y."""
    del ay
    return _caption_band_block(ann, "callout", ax, canvas, obstacles, cfg, style)


def place_aside_near(
    ann: DiagramAnnotation,
    anchor: RectSpec,
    canvas: RectSpec,
    obstacles: list[Obstacle],
    cfg: Any,
    style: ck.ChromeStyle,
    *,
    anchor_ref: int,
) -> AnnotationPlacement:
    """A graph-anchored margin note sits NEAR its anchor — directly below
    the card (centred), then above, then beside it, widening each seat's
    row/column in steps before giving up on it — never parked in the
    caption band's void ("static where it must survive" floated at the
    plate's bottom-left, 250px under the hero it annotates). ``anchor`` is
    the anchor's own FIGURE (its geometry box unioned with any outboard
    text it carries — annotate.py's ``_node_text_box``), not just its box:
    'below the anchor' must mean below the whole thing a circle's outboard
    label+desc stack draws beneath it, or a below-seat lands ON that text
    (hw_discover). The first clear seat wins; the content-union grows the
    canvas when a seat pokes past content, so nearness never costs a
    collision. No leader while a near seat (or a widened one) wins — the
    adjacency IS the tie; AMENDED for the growth fallback, which draws one
    once adjacency is genuinely lost (see ``_growth_block``)."""
    voice = voice_for(cfg, "ann")
    lines = wrap_full(ann.text, style.callout_max_w - 2 * style.box_pad_x, voice)
    bw, bh = _block(lines, voice, style)
    accent = -1 if ann.accent is None else ann.accent
    obs = [o for o in obstacles if not (o.kind == "node" and o.ref == anchor_ref)]
    # A foreign wire earns the same standoff a foreign card gets here — see
    # _wire_padded (the generic edge-obstacle pad is sized for a label/chip
    # riding its OWN wire, not a seat with no relation to one).
    obs = _wire_padded(obs, style.standoff)
    acx = anchor.x + anchor.w / 2
    acy = anchor.y + anchor.h / 2
    s = style.standoff
    seats = (
        RectSpec(x=acx - bw / 2, y=anchor.y + anchor.h + s, w=bw, h=bh),
        RectSpec(x=acx - bw / 2, y=anchor.y - s - bh, w=bw, h=bh),
        RectSpec(x=anchor.x - s - bw, y=acy - bh / 2, w=bw, h=bh),
        RectSpec(x=anchor.x + anchor.w + s, y=acy - bh / 2, w=bw, h=bh),
    )
    for box in seats:
        if _clear(box, obs):
            runs = _middle_runs(lines, box, voice, style, "ann")
            return AnnotationPlacement(kind="aside", lines=runs, box=box, accent_index=accent)
    # Widen before growth: a seat blocked by a thin obstacle dead-centred on
    # its own standoff axis (a compass hub's spoke shares the below/above
    # seats' x, the left/right seats' y) usually clears one slide step,
    # never needing the beyond-content fallback below.
    for i, seat in enumerate(seats):
        for cand in _slide_seat(seat, along_x=i < 2, step=_SEAT_SLIDE_STEP, max_slide=_SEAT_SLIDE_MAX):
            if _clear(cand, obs):
                runs = _middle_runs(lines, cand, voice, style, "ann")
                return AnnotationPlacement(kind="aside", lines=runs, box=cand, accent_index=accent)
    return _growth_block(ann, "aside", anchor, canvas, obstacles, lines, voice, style, accent)


def place_aside_point(
    ann: DiagramAnnotation,
    ax: float,
    ay: float,
    canvas: RectSpec,
    obstacles: list[Obstacle],
    cfg: Any,
    style: ck.ChromeStyle,
) -> AnnotationPlacement:
    """A margin note anchored to a canvas point (``at``/``region``): the block
    seats in the caption band CENTRED on the authored point's x, middle-
    anchored, no leader — the fraction is honored horizontally; the band
    supplies the y and the canvas grows to hold it."""
    del ay
    return _caption_band_block(ann, "aside", ax, canvas, obstacles, cfg, style)


def _zone_normal(zone: str) -> tuple[float, float]:
    """The outward unit-ish direction of ``zone`` (cardinal or diagonal)."""
    nx = 1.0 if ("e" in zone or zone == "right") else (-1.0 if ("w" in zone or zone == "left") else 0.0)
    ny = 1.0 if zone in ("below", "se", "sw") else (-1.0 if zone in ("above", "ne", "nw") else 0.0)
    return nx, ny


def _union(a: RectSpec, b: RectSpec) -> RectSpec:
    x0, y0 = min(a.x, b.x), min(a.y, b.y)
    x1, y1 = max(a.x + a.w, b.x + b.w), max(a.y + a.h, b.y + b.h)
    return RectSpec(x=x0, y=y0, w=x1 - x0, h=y1 - y0)


def _growth_block(
    ann: DiagramAnnotation,
    kind: str,
    anchor: RectSpec,
    canvas: RectSpec,
    obstacles: list[Obstacle],
    lines: tuple[str, ...],
    voice: MatrixVoice,
    style: ck.ChromeStyle,
    accent: int,
) -> AnnotationPlacement:
    """No seat (near or widened) was clear: drop the block just beyond the
    TRUE content on the anchor's near side (below if the anchor is in the
    upper half, else above), centred on the anchor's x, at MINIMAL distance
    — ``_tight_content_bounds``, not ``_content_bounds``: the latter's
    canvas floor/ceiling put the note at the canvas edge regardless of how
    far short of it content actually reached (a compass hub's topmost node
    sitting 53px down still saw a reported content-top of 0, stranding the
    note 300+px from its anchor with no visual tie at all —
    genome-consumers/'the seed lights everything'). A leader draws back to
    the anchor once that minimal distance still exceeds
    ``_GROWTH_LEADER_MIN`` (adjacency lost must be drawn, not left silent —
    the near-seat's leaderless default doesn't hold once growth is reached).
    The box sits outside the content bbox, so finish_layout's content-union
    growth expands the canvas — content is never truncated or pushed to
    make room."""
    bw, bh = _block(lines, voice, style)
    acx = anchor.x + anchor.w / 2
    tight = _tight_content_bounds(obstacles)
    _, y0, _, y1 = tight if tight is not None else (canvas.x, canvas.y, canvas.x + canvas.w, canvas.y + canvas.h)
    if anchor.y + anchor.h / 2 < canvas.h / 2:
        box = RectSpec(x=acx - bw / 2, y=y1 + style.standoff, w=bw, h=bh)
        anchor_y = anchor.y + anchor.h
    else:
        box = RectSpec(x=acx - bw / 2, y=y0 - style.standoff - bh, w=bw, h=bh)
        anchor_y = anchor.y
    runs = _middle_runs(lines, box, voice, style, "ann")
    leader = _leader_path(box, acx, anchor_y, _GROWTH_LEADER_MIN)
    return AnnotationPlacement(kind=kind, lines=runs, box=box, leader=leader, accent_index=accent)


def _leader_path(box: RectSpec, ax: float, ay: float, leader_gap: float) -> str:
    """A hairline from the box edge midpoint nearest the anchor to the anchor
    point ('' when the anchor already abuts the box)."""
    left, right = box.x, box.x + box.w
    top, bottom = box.y, box.y + box.h
    cx, cy = box.x + box.w / 2, box.y + box.h / 2
    if ax < left:
        ex, ey = left, cy
    elif ax > right:
        ex, ey = right, cy
    elif ay < top:
        ex, ey = cx, top
    elif ay > bottom:
        ex, ey = cx, bottom
    else:
        return ""
    if math.hypot(ax - ex, ay - ey) <= leader_gap:
        return ""
    return f"M {fmt(ex)},{fmt(ey)} L {fmt(ax)},{fmt(ay)}"
