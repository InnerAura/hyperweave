"""Receipt resolver + section-layout tests (the primer receipt).

Covers the section dataclasses' extremes (the explicit quality bar):
* tool-spend top-N + '+N OTHERS' overflow; remainder-token accounting
* cost-by-model segment widths summing EXACTLY to 752; solo / keyed / '+N more'
* metrics zero-cases (0 errors still shows '0 ERRORS')
* model-mix suppressed for a solo-model run
* variant geometry-identical (only chromatics differ across the 8 variants)
* the embedded payload stays compact / data-only and the envelope id hashes it
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

import pytest

from hyperweave.compose.engine import compose
from hyperweave.compose.resolvers.receipt_sections import (
    CONTENT_W,
    LEFT_RAIL,
    RIGHT_RAIL,
    build_cost_by_model,
    build_metrics,
    build_model_mix,
    build_tool_spend,
)
from hyperweave.core.models import ComposeSpec
from hyperweave.core.text import measure_text

_MONO_FF = "JetBrains Mono"  # the one real metric LUT (matches the resolver's _MONO)


def _dollars(cost: str) -> float:
    """Parse a '$1,234.56' cost string back to a float (test helper)."""
    return float(cost.replace("$", "").replace(",", ""))


_PALETTE: dict[str, str] = {
    "ramp": ["#FAFAFA", "#D7D7D7", "#B5B5B5", "#929292", "#6F6F6F"],  # type: ignore[dict-item]
    "area_fill": "#FAFAFA",
    "signal": "#FAFAFA",
    "track": "#1A1A1A",
    "track_stroke": "#262626",
    "grid_ink": "#E5E5E5",
    "eyebrow": "#8A8A8A",
    "label_ink": "#E5E5E5",
    "value_ink": "#FAFAFA",
    "dim_ink": "#8A8A8A",
    "error": "#EF4444",
    "ink": "#E5E5E5",
    "ink_secondary": "#8A8A8A",
    "stroke": "#262626",
    "surface_1": "#141414",
    "surface_2": "#1A1A1A",
}


SPECIMEN_PAYLOAD: dict[str, Any] = {
    "session": "398ce70f",
    "model": "opus-4.7",
    "cost_usd": 175.01,
    "models": [
        {"name": "opus-4.7", "role": "main thread", "cost_usd": 128.00, "cost_pct": 73},
        {"name": "sonnet-4.6", "role": "subagent", "cost_usd": 39.00, "cost_pct": 22},
        {"name": "haiku-4.5", "role": "2 subagents", "cost_usd": 8.01, "cost_pct": 5},
    ],
    "dominant": "opus-4.7",
    "cost_basis": "public per-token rates",
    "estimate": True,
    "tokens": {
        "total": 262400000,
        "in": 157500,
        "out": 867300,
        "cache_read": 257600000,
        "cache_write": 3800000,
        "working": 1024800,
    },
    "calls": 562,
    "stages": 55,
    "turns": 31,
    "errors": 15,
    "active_min": 157,
    "context": {
        "window": 200000,
        "peak_ctx": 196000,
        "events": [
            {"min": 31, "cmd": "compact", "to": 38000},
            {"min": 62, "cmd": "clear", "to": 6000},
            {"min": 92, "cmd": "auto", "to": 40000},
            {"min": 138, "cmd": "compact", "to": 38000},
        ],
        "note": "modelled",
    },
    "tools": [
        {"name": "Edit", "tok": 709300, "calls": 242, "err": 6, "class": "mutate"},
        {"name": "Bash", "tok": 116400, "calls": 162, "err": 2, "class": "execute"},
        {"name": "Read", "tok": 94600, "calls": 116, "err": 1, "class": "explore"},
        {"name": "TaskCreate", "tok": 30200, "calls": 9, "err": 0, "class": "coordinate"},
        {"name": "TaskUpdate", "calls": 18},
        {"name": "ExitPlanMode", "calls": 4, "err": 3},
        {"name": "Write", "calls": 3},
        {"name": "AskUserQuestion", "calls": 3, "err": 3},
        {"name": "Agent", "calls": 3},
        {"name": "ToolSearch", "calls": 2},
    ],
}


# --------------------------------------------------------------------------- #
# cost-by-model: segment math closes on the rail                              #
# --------------------------------------------------------------------------- #


class TestCostByModelSegments:
    def test_segments_sum_exactly_to_content_width(self) -> None:
        cbm = build_cost_by_model(SPECIMEN_PAYLOAD, palette=_PALETTE)
        total = sum(s.w for s in cbm.segments)
        assert abs(total - CONTENT_W) < 1e-6, f"segments must close on {CONTENT_W}, got {total}"

    def test_last_segment_lands_on_right_rail(self) -> None:
        cbm = build_cost_by_model(SPECIMEN_PAYLOAD, palette=_PALETTE)
        last = cbm.segments[-1]
        assert abs((last.x + last.w) - RIGHT_RAIL) < 0.05

    def test_rows_sort_by_cost_descending(self) -> None:
        shuffled = [
            {"name": "mid", "role": "subagent", "cost_usd": 30.0, "cost_pct": 23},
            {"name": "top", "role": "main thread", "cost_usd": 90.0, "cost_pct": 69},
            {"name": "low", "role": "subagent", "cost_usd": 10.0, "cost_pct": 8},
        ]
        cbm = build_cost_by_model({**SPECIMEN_PAYLOAD, "models": shuffled}, palette=_PALETTE)
        assert [r.name for r in cbm.rows] == ["top", "mid", "low"]
        costs = [_dollars(r.cost) for r in cbm.rows]
        assert costs == sorted(costs, reverse=True)

    def test_markers_color_map_to_segments(self) -> None:
        # A reader maps a row to its slice: marker fill == segment fill, in order.
        cbm = build_cost_by_model(SPECIMEN_PAYLOAD, palette=_PALETTE)
        assert [r.marker_fill for r in cbm.rows] == [s.fill for s in cbm.segments]

    def test_solo_model_plain_one_row(self) -> None:
        solo = {**SPECIMEN_PAYLOAD, "models": [SPECIMEN_PAYLOAD["models"][0]]}
        cbm = build_cost_by_model(solo, palette=_PALETTE)
        assert len(cbm.segments) == 1
        assert cbm.segments[0].w == pytest.approx(CONTENT_W, abs=0.05)
        assert cbm.count_label == ""  # no count for a solo run
        assert not cbm.rich
        assert cbm.dividers == []
        assert len(cbm.rows) == 1

    def test_two_models_stay_plain(self) -> None:
        # ≤2 models: no right-eyebrow, no dividers, no closing rule (the cream case).
        models = SPECIMEN_PAYLOAD["models"][:2]
        cbm = build_cost_by_model({**SPECIMEN_PAYLOAD, "models": models}, palette=_PALETTE)
        assert not cbm.rich
        assert cbm.count_label == ""
        assert cbm.dividers == []
        assert len(cbm.rows) == 2

    def test_three_plus_models_go_rich(self) -> None:
        # ≥3 models: right-eyebrow count + one divider per internal boundary.
        cbm = build_cost_by_model(SPECIMEN_PAYLOAD, palette=_PALETTE)  # 3 models
        assert cbm.rich
        assert cbm.count_label == "3 MODELS · WITH SUBAGENTS"
        assert len(cbm.dividers) == len(cbm.segments) - 1
        assert len(cbm.rows) == 3

    def test_many_models_all_render_no_collapse(self) -> None:
        models = [
            {"name": "opus-4.7", "role": "main thread", "cost_usd": 100, "cost_pct": 50},
            {"name": "sonnet-4.6", "role": "3 subagents", "cost_usd": 40, "cost_pct": 20},
            {"name": "haiku-4.5", "role": "subagent", "cost_usd": 30, "cost_pct": 15},
            {"name": "gpt-5.4", "role": "subagent", "cost_usd": 20, "cost_pct": 10},
            {"name": "gemini-3", "role": "subagent", "cost_usd": 10, "cost_pct": 5},
        ]
        cbm = build_cost_by_model({**SPECIMEN_PAYLOAD, "models": models}, palette=_PALETTE)
        # No '+N more' collapse: every model gets a segment AND a row.
        assert len(cbm.segments) == 5
        assert len(cbm.rows) == 5
        assert sum(s.w for s in cbm.segments) == pytest.approx(CONTENT_W, abs=1e-6)

    def test_main_thread_switch_omits_subagents_suffix(self) -> None:
        # 3 main-thread models (a model switch): "N MODELS", no "WITH SUBAGENTS".
        models = [
            {"name": "opus-4.7", "role": "main thread", "cost_usd": 60, "cost_pct": 60},
            {"name": "sonnet-4.6", "role": "main thread", "cost_usd": 30, "cost_pct": 30},
            {"name": "haiku-4.5", "role": "main thread", "cost_usd": 10, "cost_pct": 10},
        ]
        cbm = build_cost_by_model({**SPECIMEN_PAYLOAD, "models": models}, palette=_PALETTE)
        assert cbm.count_label == "3 MODELS"

    def test_sub_one_percent_sliver_renders_and_reads_lt1(self) -> None:
        # The 99% + 1% sliver: the tiny model still gets a (thin) segment + a row,
        # and a non-zero cost that rounds to 0% reads "<1%", never a bare "0%".
        models = [
            {"name": "opus-4.7", "role": "main thread", "cost_usd": 607.57, "cost_pct": 100},
            {"name": "haiku-4.5", "role": "11 subagents", "cost_usd": 2.59, "cost_pct": 0},
        ]
        cbm = build_cost_by_model({**SPECIMEN_PAYLOAD, "models": models}, palette=_PALETTE)
        assert cbm.segments[-1].w > 0  # sliver is visible, not zero-width
        assert cbm.rows[-1].pct == "<1%"
        assert cbm.rows[-1].cost == "$2.59"

    def test_role_display_forms(self) -> None:
        models = [
            {"name": "a", "role": "main thread", "cost_usd": 50, "cost_pct": 50},
            {"name": "b", "role": "1 subagents", "cost_usd": 30, "cost_pct": 30},
            {"name": "c", "role": "6 subagents", "cost_usd": 20, "cost_pct": 20},
        ]
        cbm = build_cost_by_model({**SPECIMEN_PAYLOAD, "models": models}, palette=_PALETTE)
        assert [r.role for r in cbm.rows] == ["main thread", "subagent", "subagents ×6"]  # noqa: RUF001

    def test_dominant_name_in_wide_bar_sliver_skips(self) -> None:
        # A wide dominant segment carries an in-bar name; a thin sliver carries none.
        models = [
            {"name": "opus-4.7", "role": "main thread", "cost_usd": 607.57, "cost_pct": 100},
            {"name": "haiku-4.5", "role": "subagent", "cost_usd": 2.59, "cost_pct": 0},
        ]
        cbm = build_cost_by_model({**SPECIMEN_PAYLOAD, "models": models}, palette=_PALETTE)
        names = {bn.text for bn in cbm.bar_names}
        assert "opus-4.7" in names
        assert "haiku-4.5" not in names  # sliver too thin for a label

    def test_long_name_does_not_collide_with_figures(self) -> None:
        # A long model name + role must not reach the right-anchored cost column.
        models = [
            {"name": "anthropic-claude-opus-4.7-preview", "role": "6 subagents", "cost_usd": 90, "cost_pct": 90},
            {"name": "x", "role": "main thread", "cost_usd": 10, "cost_pct": 10},
        ]
        cbm = build_cost_by_model({**SPECIMEN_PAYLOAD, "models": models}, palette=_PALETTE)
        row = cbm.rows[0]
        label = f"{row.name} · {row.role}"
        label_w = measure_text(label, font_family=_MONO_FF, font_size=11.0, font_weight=700, letter_spacing_em=0.0)
        cost_w = measure_text(row.cost, font_family=_MONO_FF, font_size=11.0, font_weight=700, letter_spacing_em=0.0)
        assert row.text_x + label_w < cbm.cost_x - cost_w


# --------------------------------------------------------------------------- #
# tool-spend: overflow + remainder accounting                                 #
# --------------------------------------------------------------------------- #


class TestToolSpendOverflow:
    def test_long_list_collapses_tail_into_others_row(self) -> None:
        ts = build_tool_spend(SPECIMEN_PAYLOAD, palette=_PALETTE)
        names = [r.name for r in ts.rows]
        assert any(n.startswith("+") and "others" in n for n in names)

    def test_others_row_tokens_are_remainder_of_working_total(self) -> None:
        """'+N others' tokens = working total minus the shown rows (sparse tail)."""
        ts = build_tool_spend(SPECIMEN_PAYLOAD, palette=_PALETTE)
        others = next(r for r in ts.rows if r.is_tail)
        # working 1024800 minus (Edit 709300 + Bash 116400 + Read 94600 + TaskCreate 30200) = 74300
        assert others.tokens == "74.3K"

    def test_row_count_fits_vertical_band(self) -> None:
        ts = build_tool_spend(SPECIMEN_PAYLOAD, palette=_PALETTE)
        # Rows from y137 pitch 23 down to the legend at y261 → at most 5 rows.
        assert len(ts.rows) <= 5
        for r in ts.rows:
            assert r.accent_y < 261.0

    def test_leader_bar_fills_track(self) -> None:
        ts = build_tool_spend(SPECIMEN_PAYLOAD, palette=_PALETTE)
        # The top tool (Edit) is the width reference → full 322px bar.
        assert ts.rows[0].bar_fill_w == pytest.approx(322.0, abs=0.1)

    def test_pct_is_share_of_session_working(self) -> None:
        ts = build_tool_spend(SPECIMEN_PAYLOAD, palette=_PALETTE)
        # Edit 709300 / working 1024800 = 69%.
        assert ts.rows[0].pct == "69%"

    def test_errcount_only_on_rows_with_errors(self) -> None:
        ts = build_tool_spend(SPECIMEN_PAYLOAD, palette=_PALETTE)
        edit = next(r for r in ts.rows if r.name == "Edit")
        assert edit.err == 6
        # A zero-error tool would carry err == 0 (the template suppresses the badge).
        read = next(r for r in ts.rows if r.name == "Read")
        assert read.err == 1

    def test_short_list_renders_all_rows_no_overflow(self) -> None:
        payload = {
            **SPECIMEN_PAYLOAD,
            "tools": [
                {"name": "Edit", "tok": 1000, "calls": 2, "class": "mutate"},
                {"name": "Read", "tok": 500, "calls": 1, "class": "explore"},
            ],
        }
        ts = build_tool_spend(payload, palette=_PALETTE)
        assert all(not r.is_tail for r in ts.rows)
        assert len(ts.rows) == 2


# --------------------------------------------------------------------------- #
# metrics + model-mix zero / solo cases                                       #
# --------------------------------------------------------------------------- #


class TestMetricsAndModelMix:
    def test_zero_errors_still_shows_errors_cell(self) -> None:
        m = build_metrics({**SPECIMEN_PAYLOAD, "errors": 0}, palette=_PALETTE)
        err_cell = next(c for c in m.cells if c.label == "ERRORS")
        assert err_cell.value == "0"
        assert err_cell.is_error  # tone is still semantic-red even at 0

    def test_metric_cells_are_ascending_x(self) -> None:
        m = build_metrics(SPECIMEN_PAYLOAD, palette=_PALETTE)
        xs = [c.value_x for c in m.cells]
        assert xs == sorted(xs)
        assert xs[0] == LEFT_RAIL
        # last cell has no trailing separator
        assert m.cells[-1].show_sep is False

    def test_solo_model_shows_single_model_block(self) -> None:
        # The slot is always present (the prototypes carry it); a solo run names
        # the model without the MIX / DOMINANT / multi-percent comparison.
        solo = {**SPECIMEN_PAYLOAD, "models": [SPECIMEN_PAYLOAD["models"][0]]}
        mm = build_model_mix(solo, palette=_PALETTE)
        assert mm.show is True
        assert mm.eyebrow == "MODEL"
        assert mm.dominant == "opus-4.7"
        assert mm.dominant_suffix == ""
        assert mm.split == "100% spend"

    def test_multi_model_mix_names_dominant(self) -> None:
        mm = build_model_mix(SPECIMEN_PAYLOAD, palette=_PALETTE)
        assert mm.show is True
        assert mm.dominant == "opus-4.7"
        assert "3 MODELS" in mm.eyebrow
        assert mm.split.startswith("73% spend")


# --------------------------------------------------------------------------- #
# Variant geometry-identical (only chromatics differ)                         #
# --------------------------------------------------------------------------- #

_VARIANTS = ["noir", "carbon", "space", "anvil", "porcelain", "cream", "dusk", "petrol"]


def _geometry_skeleton(svg: str) -> list[tuple[str, tuple[tuple[str, str], ...]]]:
    """Extract (tag, coord-attrs) for every shape — colour-free geometry."""
    out: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    for m in re.finditer(r"<(text|rect|line|circle|use|path)\b([^>]*)>", svg):
        tag, attrs = m.group(1), m.group(2)
        coords: dict[str, str] = {}
        for k in ("x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "width", "height", "d", "href"):
            mm = re.search(rf'\b{k}="([^"]*)"', attrs)
            if mm:
                coords[k] = mm.group(1)
        out.append((tag, tuple(sorted(coords.items()))))
    return out


class TestVariantGeometryIdentical:
    def test_all_eight_variants_share_one_geometry(self) -> None:
        skeletons = {}
        for v in _VARIANTS:
            svg = compose(
                ComposeSpec(type="receipt", genome_id="primer", variant=v, telemetry_data=SPECIMEN_PAYLOAD)
            ).svg
            skeletons[v] = _geometry_skeleton(svg)
        ref = skeletons["porcelain"]
        for v in _VARIANTS:
            assert skeletons[v] == ref, f"variant {v} geometry diverged from porcelain"

    def test_variants_differ_chromatically(self) -> None:
        """Geometry-identical must NOT mean byte-identical — colours must differ."""
        noir = compose(
            ComposeSpec(type="receipt", genome_id="primer", variant="noir", telemetry_data=SPECIMEN_PAYLOAD)
        ).svg
        porc = compose(
            ComposeSpec(type="receipt", genome_id="primer", variant="porcelain", telemetry_data=SPECIMEN_PAYLOAD)
        ).svg
        # noir ramp tier vs porcelain ramp tier — distinct signal hues.
        assert "#FAFAFA" in noir
        assert "#1D4ED8" in porc

    def test_light_variant_carries_lift_filter_dark_omits(self) -> None:
        porc = compose(
            ComposeSpec(type="receipt", genome_id="primer", variant="porcelain", telemetry_data=SPECIMEN_PAYLOAD)
        ).svg
        noir = compose(
            ComposeSpec(type="receipt", genome_id="primer", variant="noir", telemetry_data=SPECIMEN_PAYLOAD)
        ).svg
        assert "filter=" in porc and "feDropShadow" in porc
        assert "feDropShadow" not in noir  # a dark card does not cast on a dark host


# --------------------------------------------------------------------------- #
# Payload / envelope conformance                                              #
# --------------------------------------------------------------------------- #


class TestPayloadEnvelope:
    def test_embedded_payload_is_compact_and_data_only(self) -> None:
        svg = compose(
            ComposeSpec(type="receipt", genome_id="primer", variant="noir", telemetry_data=SPECIMEN_PAYLOAD)
        ).svg
        m = re.search(r'schema="receipt/1"[^>]*><!\[CDATA\[(.*?)\]\]>', svg, re.S)
        assert m, "receipt/1 payload CDATA not found"
        body = m.group(1)
        assert "\n" not in body  # single-line
        assert "$" not in body  # no formatted money
        assert "spend" not in body  # no label strings

    def test_envelope_id_hashes_the_emitted_payload(self) -> None:
        svg = compose(
            ComposeSpec(type="receipt", genome_id="primer", variant="noir", telemetry_data=SPECIMEN_PAYLOAD)
        ).svg
        m = re.search(r'schema="receipt/1"[^>]*><!\[CDATA\[(.*?)\]\]>', svg, re.S)
        assert m
        digest = hashlib.sha256(m.group(1).encode("utf-8")).hexdigest()
        assert f"sha256:{digest}" in svg

    def test_renders_stable_uid_for_same_inputs(self) -> None:
        """The content-hashed uid is identical across renders (the cache contract).

        Full byte-equality additionally requires freezing the clock — the
        envelope's prov.ts + hw:created read wall-clock time — so we pin the
        deterministic surface: the content-derived uid/contract id.
        """
        a = compose(
            ComposeSpec(type="receipt", genome_id="primer", variant="noir", telemetry_data=SPECIMEN_PAYLOAD)
        ).svg
        b = compose(
            ComposeSpec(type="receipt", genome_id="primer", variant="noir", telemetry_data=SPECIMEN_PAYLOAD)
        ).svg
        uid_a = re.search(r'data-hw-contract="(receipt-[0-9a-f]+)"', a)
        uid_b = re.search(r'data-hw-contract="(receipt-[0-9a-f]+)"', b)
        assert uid_a and uid_b
        assert uid_a.group(1) == uid_b.group(1)


def test_specimen_payload_renders_all_zones() -> None:
    """The canonical specimen payload renders every receipt zone end-to-end."""
    svg = compose(ComposeSpec(type="receipt", genome_id="primer", variant="noir", telemetry_data=SPECIMEN_PAYLOAD)).svg
    for needle in ("$175.01", "MODEL MIX · 3 MODELS", "opus-4.7", "562", "CALLS", "196K PEAK", "+6 others"):
        assert needle in svg, f"missing {needle!r}"
    # Cost-by-model legend uses whole-dollar money.
    assert "$128" in svg and "$8" in svg
