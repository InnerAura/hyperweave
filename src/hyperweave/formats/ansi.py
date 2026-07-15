"""``--format ansi`` — a true spatial character-grid RENDER (§12.2).

Not raster-to-halfblocks: the grid derives from the artifact's own machine
layer — the ``hw:payload`` sidecar carries the full ``DiagramSpec``, which
this module re-solves through the IDENTICAL production pipeline the compose
path uses (``coerce_diagram_input`` -> embed composition -> topology-family
solver dispatch in ``compute_diagram_layout``) — so the projection is
deterministic by construction (same spec, same grid) and never touches
pixels. The payload carries no genome (this projection is genome-blind, like
every structural invariant elsewhere in the frame): PRIMER is diagrams'
first chassis and its structural constants are load-bearing (see
``core/paradigm.py``), so it is the canonical geometry every topology
solves against here, independent of which genome actually rendered the SVG.

Node boxes, connector polylines, direction terminals, self-loops, and
subsumed edge labels all paint onto the same character grid the masthead and
footer frame — a diagram drawn in whatever the terminal can digitize,
not described in prose.
"""

from __future__ import annotations

import itertools
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram.paths import sample_path

if TYPE_CHECKING:
    from hyperweave.compose.diagram.records import DiagramLayout, NodePlacement
    from hyperweave.core.diagram import DiagramSpec

_REGIONS = re.compile(r"<hw:regions[^>]*><!\[CDATA\[(.*?)\]\]></hw:regions>", re.S)
_PAYLOAD = re.compile(r"<hw:payload[^>]*><!\[CDATA\[(.*?)\]\]></hw:payload>", re.S)
_TITLE = re.compile(r"<hw:title>([^<]*)</hw:title>")

_MAX_COLS = 96
_PX_PER_ROW = 56.0

# Content-grid tuning (diagrams-v2 §12.2): a monospace cell reads roughly
# twice as tall as it is wide, so the y divisor is always 2x the x divisor —
# the "aspect roughly 2:1" the spec calls for. The base divisor (8px/col)
# keeps a 740px content band under 100 columns; wider content (a roomy
# 3-card pipeline routinely spans 800px+) scales BOTH divisors up together
# so the cap holds without distorting the grid's aspect.
_BASE_X_DIV = 8.0
_GRID_ASPECT = 2.0
_MAX_CONTENT_COLS = 100

# Chrome-only knob (connector/node hue-index assignment) — irrelevant to a
# projection that paints no color at all; any positive value is safe.
_PALETTE_LEN = 6


def _clip(text: str, width: int) -> str:
    if width <= 1:
        return text[:width]
    return text if len(text) <= width else text[: width - 1] + "…"


def _frame(inner_w: int, label: str, lines: list[str]) -> list[str]:
    """One region as a box-drawing frame: ``┌─ label ──┐`` + body rows."""
    head_label = f" {label} " if label else ""
    head = "┌─" + head_label + "─" * max(0, inner_w - len(head_label) - 1) + "┐"
    rows = [head]
    for line in lines:
        rows.append("│ " + _clip(line, inner_w - 2).ljust(inner_w - 2) + " │")
    rows.append("└" + "─" * inner_w + "┘")
    return rows


def _payload_summary(payload: dict[str, Any]) -> tuple[str, list[str]]:
    """(content frame label, body lines) FALLBACK — the structural story
    (topology, member labels, edge count) used only when the embedded spec
    cannot be re-solved into a fresh layout (an unsupported/mid-flight
    topology). The common path never reaches this; ``_content_grid`` draws
    the real spatial grid instead."""
    spec = payload.get("spec") or {}
    nodes = spec.get("nodes") or []
    edges = spec.get("edges") or []
    topology = str(spec.get("topology", ""))
    label = f"content · {topology} · {len(nodes)} nodes · {len(edges)} edges"
    names = []
    for n in nodes:
        name = str(n.get("label") or n.get("id") or "")
        if n.get("embed"):
            name += " [⊞]"
        if n.get("chips"):
            name += " (" + " · ".join(str(c) for c in n["chips"]) + ")"
        names.append(name)
    lines: list[str] = []
    row = ""
    for name in names:
        cand = f"{row} · {name}" if row else name
        if len(cand) > _MAX_COLS - 6 and row:
            lines.append(row)
            row = name
        else:
            row = cand
    if row:
        lines.append(row)
    rels = sorted({str(e.get("relation")) for e in edges if e.get("relation")})
    if rels:
        lines.append("relations: " + " · ".join(rels))
    return label, lines


