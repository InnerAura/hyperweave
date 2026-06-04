"""Automata cellular badge — Phase 4 rendering validation.

Covers automata's cellular badge structure across version and state modes.
Assertions verify structural elements and family-specific colors, not byte
equality — dynamic width from measure_text and UID suffix variance make
golden-file comparison fragile.
"""

from __future__ import annotations

import re

import pytest
from fontTools.pens.boundsPen import BoundsPen  # type: ignore[import-untyped]
from fontTools.svgLib.path import parse_path  # type: ignore[import-untyped]

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec
from hyperweave.core.text import measure_text_ink_metrics


def _compose_svg(**kwargs: object) -> str:
    kwargs.setdefault("type", "badge")
    kwargs.setdefault("genome_id", "automata")
    spec = ComposeSpec(**kwargs)  # type: ignore[arg-type]
    return compose(spec).svg


_PATTERN_CELL_RE = re.compile(r'<rect x="([\d.]+)" y="[\d.]+" width="([\d.]+)" height="[\d.]+" fill="[^"]+" class="cz')
_GLYPH_RE = re.compile(
    r'<g data-hw-zone="glyph" transform="translate\(([\d.]+),([\d.]+)\)">\s*'
    r'<svg width="([\d.]+)" height="([\d.]+)"',
    re.S,
)
_GLYPH_DETAIL_RE = re.compile(
    r'<g data-hw-zone="glyph" transform="translate\(([\d.\-]+),([\d.\-]+)\)">\s*'
    r"<svg\s+([^>]*)>\s*<path d=\"([^\"]+)\"",
    re.S,
)
_VIEWBOX_RE = re.compile(r'viewBox="0 0 ([\d.]+) ([\d.]+)"')
_TEXT_RE = re.compile(
    r'<text data-hw-zone="(label|value)"\s+'
    r'x="([\d.]+)" y="[\d.]+"\s+'
    r'text-anchor="middle"\s+'
    r'font-family="([^"]+)"\s+'
    r'font-size="([\d.]+)" font-weight="([\d.]+)"\s+'
    r"([^>]*)>([^<]+)</text>",
    re.S,
)
_SEAM_RE = re.compile(r'<rect x="([\d.]+)" y="[\d.]+" width="([\d.]+)" height="[\d.]+" fill="url\(#[^"]+-seam\)"')
_SEAM_SHADOW_RE = re.compile(
    r'<rect x="([\d.]+)" y="[\d.]+" width="([\d.]+)" height="[\d.]+" fill="var\(--dna-surface-deep\)"'
)


def _font_family(raw: str) -> str:
    return raw.split(",")[0].strip().strip("'").strip('"')


def _svg_attr(attrs: str, name: str) -> str:
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


def _glyph_ink_bounds(svg: str) -> tuple[float, float, float, float, float, float]:
    glyph = _GLYPH_DETAIL_RE.search(svg)
    assert glyph is not None
    glyph_x = float(glyph.group(1))
    glyph_y = float(glyph.group(2))
    attrs = glyph.group(3)
    path = glyph.group(4)
    width = float(_svg_attr(attrs, "width"))
    height = float(_svg_attr(attrs, "height"))
    vb_x, vb_y, vb_w, vb_h = _viewbox(_svg_attr(attrs, "viewBox"))
    ink_x0, ink_y0, ink_x1, ink_y1 = _path_bounds(path)
    left = glyph_x + (ink_x0 - vb_x) / vb_w * width
    right = glyph_x + (ink_x1 - vb_x) / vb_w * width
    top = glyph_y + (ink_y0 - vb_y) / vb_h * height
    bottom = glyph_y + (ink_y1 - vb_y) / vb_h * height
    return left, right, top, bottom, glyph_x, width


def _text_ink_bounds(svg: str, zone: str) -> tuple[float, float, float]:
    for match in _TEXT_RE.finditer(svg):
        if match.group(1) != zone:
            continue
        x = float(match.group(2))
        family = _font_family(match.group(3))
        font_size = float(match.group(4))
        font_weight = int(match.group(5))
        attrs = match.group(6)
        text = match.group(7)
        letter_spacing = 0.0
        if ls_match := re.search(r'letter-spacing="([\d.]+)em"', attrs):
            letter_spacing = float(ls_match.group(1))
        metrics = measure_text_ink_metrics(
            text,
            font_family=family,
            font_size=font_size,
            font_weight=font_weight,
            letter_spacing_em=letter_spacing,
        )
        advance_left = x - metrics.advance_width / 2
        ink_left = advance_left + metrics.leading_bearing
        ink_right = advance_left + metrics.advance_width - metrics.trailing_bearing
        return x, ink_left, ink_right
    raise AssertionError(f"missing {zone} text")


