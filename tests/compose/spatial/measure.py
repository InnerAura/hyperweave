"""Read-only spatial measurements over layout records and rendered SVG.

Every function reports a number about what the engine drew. None of them
grades it: the characterization fixture records these values as the present
state, and each family repair flips its own slice. Path flattening here is a
fixed-count sample — an instrument for characterization only; the bounded
flattener that a hard law may consume lands with the geometry package.
"""

from __future__ import annotations

import math
import re
from itertools import pairwise
from pathlib import Path
from typing import Any

import yaml

import hyperweave
from hyperweave.compose.matrix.cells import measure_voice
from hyperweave.core.text import measure_text
from tests.compose.parity.svgfacts import parse_svg

Point = tuple[float, float]
Box = tuple[float, float, float, float]

_TOKEN = re.compile(r"[MLHVCSQTAZ]|-?\d*\.?\d+(?:e[+-]?\d+)?", re.I)
_ARITY = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}
_CURVE_SAMPLES = 24
_BOUNDARY_SHRINK = 0.5


def github_readme_max_width() -> float:
    """The measured github-readme column ceiling from ``destinations.yaml``."""
    path = Path(hyperweave.__file__).parent / "data" / "config" / "destinations.yaml"
    profiles = yaml.safe_load(path.read_text())["profiles"]
    return float(profiles["github-readme"]["render_width"]["max"])


def scale_at(viewbox_w: float, column_w: float) -> float:
    return min(1.0, column_w / viewbox_w) if viewbox_w > 0 else 1.0


# ── paths ───────────────────────────────────────────────────────────────────


def _bezier(points: list[Point], samples: int) -> list[Point]:
    out: list[Point] = []
    n = len(points) - 1
    for i in range(1, samples + 1):
        t = i / samples
        x = y = 0.0
        for k, (px, py) in enumerate(points):
            b = math.comb(n, k) * (1 - t) ** (n - k) * t**k
            x += b * px
            y += b * py
        out.append((x, y))
    return out


def flatten_path(d: str) -> list[list[Point]]:
    """Every subpath of ``d`` as a polyline (curves sampled, arcs chorded).

    Relative commands are tracked through the cursor so hand-authored and
    engine paths measure alike. Control points never appear in the output.
    """
    tokens = _TOKEN.findall(d)
    subpaths: list[list[Point]] = []
    pts: list[Point] = []
    cur: Point = (0.0, 0.0)
    start: Point = (0.0, 0.0)
    last_ctrl: Point | None = None
    cmd = ""
    i = 0

    def flush() -> None:
        nonlocal pts
        if len(pts) > 1:
            subpaths.append(pts)
        pts = []

    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            cmd = tok
            i += 1
            if cmd.upper() == "Z":
                if pts:
                    pts.append(start)
                flush()
                cur = start
                continue
            continue
        arity = _ARITY[cmd.upper()]
        nums = [float(n) for n in tokens[i : i + arity]]
        i += arity
        if len(nums) < arity:
            break
        rel = cmd.islower()
        ox, oy = cur if rel else (0.0, 0.0)
        upper = cmd.upper()
        if upper == "M":
            flush()
            cur = (ox + nums[0], oy + nums[1])
            start = cur
            pts = [cur]
            cmd = "l" if rel else "L"
            last_ctrl = None
        elif upper == "L" or upper == "T":
            cur = (ox + nums[0], oy + nums[1])
            pts.append(cur)
            last_ctrl = None
        elif upper == "H":
            cur = (ox + nums[0], cur[1])
            pts.append(cur)
        elif upper == "V":
            cur = (cur[0], oy + nums[0])
            pts.append(cur)
        elif upper == "C":
            c1, c2, end = (ox + nums[0], oy + nums[1]), (ox + nums[2], oy + nums[3]), (ox + nums[4], oy + nums[5])
            pts.extend(_bezier([cur, c1, c2, end], _CURVE_SAMPLES))
            cur, last_ctrl = end, c2
        elif upper == "S":
            c1 = (2 * cur[0] - last_ctrl[0], 2 * cur[1] - last_ctrl[1]) if last_ctrl else cur
            c2, end = (ox + nums[0], oy + nums[1]), (ox + nums[2], oy + nums[3])
            pts.extend(_bezier([cur, c1, c2, end], _CURVE_SAMPLES))
            cur, last_ctrl = end, c2
        elif upper == "Q":
            c1, end = (ox + nums[0], oy + nums[1]), (ox + nums[2], oy + nums[3])
            pts.extend(_bezier([cur, c1, end], _CURVE_SAMPLES))
            cur, last_ctrl = end, c1
        elif upper == "A":
            cur = (ox + nums[5], oy + nums[6])
            pts.append(cur)
    flush()
    return subpaths