def _reconstruct_layout(spec_dict: dict[str, Any]) -> tuple[DiagramLayout, DiagramSpec]:
    """Re-solve the payload's ``spec`` through the SAME production pipeline
    ``compose/resolvers/diagram.py`` uses: normalize (AUTO roles, cyclic-dag
    promotion), recursively compose any embeds (so a container node's box
    reserves its real nested-artifact width), then dispatch to the
    topology-family solver. Deterministic: identical spec in, identical
    ``DiagramLayout`` out."""
    from hyperweave.compose.diagram import compute_diagram_layout
    from hyperweave.compose.diagram.input import coerce_diagram_input
    from hyperweave.compose.resolvers.diagram import _compose_embeds
    from hyperweave.config.loader import load_diagram_config, load_glyphs
    from hyperweave.config.registry import get_paradigms
    from hyperweave.core.models import ComposeSpec

    cspec = ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=spec_dict)
    normalized = coerce_diagram_input(None, cspec)
    engine = load_diagram_config()
    _markup, dspec = _compose_embeds(normalized.spec, cspec, engine)
    paradigms = get_paradigms()
    cfg = (paradigms.get("primer") or paradigms["default"]).diagram
    layout = compute_diagram_layout(
        dspec,
        paradigm=cfg,
        engine=engine,
        palette_len=_PALETTE_LEN,
        chrome="caption",
        glyph_registry=load_glyphs(),
        warnings=normalized.warnings,
    )
    return layout, dspec


def _grid_divisors(content_w: float) -> tuple[float, float]:
    x_div = max(_BASE_X_DIV, content_w / _MAX_CONTENT_COLS) if content_w > 0 else _BASE_X_DIV
    return x_div, x_div * _GRID_ASPECT


@dataclass(frozen=True, slots=True)
class _GridSpace:
    """The content region's local coordinate system: canvas px -> grid cell."""

    ox: float
    oy: float
    xdiv: float
    ydiv: float
    rows: int
    cols: int

    def cell(self, x: float, y: float) -> tuple[int, int]:
        row = round((y - self.oy) / self.ydiv)
        col = round((x - self.ox) / self.xdiv)
        return max(0, min(self.rows - 1, row)), max(0, min(self.cols - 1, col))

    def box(self, x0: float, y0: float, x1: float, y1: float) -> tuple[int, int, int, int]:
        c0 = max(0, min(self.cols, round((x0 - self.ox) / self.xdiv)))
        c1 = max(0, min(self.cols, round((x1 - self.ox) / self.xdiv)))
        r0 = max(0, min(self.rows, round((y0 - self.oy) / self.ydiv)))
        r1 = max(0, min(self.rows, round((y1 - self.oy) / self.ydiv)))
        if c1 <= c0:
            c1 = min(self.cols, c0 + 1)
        if r1 <= r0:
            r1 = min(self.rows, r0 + 1)
        return c0, r0, c1, r1


def _set(grid: list[list[str]], row: int, col: int, ch: str) -> None:
    if 0 <= row < len(grid) and 0 <= col < len(grid[0]):
        grid[row][col] = ch


def _ensure_min(lo: int, hi: int, min_len: int, limit: int) -> tuple[int, int]:
    """Widen a [lo, hi) span to at least ``min_len``, growing right first
    then left, never past ``limit`` — a card too short/narrow at this grid's
    resolution still gets room for a border plus one line of text."""
    while hi - lo < min_len and (lo > 0 or hi < limit):
        if hi < limit:
            hi += 1
        else:
            lo -= 1
    return lo, hi