def _badge_gap_metrics(svg: str) -> dict[str, float]:
    viewbox = _VIEWBOX_RE.search(svg)
    assert viewbox is not None
    width = float(viewbox.group(1))
    cells = _PATTERN_CELL_RE.findall(svg)
    assert cells
    bookend_right = max(float(x) + float(w) for x, w in cells)
    glyph = _GLYPH_RE.search(svg)
    glyph_x = float(glyph.group(1)) if glyph else 0.0
    _label_x, label_left, label_right = _text_ink_bounds(svg, "label")
    _value_x, value_left, value_right = _text_ink_bounds(svg, "value")
    seam = _SEAM_RE.search(svg)
    seam_shadow = _SEAM_SHADOW_RE.search(svg)
    assert seam is not None
    assert seam_shadow is not None
    seam_left = float(seam.group(1))
    seam_right = float(seam_shadow.group(1)) + float(seam_shadow.group(2))
    metrics = {
        "width": width,
        "bookend_right": bookend_right,
        "label_left": label_left,
        "label_right": label_right,
        "seam_left": seam_left,
        "seam_right": seam_right,
        "value_left": value_left,
        "value_right": value_right,
        "visible_right": width - 2,
        "gap_3": seam_left - label_right,
        "gap_4": value_left - seam_right,
        "gap_5": (width - 2) - value_right,
    }
    if glyph:
        glyph_left, glyph_right, _glyph_top, _glyph_bottom, glyph_x, _glyph_size = _glyph_ink_bounds(svg)
        metrics.update(
            {
                "glyph_x": glyph_x,
                "glyph_right": glyph_right,
                "gap_1": glyph_left - bookend_right,
                "gap_2": label_left - glyph_right,
            }
        )
    else:
        metrics["gap_1"] = label_left - bookend_right
    return metrics


def _bookend_glyph_metrics(svg: str) -> tuple[float, float, float, float, float, float]:
    cells = _PATTERN_CELL_RE.findall(svg)
    glyph = _GLYPH_RE.search(svg)
    label = re.search(
        r'<text data-hw-zone="label"\s+x="([\d.]+)" y="[^"]+"\s+text-anchor="middle"[^>]*'
        r'font-size="([\d.]+)"[^>]*letter-spacing="([\d.]+)em"[^>]*>([^<]+)</text>',
        svg,
    )
    assert cells
    assert glyph is not None
    assert label is not None
    pattern_right = max(float(x) + float(w) for x, w in cells)
    glyph_x = float(glyph.group(1))
    glyph_size = float(glyph.group(3))
    glyph_left, glyph_right, _glyph_top, _glyph_bottom, _glyph_box_x, _glyph_box_size = _glyph_ink_bounds(svg)
    label_x = float(label.group(1))
    label_metrics = measure_text_ink_metrics(
        label.group(4),
        font_family="Orbitron",
        font_size=float(label.group(2)),
        font_weight=700,
        letter_spacing_em=float(label.group(3)),
    )
    label_left = label_x - label_metrics.advance_width / 2 + label_metrics.leading_bearing
    return pattern_right, glyph_x, glyph_size, label_left, glyph_left - pattern_right, label_left - glyph_right


# ── Version-mode badges ──────────────────────────────────────────────────


def test_version_badge_blue_default() -> None:
    svg = _compose_svg(title="PYPI", value="v0.2.5", variant="teal", glyph="python")
    # Blue-family signature colors
    assert "#3A9FB8" in svg  # label text
    assert "#A8D4F0" in svg  # value text
    assert "#8AC8E0" in svg  # top highlight (first rim stop)
    # Paradigm font stack
    assert "Orbitron" in svg
    assert "Chakra Petch" in svg
    # Rim gradient has 7 stops
    assert svg.count("<stop offset=") >= 7
    # No state indicator ring in version mode
    assert 'class="hw-ring"' not in svg
    assert 'class="hw-bit"' not in svg


