"""v0.3.13 rendering-invariant regression pins.

Cross-cutting guards caught in proofset visual review: stateless strip trailing,
chrome badge uppercase measure-vs-render, brutalist-light badge inline attrs,
cell-rhythm constant padding, adaptive status-indicator symmetry, adaptive strip
dividers, and the empty-state minimal-identity render.
"""

from __future__ import annotations

import re

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec


def test_brutalist_stateless_strip_trailing_is_minimal() -> None:
    """A DARK stateless strip ends a thin stroke clearance past the last cell,
    NOT a full strip_pad of trailing — so the last value's right margin mirrors
    its left (no lopsided gap). Uniform cells make the cell pitch equal the last
    cell's width, so the leftover trailing (right_gap - pitch) must be tiny.
    (Light substrates instead reserve a fixed ink bookend terminus, so this
    reclaim invariant is dark-only — celadon here.)"""
    svg = compose(
        ComposeSpec(type="strip", genome_id="brutalist", variant="celadon", title="repo", value="AA:1,BB:2,CC:3,DD:4")
    ).svg
    w = float(re.search(r'viewBox="0 0 ([\d.]+)', svg).group(1))
    seams = [float(m) for m in re.findall(r'data-hw-zone="metric-\d+" transform="translate\(([\d.]+),', svg)]
    pitch = seams[-1] - seams[-2]
    trailing = (w - seams[-1]) - pitch
    assert trailing < 8, (
        f"brutalist stateless trailing {trailing:.1f}px too large (was a full strip_pad 16 before the fix)"
    )


def test_chrome_badge_label_measured_uppercase_matches_render() -> None:
    """Chrome badge labels RENDER uppercase, so the label zone must be
    MEASURED uppercase too. A lowercase title 'chrome' must yield the
    uppercase-width textLength (~47), not the lowercase ~40 — else the wider
    uppercase render overflows the seam (the 'CHROME' overflow). Root cause was
    the chrome profile's ``badge_label_uppercase: false`` vs the template's
    uppercase render; the measure used lowercase while the render used upper."""
    svg = compose(ComposeSpec(type="badge", genome_id="chrome", variant="moth", title="chrome", value="moth")).svg
    label_text = re.search(r'data-hw-zone="label"[^>]*>([^<]+)<', svg).group(1)
    assert label_text == "CHROME", f"chrome badge label must render uppercase, got {label_text!r}"
    tl = float(re.search(r'data-hw-zone="label"[^>]*?textLength="([\d.]+)"', svg).group(1))
    assert tl > 44, (
        f"chrome label textLength {tl} must reflect the uppercase measure (~47), "
        "not the lowercase ~40 (measure/render case mismatch)"
    )


def test_brutalist_light_badge_inline_attrs_match_measure() -> None:
    """Measure-vs-render audit: the brutalist LIGHT badge renders inline font
    attrs (drift-prone) that must match the resolver's badge measure — JBM label
    11/700/0.06, value 11/700/0.04. The light partial had drifted (label weight
    600, value missing letter-spacing), sizing the zone for params it didn't
    render. Dark already matched; this pins light to the same measure."""
    svg = compose(
        ComposeSpec(type="badge", genome_id="brutalist", variant="archive", title="build", value="passing")
    ).svg
    label = re.search(r'data-hw-zone="label"[^>]*>', svg).group(0)
    value = re.search(r'data-hw-zone="value"[^>]*>', svg).group(0)
    assert 'font-weight="700"' in label, "light badge label weight must be 700 (matches dark + measure)"
    assert 'letter-spacing="0.06em"' in label, "light badge label letter-spacing must be 0.06em (measure)"
    assert 'letter-spacing="0.04em"' in value, "light badge value letter-spacing must be 0.04em (measure)"


def test_cell_layout_constant_padding_rhythm() -> None:
    """Cell rhythm: every cell carries a CONSTANT cell_pad gutter — the content
    is floored, THEN pad is added (not max(content+pad, floor)), so a short cell
    and a wide cell share the same padding. Floored short cells no longer absorb
    the floor as generous extra spacing (the README-AI-vs-VLLM gap mismatch)."""
    from hyperweave.config.registry import get_paradigms
    from hyperweave.core.cell_layout import TextSpec, compute_cell_layout

    sc = get_paradigms()["chrome"].strip

    def pad(label: str, value: str) -> float:
        lay = compute_cell_layout(
            TextSpec(
                label.upper(),
                sc.label_font_family,
                sc.label_font_size,
                sc.label_font_weight,
                sc.label_letter_spacing_em,
            ),
            TextSpec(value, sc.value_font_family, sc.value_font_size, sc.value_font_weight, sc.value_letter_spacing_em),
            cell_pad=sc.cell_pad,
            anchor=sc.metric_text_anchor,
            text_inset=sc.metric_text_x,
            min_cell_w=sc.cell_min_width,
        )
        return lay.cell_w - lay.content_w

    short = pad("PRS", "7")  # short content, above the floor → content-driven
    wide = pad("DOCKER", "23.1M")  # wide content → content-driven
    # ceil rounding allows ≤1px; both must sit at the constant cell_pad gutter.
    assert abs(short - sc.cell_pad) < 1.5, f"short cell padding {short} must be ~cell_pad {sc.cell_pad}"
    assert abs(wide - sc.cell_pad) < 1.5, f"wide cell padding {wide} must be ~cell_pad {sc.cell_pad}"
    assert abs(short - wide) < 1.5, f"short + wide cells must share rhythm: {short} vs {wide}"


