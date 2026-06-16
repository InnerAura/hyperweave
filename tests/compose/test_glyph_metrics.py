"""Glyph ink metrics and badge alignment guards."""

from __future__ import annotations

import re

from fontTools.pens.boundsPen import BoundsPen  # type: ignore[import-untyped]
from fontTools.svgLib.path import parse_path  # type: ignore[import-untyped]

from hyperweave.compose.engine import compose
from hyperweave.config.settings import get_settings
from hyperweave.core.models import ComposeSpec
from hyperweave.core.text import measure_text_ink_metrics
from hyperweave.render.glyph_metrics import compute_glyph_ink_metrics, compute_glyph_render_metrics
from hyperweave.render.glyphs import load_glyphs

_GLYPH_RE = re.compile(
    r'<g data-hw-zone="glyph" transform="translate\(([\d.\-]+),([\d.\-]+)\)">\s*'
    r"<svg\s+([^>]*)>\s*<path d=\"([^\"]+)\"",
    re.S,
)
_LABEL_RE = re.compile(
    r'<text data-hw-zone="label"\s+x="[\d.\-]+" y="([\d.\-]+)"\s+text-anchor="[^"]+"\s+'
    r"([^>]*)>([^<]+)</text>",
    re.S,
)


def _glyphs() -> dict[str, dict[str, str]]:
    return load_glyphs(get_settings().data_dir / "registries" / "glyphs.json")


def _attr(attrs: str, name: str) -> str:
    match = re.search(rf'{name}="([^"]+)"', attrs)
    assert match is not None
    return match.group(1)


def _viewbox(raw: str) -> tuple[float, float, float, float]:
    values = [float(part) for part in raw.replace(",", " ").split()]
    assert len(values) == 4
    return values[0], values[1], values[2], values[3]


def _path_bounds(path: str) -> tuple[float, float, float, float]:
    pen = BoundsPen(None)
    parse_path(path, pen)
    assert pen.bounds is not None
    x0, y0, x1, y1 = pen.bounds
    return float(x0), float(y0), float(x1), float(y1)


def _font_family(raw: str) -> str:
    family = raw.split(",")[0].strip().strip("'").strip('"')
    return "JetBrains Mono" if family.startswith("var(") else family


def _rendered_glyph_ink_center_y(svg: str) -> float:
    match = _GLYPH_RE.search(svg)
    assert match is not None
    glyph_y = float(match.group(2))
    attrs = match.group(3)
    path = match.group(4)
    height = float(_attr(attrs, "height"))
    vb_x, vb_y, vb_w, vb_h = _viewbox(_attr(attrs, "viewBox"))
    _ = (vb_x, vb_w)
    _ink_x0, ink_y0, _ink_x1, ink_y1 = _path_bounds(path)
    return glyph_y + (((ink_y0 + ink_y1) / 2.0) - vb_y) / vb_h * height


def _rendered_label_ink_center_y(svg: str) -> float:
    match = _LABEL_RE.search(svg)
    assert match is not None
    text_y = float(match.group(1))
    attrs = match.group(2)
    text = match.group(3)
    if 'dominant-baseline="central"' in attrs:
        return text_y
    metrics = measure_text_ink_metrics(
        text,
        font_family=_font_family(_attr(attrs, "font-family")),
        font_size=float(_attr(attrs, "font-size")),
        font_weight=int(float(_attr(attrs, "font-weight"))),
        letter_spacing_em=float(re.search(r'letter-spacing="([\d.]+)em"', attrs).group(1))  # type: ignore[union-attr]
        if "letter-spacing" in attrs
        else 0.0,
    )
    return text_y + metrics.ink_center_offset_y


def test_registry_glyphs_have_programmatic_ink_metrics() -> None:
    """Every registry glyph path must expose computed nonzero ink bounds."""
    for glyph_id, glyph in _glyphs().items():
        metrics = compute_glyph_ink_metrics(glyph_id, glyph["path"], glyph["viewBox"])
        assert metrics.ink_w > 0, glyph_id
        assert metrics.ink_h > 0, glyph_id
        assert metrics.area_ratio > 0, glyph_id


def test_area_capped_optical_scale_balances_docker_and_github() -> None:
    """Docker's sparse mark scales up to comparable visual area without hand tuning."""
    glyphs = _glyphs()
    github = compute_glyph_render_metrics("github", glyphs["github"]["path"], glyphs["github"]["viewBox"], 10)
    docker = compute_glyph_render_metrics("docker", glyphs["docker"]["path"], glyphs["docker"]["viewBox"], 10)

    assert docker.source.area_ratio < github.source.area_ratio
    assert docker.optical_scale > github.optical_scale
    assert 0.95 <= docker.rendered_ink_area / github.rendered_ink_area <= 1.05


def test_normalized_viewbox_centers_all_registry_glyph_ink() -> None:
    """The generated viewBox centers ink in the render box for every glyph."""
    for glyph_id, glyph in _glyphs().items():
        render = compute_glyph_render_metrics(glyph_id, glyph["path"], glyph["viewBox"], 12)
        assert abs(render.ink_left_inset - ((12 - render.rendered_ink_w) / 2.0)) < 0.001, glyph_id
        assert abs(render.ink_top_inset - ((12 - render.rendered_ink_h) / 2.0)) < 0.001, glyph_id


def test_badge_glyph_ink_centers_match_label_ink_centers_for_all_registry_glyphs() -> None:
    """Badge glyph ink center must track label ink center across all paradigms."""
    failures: list[str] = []
    for genome_id in ("automata", "brutalist", "chrome"):
        variant = "teal" if genome_id == "automata" else ""
        for glyph_id in _glyphs():
            svg = compose(
                ComposeSpec(
                    type="badge",
                    genome_id=genome_id,
                    variant=variant,
                    title="PULLS",
                    value="135.9M",
                    glyph=glyph_id,
                )
            ).svg
            delta = _rendered_glyph_ink_center_y(svg) - _rendered_label_ink_center_y(svg)
            if abs(delta) >= 0.3:
                failures.append(f"{genome_id}:{glyph_id}:{delta:.3f}")
    assert failures == []


def test_brutalist_and_chrome_badge_slots_stay_pinned() -> None:
    """Normalized glyph rendering must not move existing non-cellular badge slots."""
    brutalist = compose(
        ComposeSpec(type="badge", genome_id="brutalist", title="PULLS", value="135.9M", glyph="github")
    ).svg
    chrome = compose(ComposeSpec(type="badge", genome_id="chrome", title="PULLS", value="135.9M", glyph="github")).svg

    assert 'viewBox="0 0 124 20"' in brutalist
    assert 'transform="translate(9.0,3.8)"' in brutalist
    # chrome width grew 2px in v0.3.14: right_canvas_inset=2 reserves the metallic
    # bezel so trailing content pads to the well's inner edge, not the badge edge.
    assert 'viewBox="0 0 125 20"' in chrome
    assert 'transform="translate(11.0,4.5)"' in chrome