def segment_inside_length(a: Point, b: Point, box: Box, *, shrink: float = _BOUNDARY_SHRINK) -> float:
    """Length of segment ``a→b`` lying strictly inside ``box`` (Liang-Barsky).

    The box is shrunk by ``shrink`` so a wire that merely touches a face — a
    port arrival — measures zero while a wire that crosses the interior
    measures the distance it travelled inside.
    """
    x0, y0, x1, y1 = box[0] + shrink, box[1] + shrink, box[2] - shrink, box[3] - shrink
    if x1 <= x0 or y1 <= y0:
        return 0.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0:
            if q < 0:
                return 0.0
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return 0.0
            t0 = max(t0, r)
        else:
            if r < t0:
                return 0.0
            t1 = min(t1, r)
    if t1 <= t0:
        return 0.0
    return math.hypot(dx, dy) * (t1 - t0)


def polyline_inside_length(points: list[Point], box: Box) -> float:
    return sum(segment_inside_length(a, b, box) for a, b in pairwise(points))


def _box(rect: Any) -> Box:
    return (rect.x, rect.y, rect.x + rect.w, rect.y + rect.h)


# ── diagram layout records ──────────────────────────────────────────────────


def wires_through_cards(layout: Any) -> list[dict[str, Any]]:
    """Connector legs running inside a card that is not one of their endpoints."""
    hits: list[dict[str, Any]] = []
    for conn in layout.connectors:
        polylines = flatten_path(conn.path_d)
        for node in layout.nodes:
            if node.index in (conn.source_index, conn.target_index):
                continue
            inside = sum(polyline_inside_length(pl, _box(node.box)) for pl in polylines)
            if inside > 0.0:
                hits.append({"connector": conn.index, "node": node.node_id, "inside_px": round(inside, 1)})
    return hits


def endpoint_penetration(layout: Any) -> list[dict[str, Any]]:
    """How far each connector runs inside its OWN endpoint cards.

    A port arrival measures ~0; a riser spanning a card top to bottom measures
    the card's full height. Recorded per connector as the larger of its two
    endpoints so an author-direction defect is visible in one number.
    """
    by_index = {node.index: node for node in layout.nodes}
    out: list[dict[str, Any]] = []
    for conn in layout.connectors:
        polylines = flatten_path(conn.path_d)
        worst = 0.0
        for idx in (conn.source_index, conn.target_index):
            node = by_index.get(idx)
            if node is None:
                continue
            worst = max(worst, sum(polyline_inside_length(pl, _box(node.box)) for pl in polylines))
        out.append({"connector": conn.index, "inside_px": round(worst, 1)})
    return out


def lane_band_overlaps(layout: Any, cfg: Any) -> list[dict[str, Any]]:
    """Header ink end versus count-badge ink start, per lane band (positive = collision)."""
    out: list[dict[str, Any]] = []
    header_voice, count_voice = cfg.label_voice, cfg.label_voice
    for name, attr in (("lane", "lane_voice"), ("cnt", "count_voice")):
        voice = getattr(cfg, attr, None)
        if voice is not None:
            if name == "lane":
                header_voice = voice
            else:
                count_voice = voice
    for band in layout.lane_bands:
        header_end = band.header.x + measure_voice(band.header.text, header_voice)
        count_start = band.count.x - measure_voice(band.count.text, count_voice)
        out.append(
            {
                "band": band.header.text,
                "band_w": round(band.box.w, 1),
                "header_ink": round(header_end - band.header.x, 1),
                "overlap_px": round(header_end - count_start, 1),
            }
        )
    return out