def test_adaptive_stateful_status_indicator_is_symmetric() -> None:
    """Bug: the chrome/automata (adaptive) stateful status indicator sat closer
    to the right edge than to the last metric value. The pre-fix formula placed
    it at last_seam + pre_gap, but the last cell's own right gutter (cell_pad/2)
    already separates the value from the seam — so a constant pre_gap stacked on
    chrome's 48px gutter seated the diamond 40px from the value but 18px from the
    edge. The fix centers the indicator between the last cell's content-right
    edge and the trailing content edge (envelope edge / right flank), one code
    path for every adaptive genome. Both adaptive status partials are
    center-anchored on status_x, so status_x IS the indicator center."""
    from hyperweave.config.registry import get_paradigms

    for genome, variant, paradigm in [("chrome", "moth", "chrome"), ("automata", "teal", "cellular")]:
        svg = compose(
            ComposeSpec(type="strip", genome_id=genome, variant=variant, title="repo", value="STARS:2.9k,BUILD:passing")
        ).svg
        w = float(re.search(r'viewBox="0 0 ([\d.]+)', svg).group(1))
        center = float(re.search(r'data-hw-zone="status" transform="translate\(([\d.]+)', svg).group(1))
        flank = get_paradigms()[paradigm].strip.flank_width
        # Last metric cell: value text is middle-anchored at cell_w/2, so the cell
        # center is cell_x + value_x; the content block is max(label, value) wide.
        last = [b for b in re.split(r'(?=data-hw-zone="metric-\d+")', svg) if b.startswith('data-hw-zone="metric-')][-1]
        cell_x = float(re.search(r'transform="translate\(([\d.]+)', last).group(1))
        # value text is middle-anchored at cell_w/2; the x attr precedes the class.
        value_x = float(re.search(r'<text x="([\d.]+)"[^>]*?-metric-value"', last, re.S).group(1))
        content_w = max(float(t) for t in re.findall(r'textLength="([\d.]+)"', last))
        last_content_right = cell_x + value_x + content_w / 2.0
        trailing_edge = w - flank
        leading = center - last_content_right
        trailing = trailing_edge - center
        assert abs(leading - trailing) < 3, (
            f"{genome}: status indicator must sit symmetrically — lead {leading:.1f}px (from last value) "
            f"vs trail {trailing:.1f}px (to edge); pre-fix chrome was 40 vs 18"
        )
        assert trailing > 18, f"{genome}: status indicator trailing {trailing:.1f}px reads jammed against the edge"


def test_adaptive_strip_no_divider_after_last_cell() -> None:
    """Architecture: the adaptive strip pipeline (chrome/cellular) must honor the
    layout engine's per-cell show_leading_rule — the SAME flag brutalist consumes
    — drawing a LEADING divider before each cell except the first, and NONE after
    the last. The pre-fix template rendered an unconditional TRAILING divider
    after every cell, including a redundant one after the last; that divider
    became the status indicator's visible left-neighbor and pulled it off-center
    (automata's solid dividers exposed it; chrome's gradient dividers hid it).
    Every vertical divider must sit at or before the last cell's left seam."""
    for genome, variant in [("chrome", "moth"), ("automata", "amber")]:
        svg = compose(
            ComposeSpec(
                type="strip",
                genome_id=genome,
                variant=variant,
                title="repo",
                value="TESTS:failing,COVERAGE:87%,BUILD:warning",
            )
        ).svg
        blocks = [b for b in re.split(r'(?=data-hw-zone="metric-\d+")', svg) if b.startswith('data-hw-zone="metric-')]
        last_cell_left = float(re.search(r'transform="translate\(([\d.]+)', blocks[-1]).group(1))
        # vertical inter-cell dividers: x1 == x2 (back-reference), single-line form.
        divider_xs = [float(x) for x in re.findall(r'<line x1="([\d.]+)" y1="\d+" x2="\1"', svg)]
        assert divider_xs, f"{genome}: expected inter-metric dividers between cells"
        assert len(divider_xs) == len(blocks) - 1, (
            f"{genome}: expected {len(blocks) - 1} inter-metric dividers for {len(blocks)} metrics, "
            f"got {len(divider_xs)} (a trailing divider after the last cell would add one)"
        )
        assert max(divider_xs) <= last_cell_left + 1, (
            f"{genome}: divider at {max(divider_xs):.1f} sits past the last cell's left seam "
            f"({last_cell_left:.1f}) — a redundant trailing divider before the status terminus"
        )


def test_empty_strip_is_minimal_identity_only_all_genomes() -> None:
    """Empty-state (no metrics): every genome renders a minimal identity-only
    strip — height 52, NO metric zone, and a tight width (not the 543 elongated
    brutalist / 320 clamped chrome / 48-tall automata of before)."""
    for genome, variant in [("brutalist", "pulse"), ("chrome", ""), ("automata", "")]:
        svg = compose(ComposeSpec(type="strip", genome_id=genome, variant=variant, title="hyperweave", value="")).svg
        m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
        w, h = float(m.group(1)), float(m.group(2))
        assert h == 52, f"{genome}: empty strip height must be 52 (parity), got {h}"
        assert 'data-hw-zone="metric-' not in svg, f"{genome}: empty strip must render no metric zone"
        assert w < 240, f"{genome}: empty strip must be a tight identity-only width, got {w}"