def _elbow_glyph(dc: int, dr: int) -> str:
    """The rounded corner an H-then-V step turns through (dc, dr are the
    signed column/row deltas either side of the corner)."""
    if dc > 0:
        return "╮" if dr > 0 else "╯"
    return "╭" if dr > 0 else "╰"


def _arrow_glyph(dx: float, dy: float) -> str:
    if abs(dx) >= abs(dy):
        return "▶" if dx >= 0 else "◀"
    return "▼" if dy >= 0 else "▲"


def _paint_wire(grid: list[list[str]], r1: int, c1: int, r2: int, c2: int, hchar: str, vchar: str) -> None:
    """One polyline leg, approximated to the grid: straight runs of
    ``hchar``/``vchar``; a diagonal jump (coarse curve sampling) becomes an
    H-then-V elbow with a rounded corner glyph."""
    if r1 == r2 and c1 == c2:
        return
    if r1 == r2:
        lo, hi = (c1, c2) if c1 <= c2 else (c2, c1)
        for c in range(lo, hi + 1):
            _set(grid, r1, c, hchar)
        return
    if c1 == c2:
        lo, hi = (r1, r2) if r1 <= r2 else (r2, r1)
        for r in range(lo, hi + 1):
            _set(grid, r, c1, vchar)
        return
    lo, hi = (c1, c2) if c1 <= c2 else (c2, c1)
    for c in range(lo, hi + 1):
        _set(grid, r1, c, hchar)
    lo2, hi2 = (r1, r2) if r1 <= r2 else (r2, r1)
    for r in range(lo2, hi2 + 1):
        _set(grid, r, c2, vchar)
    _set(grid, r1, c2, _elbow_glyph(c2 - c1, r2 - r1))


def _place_str(
    grid: list[list[str]],
    gs: _GridSpace,
    x: float,
    y: float,
    anchor: str,
    text: str,
    row_bounds: tuple[int, int] | None = None,
    *,
    only_if_free: bool = False,
) -> None:
    """Stamp ``text`` at its OWN solver-measured position — the same (x, y,
    anchor) the SVG template would stamp — rather than re-centering it
    inside the grid ourselves; the continuous-space layout already solved
    that problem correctly. ``row_bounds`` (a node's interior span) clamps a
    secondary run (desc/chip/tag) off the node's OWN border row — real
    cards carry far more vertical room than a coarse 16px-per-row grid can
    reproduce, so a chip measured near the card's bottom edge would
    otherwise land squarely on the border it belongs inside of. A card with
    only ONE interior row at this resolution clamps label AND desc onto the
    very same row; ``only_if_free`` (secondary runs only — never the label)
    drops the run entirely rather than interleaving it, character by
    character, into whatever the label already wrote there."""
    if not text:
        return
    row, col = gs.cell(x, y)
    if row_bounds is not None:
        lo, hi = row_bounds
        if lo <= hi:
            row = max(lo, min(hi, row))
    if anchor == "middle":
        start = col - len(text) // 2
    elif anchor == "end":
        start = col - len(text) + 1
    else:
        start = col
    if only_if_free:
        lo_c, hi_c = max(0, start), min(len(grid[0]), start + len(text))
        if lo_c >= hi_c or any(grid[row][cc] != " " for cc in range(lo_c, hi_c)):
            return
    for i, ch in enumerate(text):
        _set(grid, row, start + i, ch)


def _paint_border(grid: list[list[str]], hero: bool, c0: int, r0: int, c1: int, r1: int) -> None:
    tl, tr, bl, br, horiz, vert = ("╔", "╗", "╚", "╝", "═", "║") if hero else ("╭", "╮", "╰", "╯", "─", "│")
    _set(grid, r0, c0, tl)
    _set(grid, r0, c1 - 1, tr)
    for c in range(c0 + 1, c1 - 1):
        _set(grid, r0, c, horiz)
    _set(grid, r1 - 1, c0, bl)
    _set(grid, r1 - 1, c1 - 1, br)
    for c in range(c0 + 1, c1 - 1):
        _set(grid, r1 - 1, c, horiz)
    for r in range(r0 + 1, r1 - 1):
        _set(grid, r, c0, vert)
        _set(grid, r, c1 - 1, vert)