def _texts_of(layout: Any) -> list[str]:
    texts: list[str] = []
    for node in layout.nodes:
        texts.append(node.label.text)
        texts.extend(t.text for t in node.label_lines)
        texts.extend(t.text for t in node.desc_lines)
        texts.extend(t.text for t in node.chip_texts)
        for extra in (node.short, node.tag):
            if extra is not None:
                texts.append(extra.text)
    for ann in layout.annotations:
        texts.extend(t.text for t in ann.lines)
    for band in layout.lane_bands:
        texts.append(band.header.text)
    return texts


def truncated_texts(layout: Any) -> int:
    return sum(1 for t in _texts_of(layout) if t.endswith("…"))


def diagram_summary(layout: Any) -> dict[str, Any]:
    column = github_readme_max_width()
    scale = scale_at(float(layout.width), column)
    return {
        "layout_slug": layout.layout_slug,
        "width": layout.width,
        "height": layout.height,
        "display_w": layout.display_w,
        "nodes": len(layout.nodes),
        "connectors": len(layout.connectors),
        "scale_at_github_readme_max": round(scale, 3),
        "truncated_texts": truncated_texts(layout),
        "wires_through_cards": wires_through_cards(layout),
        "endpoint_penetration_max": max((e["inside_px"] for e in endpoint_penetration(layout)), default=0.0),
    }


# ── matrix layout records ───────────────────────────────────────────────────


def matrix_header_overruns(layout: Any, cfg: Any) -> list[float]:
    """Header ink plus both pads minus the solved column width (positive = overrun)."""
    out: list[float] = []
    for j, col in enumerate(layout.colheaders):
        if j >= len(layout.col_w):
            break
        ink = measure_voice(col.label.text, cfg.colhead_voice)
        if col.sublabel is not None:
            ink = max(ink, measure_voice(col.sublabel.text, cfg.colhead_sub_voice))
        out.append(round(ink + 2 * cfg.cell_pad_x - layout.col_w[j], 1))
    return out


def matrix_title_metrics(layout: Any, cfg: Any) -> dict[str, float]:
    title = layout.header.title
    if title is None:
        return {"title_overrun": 0.0, "title_vs_headline": 0.0}
    voice = cfg.title_voice.model_copy(update={"size": layout.title_size})
    end_x = title.x + measure_voice(title.text, voice)
    content_right = layout.width - cfg.margin_x
    chip = layout.header.headline_chip
    return {
        "title_size": round(layout.title_size, 1),
        "title_end_x": round(end_x, 1),
        "content_right": round(content_right, 1),
        "title_overrun": round(end_x - content_right, 1),
        "title_vs_headline": round(end_x - chip.x, 1) if chip is not None else 0.0,
    }


def matrix_label_metrics(layout: Any, spec: Any, cfg: Any) -> dict[str, Any]:
    label_w = layout.col_x[0] - cfg.margin_x if layout.col_x else 0.0
    need = max((measure_voice(row.label, cfg.row_label_voice) for row in spec.rows), default=0.0) + 2 * cfg.cell_pad_x
    truncated = sum(1 for c in layout.cells if c.col == -1 and c.text.endswith("…"))
    summary = layout.summary.label if layout.summary is not None else None
    summary_overrun = 0.0
    if summary is not None and summary.text:
        summary_overrun = measure_voice(summary.text, cfg.summary_text_voice) + 2 * cfg.cell_pad_x - label_w
    return {
        "label_w": round(label_w, 1),
        "label_need": round(need, 1),
        "truncated_labels": truncated,
        "summary_label_overrun": round(summary_overrun, 1),
    }