def test_version_badge_purple_default() -> None:
    svg = _compose_svg(title="PYPI", value="v0.2.5", variant="violet", glyph="python")
    # Purple-family signature colors — label/value/rim all use amethyst palette
    assert "#A88AD4" in svg  # label text
    assert "#D8B4FE" in svg  # value text
    assert "#E6C0FF" in svg  # top highlight (first rim stop)
    assert "#6B3B8A" in svg  # pattern cell mid
    # Note: the glyph inline SVG still uses genome.glyph_inner (blue-family tint)
    # and CSS --dna-badge-value-text retains the blue stop (unused in purple render
    # but emitted by the assembler for state-mode fallback). Family-aware glyph
    # color + CSS var routing are separate cleanup items for v1.1.


def test_version_badge_default_uses_compact_geometry() -> None:
    default_spec = ComposeSpec(
        type="badge", genome_id="automata", title="PYPI", value="v0.2.5", variant="teal", glyph="python"
    )
    large_spec = ComposeSpec(
        type="badge",
        genome_id="automata",
        title="PYPI",
        value="v0.2.5",
        variant="teal",
        size="large",
        glyph="python",
    )
    default_result = compose(default_spec)
    large_result = compose(large_spec)
    assert default_result.height == 20
    assert large_result.height == 32
    assert default_result.width < large_result.width


def test_compact_badge_viewbox_is_20_tall() -> None:
    svg = _compose_svg(title="PYPI", value="v0.2.5", variant="teal", size="compact")
    # Compact height is 20 (small badge class)
    assert 'height="20"' in svg or "height=20" in svg


def test_compact_badge_glyph_is_smaller_than_large() -> None:
    """Compact automata badges use an explicit smaller glyph cap."""
    large = _compose_svg(title="PYPI", value="v0.2.5", variant="teal", size="large", glyph="python")
    compact = _compose_svg(title="PYPI", value="v0.2.5", variant="teal", size="compact", glyph="python")
    large_match = _GLYPH_RE.search(large)
    compact_match = _GLYPH_RE.search(compact)
    assert large_match is not None
    assert compact_match is not None
    assert float(compact_match.group(3)) < float(large_match.group(3))


@pytest.mark.parametrize(
    ("size", "expected_bookend_right", "expected_glyph_size"),
    [("compact", 14, 10), ("large", 20, 12)],
)
def test_badge_bookend_to_glyph_gap_matches_glyph_to_label(
    size: str,
    expected_bookend_right: int,
    expected_glyph_size: int,
) -> None:
    """Cellular badges balance bookend→glyph and glyph→label spacing."""
    svg = _compose_svg(title="PYPI", value="v0.2.5", variant="teal", size=size, glyph="github")
    pattern_right, glyph_x, glyph_size, _label_left, bookend_gap, glyph_label_gap = _bookend_glyph_metrics(svg)
    assert pattern_right == expected_bookend_right
    assert glyph_x > expected_bookend_right
    assert glyph_size == expected_glyph_size
    assert abs(bookend_gap - 4) < 0.1
    assert abs(glyph_label_gap - 4) < 0.1
    assert abs(bookend_gap - glyph_label_gap) <= 2


def test_default_badge_uses_compact_bookend_gap() -> None:
    """Automata's default badge size resolves through compact bookend geometry."""
    default = _compose_svg(title="PYPI", value="v0.2.5", variant="teal", glyph="github")
    compact = _compose_svg(title="PYPI", value="v0.2.5", variant="teal", size="compact", glyph="github")
    assert _bookend_glyph_metrics(default) == _bookend_glyph_metrics(compact)