def _node_box(gs: _GridSpace, node: NodePlacement) -> tuple[int, int, int, int]:
    """A node's grid extent (c0, r0, c1, r1), rect/hero widened to a minimum
    3x3 so a short/narrow card at this resolution still gets a border plus
    one text row. Computed once per node up front (before any painting) so
    both the wire-clamping pass and the node-painting pass agree on exactly
    the same box."""
    if node.shape == "circle":
        x0, y0, x1, y1 = node.cx - node.r, node.cy - node.r, node.cx + node.r, node.cy + node.r
    else:
        x0, y0, x1, y1 = node.box.x, node.box.y, node.box.x + node.box.w, node.box.y + node.box.h
    c0, r0, c1, r1 = gs.box(x0, y0, x1, y1)
    if node.shape != "circle":
        c0, c1 = _ensure_min(c0, c1, 3, gs.cols)
        r0, r1 = _ensure_min(r0, r1, 3, gs.rows)
    return c0, r0, c1, r1


def _interior_band(box: tuple[int, int, int, int] | None) -> tuple[int, int] | None:
    """A rect node's interior row span (None for a border-less circle/pill,
    or a box too short to carry an interior row of its own)."""
    if box is None:
        return None
    _c0, r0, _c1, r1 = box
    lo, hi = r0 + 1, r1 - 2
    return (lo, hi) if lo <= hi else None


def _paint_node(
    grid: list[list[str]], gs: _GridSpace, node: NodePlacement, embedded: bool, box: tuple[int, int, int, int]
) -> None:
    """Draw one node's border (rect: rounded box | hero: double-struck box)
    and every text run it carries, each at its real measured position.
    Circle/pill nodes get the parens form instead of a border (hero doubles
    the parens)."""
    c0, r0, c1, r1 = box
    hero = node.role == "hero"
    mark = " [⊞]" if embedded else ""
    if node.shape == "circle":
        wrap = ("((", "))") if hero else ("(", ")")
        label_text = f"{wrap[0]} {node.label.text}{mark} {wrap[1]}"
        _place_str(grid, gs, node.label.x, node.label.y, node.label.anchor, label_text)
        interior = None
    else:
        _paint_border(grid, hero, c0, r0, c1, r1)
        interior = (r0 + 1, r1 - 2)
        _place_str(grid, gs, node.label.x, node.label.y, node.label.anchor, node.label.text + mark, interior)
    for d in node.desc_lines:
        _place_str(grid, gs, d.x, d.y, d.anchor, d.text, interior, only_if_free=True)
    for chip in node.chip_texts:
        _place_str(grid, gs, chip.x, chip.y, chip.anchor, chip.text, interior, only_if_free=True)
    if node.short is not None:
        short = node.short
        _place_str(grid, gs, short.x, short.y, short.anchor, short.text, interior, only_if_free=True)
    if node.tag is not None:
        _place_str(grid, gs, node.tag.x, node.tag.y, node.tag.anchor, node.tag.text, interior, only_if_free=True)