def matrix_negative_rects(layout: Any) -> int:
    count = 0
    for cell in layout.cells:
        rects = [cell.box, cell.track, cell.bar_fill, cell.pill, cell.heat_tile, cell.heat_track, cell.heat_underline]
        rects.extend(chip.rect for chip in cell.chips)
        count += sum(1 for r in rects if r is not None and (r.w < 0 or r.h < 0))
    return count


def matrix_axis_vs_track(layout: Any) -> dict[str, float]:
    if layout.axis is None or not layout.axis.grid_lines:
        return {"axis_right": 0.0, "track_right": 0.0, "shift": 0.0}
    axis_right = max(line.x1 for line in layout.axis.grid_lines)
    tracks = [c.track for c in layout.cells if c.track is not None]
    track_right = max((t.x + t.w for t in tracks), default=0.0)
    return {
        "axis_right": round(axis_right, 1),
        "track_right": round(track_right, 1),
        "shift": round(track_right - axis_right, 1),
    }


def matrix_summary(layout: Any, spec: Any, cfg: Any) -> dict[str, Any]:
    return {
        "width": layout.width,
        "height": layout.height,
        "col_w": [round(w, 1) for w in layout.col_w],
        "header_overruns": matrix_header_overruns(layout, cfg),
        **matrix_title_metrics(layout, cfg),
        **matrix_label_metrics(layout, spec, cfg),
        "negative_rects": matrix_negative_rects(layout),
        "truncated_cells": sum(1 for c in layout.cells if c.col >= 0 and c.text.endswith("…")),
        **matrix_axis_vs_track(layout),
    }


# ── rendered SVG ────────────────────────────────────────────────────────────

_NUM = r"-?\d+(?:\.\d+)?"


def svg_body(svg: str) -> str:
    return svg[svg.rfind("</style>") :]


def svg_card_boxes(svg: str) -> list[Box]:
    return [
        (float(a), float(b), float(a) + float(c), float(b) + float(d))
        for a, b, c, d in re.findall(
            rf'<rect x="({_NUM})" y="({_NUM})" width="({_NUM})" height="({_NUM})"[^>]*-(?:cardbg|herobg)"',
            svg_body(svg),
        )
    ]


def svg_wire_paths(svg: str) -> list[str]:
    return [
        m.group(1)
        for m in re.finditer(r'<path\b[^>]*\bd="(M[^"]+)"[^>]*class="([^"]*)"', svg_body(svg))
        if "-branch" in m.group(2)
    ]


def svg_wire_card_crossings(svg: str) -> int:
    """Wire legs inside a card neither end of the wire touches — the rendered-artifact witness."""
    cards = svg_card_boxes(svg)
    crossings = 0
    for d in svg_wire_paths(svg):
        for polyline in flatten_path(d):
            ends = (polyline[0], polyline[-1])
            for box in cards:
                if any(box[0] - 2 <= e[0] <= box[2] + 2 and box[1] - 2 <= e[1] <= box[3] + 2 for e in ends):
                    continue
                if polyline_inside_length(polyline, box) > 0.0:
                    crossings += 1
    return crossings


def svg_ellipsis_count(svg: str) -> int:
    return sum(1 for t in parse_svg(svg).texts if "…" in t.content)


def svg_summary(svg: str) -> dict[str, Any]:
    facts = parse_svg(svg)
    return {
        "viewbox_w": facts.vb_w,
        "viewbox_h": facts.vb_h,
        "ellipses": svg_ellipsis_count(svg),
        "wire_card_crossings": svg_wire_card_crossings(svg),
    }


# ── unit-level ──────────────────────────────────────────────────────────────


def chart_ticks(v_max: int) -> list[str]:
    from hyperweave.render.chart_engine import _format_y_tick, _nice_y_ticks

    return [_format_y_tick(v) for v in _nice_y_ticks(v_max)]


def text_ink(text: str, *, family: str, size: float, weight: int, tracking_em: float = 0.0) -> float:
    return measure_text(text, font_family=family, font_size=size, font_weight=weight, letter_spacing_em=tracking_em)