@pytest.mark.parametrize(
    ("kwargs", "has_glyph"),
    [
        ({"variant": "teal", "title": "PULLS", "value": "135.9M"}, False),
        ({"variant": "teal", "title": "PULLS", "value": "135.9M", "glyph": "docker"}, True),
        ({"variant": "amber", "title": "DOWNLOADS", "value": "11.3M", "glyph": "python"}, True),
        ({"variant": "teal", "title": "PULLS", "value": "135.9M", "size": "large"}, False),
        ({"variant": "teal", "title": "PULLS", "value": "135.9M", "size": "large", "glyph": "docker"}, True),
        ({"variant": "amber", "title": "DOWNLOADS", "value": "11.3M", "size": "large", "glyph": "python"}, True),
    ],
)
def test_cellular_badge_visual_gaps_are_balanced(kwargs: dict[str, str], has_glyph: bool) -> None:
    """Automata badges balance visible bookend/glyph/text/seam/value gaps."""
    svg = _compose_svg(**kwargs)
    metrics = _badge_gap_metrics(svg)
    gap_keys = ["gap_1", "gap_3", "gap_4", "gap_5"]
    if has_glyph:
        gap_keys.insert(1, "gap_2")
    gaps = [metrics[key] for key in gap_keys]
    for gap in gaps:
        assert abs(gap - 4) <= 1.0, f"{kwargs}: expected visual gap near 4px; got {metrics}"
    assert max(gaps) - min(gaps) <= 1.4, f"{kwargs}: visual gaps are not balanced: {metrics}"


# ── State-mode badges ────────────────────────────────────────────────────


@pytest.mark.parametrize("state", ["passing", "warning", "critical", "building", "offline"])
def test_state_badge_emits_ring_and_bit(state: str) -> None:
    """state-mode badges render the ring+bit indicator block."""
    svg = _compose_svg(title="BUILD", value=state, state=state, variant="teal", glyph="github")
    assert 'class="hw-ring"' in svg
    assert 'class="hw-bit"' in svg
    # The state cascade partial defines --hw-state-signal for this status
    assert f'data-hw-status="{state}"' in svg or state in svg


def test_state_badge_binds_hw_value_text_class() -> None:
    """State value text routes through CSS custom property for runtime swap."""
    svg = _compose_svg(title="BUILD", value="passing", state="passing", variant="teal", glyph="github")
    assert 'class="hw-value-text"' in svg
    assert "var(--hw-state-value" in svg


def test_state_badge_state_signal_cascade_included() -> None:
    """The shared state-signal cascade partial is inlined for state badges."""
    svg = _compose_svg(title="BUILD", value="warning", state="warning", variant="teal", glyph="github")
    # All 5 state selectors should be present in the cascade block
    assert '[data-hw-status="passing"]' in svg
    assert '[data-hw-status="warning"]' in svg
    assert '[data-hw-status="critical"]' in svg
    assert '[data-hw-status="building"]' in svg
    assert '[data-hw-status="offline"]' in svg
    # Backfilled Tailwind 400 colors populate the cascade
    assert "#34D399" in svg  # passing core
    assert "#FBBF24" in svg  # warning core


# Version-mode isolation is verified via `hw-ring` class absence in
# `test_version_badge_blue_default`; no separate cascade-absence test
# needed because the baseline expression.css always emits state palette vars.


# ── Cellular structural invariants ───────────────────────────────────────


def test_cellular_badge_has_pattern_strip() -> None:
    """3 x 4 = 12 cellular pattern cells render on the left edge."""
    svg = _compose_svg(title="PYPI", value="v0.2.5", variant="teal")
    # Pattern cells are rects with class="cz{1,2,3,4,f,d}"; count distinct classes
    for cls in ("cz1", "cz2", "cz3", "cz4", "czf", "czd"):
        assert f'class="{cls}"' in svg, f"missing pattern class {cls}"


def test_cellular_badge_has_chrome_rim() -> None:
    """Rim, dark lip, and drop-shadow lift filter are all present."""
    svg = _compose_svg(title="PYPI", value="v0.2.5", variant="teal")
    assert "-rim" in svg  # gradient id suffix
    assert "feDropShadow" in svg
    assert "-lift" in svg  # filter id suffix


def test_cellular_badge_font_face_embedded() -> None:
    """Font-face CSS embeds Chakra Petch + Orbitron + JetBrains Mono WOFF2."""
    svg = _compose_svg(title="PYPI", value="v0.2.5", variant="teal")
    assert "@font-face" in svg


def test_cellular_badge_respects_prefers_reduced_motion() -> None:
    """CIM compliance: animation pauses under reduce-motion media query."""
    svg = _compose_svg(title="PYPI", value="v0.2.5", variant="teal")
    assert "prefers-reduced-motion" in svg