def _content_grid(layout: DiagramLayout, dspec: DiagramSpec) -> tuple[str, list[str], int]:
    """The content region's spatial drawing: (frame label, grid rows, cols)."""
    region = next((r for r in layout.regions if r.id == "content"), None)
    ox, oy = (region.x, region.y) if region is not None else (0.0, 0.0)
    cw = region.w if region is not None else float(layout.width)
    ch = region.h if region is not None else float(layout.height)
    xdiv, ydiv = _grid_divisors(cw)
    cols = max(4, round(cw / xdiv)) if cw > 0 else 4
    rows = max(3, round(ch / ydiv)) if ch > 0 else 3
    gs = _GridSpace(ox=ox, oy=oy, xdiv=xdiv, ydiv=ydiv, rows=rows, cols=cols)
    grid: list[list[str]] = [[" "] * cols for _ in range(rows)]

    embed_ids = {n.id for n in dspec.nodes if n.embed is not None}
    # Geometry first, painting second: every node's box is known before any
    # ink lands, so a wire's ATTACHMENT cell can be nudged off the node's own
    # border row without disturbing an elbow/curve's genuine intermediate
    # rows (only the polyline's first/last cell ever touches a node).
    node_boxes = {n.index: _node_box(gs, n) for n in layout.nodes}
    path_pts: dict[int, tuple[tuple[float, float], ...]] = {}
    path_cells: dict[int, tuple[tuple[int, int], ...]] = {}

    # A — edges as box-drawing polylines (self-loops paint at D, once every
    # node's border exists to anchor the orbit glyph beside). A coarser
    # per_cubic than the SVG-precision default keeps a bent/curved wire's
    # staircase of elbows readable at character resolution instead of a
    # dense one-cell zigzag.
    for c in layout.connectors:
        pts = sample_path(c.path_d, per_cubic=3)
        path_pts[c.index] = pts
        if c.source_index == c.target_index or not pts:
            continue
        raw_cells = [gs.cell(x, y) for x, y in pts]
        src_band = _interior_band(node_boxes.get(c.source_index))
        tgt_band = _interior_band(node_boxes.get(c.target_index))
        if src_band is not None:
            raw_cells[0] = (max(src_band[0], min(src_band[1], raw_cells[0][0])), raw_cells[0][1])
        if tgt_band is not None:
            raw_cells[-1] = (max(tgt_band[0], min(tgt_band[1], raw_cells[-1][0])), raw_cells[-1][1])
        cells: list[tuple[int, int]] = []
        for rc in raw_cells:
            if not cells or cells[-1] != rc:
                cells.append(rc)
        path_cells[c.index] = tuple(cells)
        dashed = bool(c.static_dash) or c.track == "dash-march"
        hchar, vchar = ("┄", "┆") if dashed else ("─", "│")
        for (r1, c1), (r2, c2) in itertools.pairwise(cells):
            _paint_wire(grid, r1, c1, r2, c2, hchar, vchar)

    # B — node boxes, painted over the edge stubs at their borders (nodes
    # own their boundary cells).
    for node in layout.nodes:
        _paint_node(grid, gs, node, node.node_id in embed_ids, node_boxes[node.index])

    # C — direction terminals at each connector's arrival point: a chevron
    # aimed by the wire's final heading, or a dot for a drift-relation
    # terminal (its marker circle closes back on itself — geometrically
    # distinct from an arrow's open chevron). Placement uses the CLAMPED
    # attachment cell (so the glyph lands beside the box, not on its
    # border); heading uses the true continuous-space direction.
    for c in layout.connectors:
        if not c.marker_d or c.source_index == c.target_index:
            continue
        pts = path_pts.get(c.index, ())
        marker_cells = path_cells.get(c.index, ())
        if len(pts) < 2 or not marker_cells:
            continue
        end = pts[-1]
        prev = pts[-2]
        row, col = marker_cells[-1]
        marker_pts = sample_path(c.marker_d)
        is_dot = (
            len(marker_pts) >= 2
            and abs(marker_pts[0][0] - marker_pts[-1][0]) < 0.75
            and abs(marker_pts[0][1] - marker_pts[-1][1]) < 0.75
        )
        glyph = "·" if is_dot else _arrow_glyph(end[0] - prev[0], end[1] - prev[1])
        _set(grid, row, col, glyph)

    # D — self-loops: an orbit glyph beside the revisited node (a loop's
    # direction is unambiguous — no chevron, just the ↺ mark). A rect node
    # anchors it to the top border row; a circle/pill has no border row at
    # all, so it anchors to the label's own row instead — its only visible
    # row in this grid.
    nodes_by_index = {n.index: n for n in layout.nodes}
    for c in layout.connectors:
        if c.source_index != c.target_index:
            continue
        box = node_boxes.get(c.source_index)
        loop_node = nodes_by_index.get(c.source_index)
        if box is None or loop_node is None:
            continue
        _c0, r0, c1, r1 = box
        if loop_node.shape == "circle":
            label_row, _label_col = gs.cell(loop_node.label.x, loop_node.label.y)
            row = max(r0, min(r1 - 1, label_row))
        else:
            row = r0
        _set(grid, row, min(gs.cols - 1, c1), "↺")

    # E — subsumed edge labels/micro-chips: land beside the wire only when
    # every cell they'd occupy is still free (nodes and wires never lose a
    # cell to a label).
    for a in layout.annotations:
        if a.kind != "label":
            continue
        for dt in a.lines:
            if not dt.text:
                continue
            row, col = gs.cell(dt.x, dt.y)
            if dt.anchor == "middle":
                start = col - len(dt.text) // 2
            elif dt.anchor == "end":
                start = col - len(dt.text) + 1
            else:
                start = col
            end_c = start + len(dt.text)
            if start < 0 or end_c > gs.cols:
                continue
            if all(grid[row][cc] == " " for cc in range(start, end_c)):
                for i, ch in enumerate(dt.text):
                    grid[row][start + i] = ch

    rows_out = ["".join(r) for r in grid]
    label = f"content · {dspec.topology.value} · {len(dspec.nodes)} nodes · {len(layout.connectors)} edges"
    return label, rows_out, cols


def project_ansi(svg: str) -> str:
    """The structural grid. Raises ``ValueError`` when the artifact carries
    no region sidecar (non-diagram frames have no region tree to project)."""
    rm = _REGIONS.search(svg)
    if rm is None or not rm.group(1).strip():
        raise ValueError("ansi projection requires an hw:regions sidecar (diagram artifacts carry one)")
    raw: list[dict[str, Any]] = json.loads(rm.group(1))
    # Sidecar schema: {id, bbox: [x, y, w, h], margin, strategy}.
    regions = [
        {
            "id": r.get("id", ""),
            "x": float(r["bbox"][0]),
            "y": float(r["bbox"][1]),
            "w": float(r["bbox"][2]),
            "h": float(r["bbox"][3]),
        }
        for r in raw
        if r.get("bbox") and float(r["bbox"][2]) > 0 and float(r["bbox"][3]) > 0
    ]
    pm = _PAYLOAD.search(svg)
    payload: dict[str, Any] = json.loads(pm.group(1)) if pm else {}
    tm = _TITLE.search(svg)
    title = tm.group(1) if tm else str((payload.get("spec") or {}).get("title", ""))

    total_w = max((r["x"] + r["w"] for r in regions), default=0.0)
    scale = min(1.0, (_MAX_COLS - 2) / total_w) if total_w else 1.0

    spec_dict = payload.get("spec") or {}
    reconstructed: tuple[DiagramLayout, DiagramSpec] | None = None
    if spec_dict:
        try:
            reconstructed = _reconstruct_layout(spec_dict)
        except (ValueError, TypeError, KeyError, AttributeError):
            # An unsupported/mid-flight topology or a malformed embedded
            # spec: fall back to the structural summary rather than refusing
            # the whole projection.
            reconstructed = None

    out: list[str] = []
    for r in sorted(regions, key=lambda r: float(r["y"])):
        inner_w = max(12, int(float(r["w"]) * scale * (_MAX_COLS - 2) / max(total_w * scale, 1.0)))
        inner_w = min(inner_w, _MAX_COLS - 2)
        rid = str(r.get("id", ""))
        if rid == "masthead":
            body = [title] if title else []
            # The masthead frame HOLDS its title — geometry scales, text
            # never truncates in a structural projection.
            out += _frame(min(_MAX_COLS - 2, max(inner_w, len(title) + 4)), "masthead", body)
        elif rid == "content":
            if reconstructed is not None:
                layout, dspec = reconstructed
                label, lines, cols = _content_grid(layout, dspec)
                out += _frame(cols + 2, label, lines)
            else:
                label, lines = _payload_summary(payload)
                depth_rows = max(1, min(6, round(float(r["h"]) / _PX_PER_ROW)))
                while len(lines) < depth_rows:
                    lines.append("")
                out += _frame(inner_w, label, lines)
        else:
            spec = payload.get("spec") or {}
            caption = str(spec.get("subtitle") or "")
            out += _frame(inner_w, rid, [caption] if caption else [])
    return "\n".join(out) + "\n"
