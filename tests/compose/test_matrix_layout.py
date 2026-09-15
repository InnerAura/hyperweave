"""Matrix layout solver invariants — geometry the templates rely on."""

from __future__ import annotations

import re

import pytest

from hyperweave.compose.matrix.infer import infer_matrix
from hyperweave.compose.matrix.layout import compute_matrix_layout
from hyperweave.compose.matrix.records import MatrixLayout  # noqa: TC001 (runtime return type)
from hyperweave.config.loader import load_glyphs, load_matrix_config
from hyperweave.core.matrix import CellKind, MatrixCapacityError, MatrixCell, MatrixInputError, MatrixSpec
from hyperweave.core.paradigm import ParadigmMatrixConfig
from tests.compose.test_matrix_input import all_fixture_specs, load_fixture

CFG = ParadigmMatrixConfig()

CELL_KIND_SLUGS = {k.value for k in CellKind if k is not CellKind.AUTO}


def solve(spec: MatrixSpec) -> MatrixLayout:
    return compute_matrix_layout(
        infer_matrix(spec), matrix=CFG, config=load_matrix_config(), glyph_registry=load_glyphs()
    )


def simple(n_rows: int, n_cols: int = 1) -> MatrixSpec:
    return MatrixSpec(
        title="T",
        columns=[{"id": "l", "label": "L", "role": "label"}]
        + [{"id": f"c{j}", "label": f"C{j}"} for j in range(n_cols)],
        rows=[{"label": f"row {i}", "cells": [{"value": i + j} for j in range(n_cols)]} for i in range(n_rows)],
    )


def _break_chain(spec: MatrixSpec) -> MatrixSpec:
    """Flip one row so the inclusion sets stop nesting (the first tier
    keeps a row the last tier lacks) — the tier-dot fallback shape."""
    rows = list(spec.rows)
    cells = list(rows[0].cells)
    cells[0] = MatrixCell(state="on")
    cells[-1] = MatrixCell(state="off")
    rows[0] = rows[0].model_copy(update={"cells": cells})
    return spec.model_copy(update={"rows": rows})


class TestColumnSolver:
    @pytest.mark.parametrize("name", ["check", "tiers", "readcost", "plans", "benchmark", "connectors"])
    def test_widths_sum_to_content_width(self, name: str) -> None:
        layout = solve(all_fixture_specs()[name])
        avail = layout.width - 2 * CFG.margin_x
        label_w = layout.col_x[0] - CFG.margin_x
        assert abs(label_w + sum(layout.col_w) - avail) < 0.01, name
        assert CFG.min_width <= layout.width <= CFG.width, name

    def test_columns_are_contiguous(self) -> None:
        layout = solve(load_fixture("check"))
        for j in range(1, len(layout.col_x)):
            assert layout.col_x[j] == pytest.approx(layout.col_x[j - 1] + layout.col_w[j - 1])

    def test_explicit_width_wins(self) -> None:
        spec = MatrixSpec(
            title="T",
            columns=[{"id": "a", "label": "A", "width": 137.0}, {"id": "b", "label": "B"}],
            rows=[{"label": "r", "cells": [{"value": 1}, {"value": 2}]}],
        )
        layout = solve(spec)
        assert layout.col_w[0] == pytest.approx(137.0)

    def test_flexible_kinds_absorb_remainder(self) -> None:
        layout = solve(all_fixture_specs()["connectors"])
        # chip column dwarfs the fixed pill columns
        assert layout.col_w[0] > 3 * max(layout.col_w[1], layout.col_w[2])

    def test_mark_columns_demand_breathing_room(self) -> None:
        """Check/dot columns floor at their cell_geometry min_col: a 9px
        mark in a 64px slot reads cramped, so mark columns widen the table
        through their kind floor, not through a global width floor."""
        geometry = load_matrix_config()["cell_geometry"]
        spec = MatrixSpec(
            title="T",
            columns=[{"id": "l", "label": "L", "role": "label"}]
            + [{"id": f"c{j}", "label": "X", "kind": "check"} for j in range(3)],
            rows=[{"label": "r", "cells": [{"state": "full"}] * 3}],
        )
        layout = solve(spec)
        assert all(w >= geometry["check"]["min_col"] for w in layout.col_w)
        assert geometry["check"]["min_col"] >= 100
        assert geometry["dot"]["min_col"] >= 100

    def test_eight_plain_numeric_columns_stay_feasible(self) -> None:
        """Regression: the heat-tile floor (110) must not apply to plain
        numeric columns — eight of them once drove the deficit path to a
        NEGATIVE width, marching headers backward over the label zone."""
        layout = solve(simple(4, n_cols=8))
        assert all(w > 40 for w in layout.col_w), layout.col_w
        for j in range(1, len(layout.col_x)):
            assert layout.col_x[j] > layout.col_x[j - 1]

    def test_infeasible_floors_scale_not_negate(self) -> None:
        """When kind floors exceed the content width, widths scale to fit
        proportionally — every column stays strictly positive."""
        spec = MatrixSpec(
            title="T",
            columns=[{"id": "l", "label": "L", "role": "label"}]
            + [{"id": f"h{j}", "label": f"H{j}", "kind": "numeric", "polarity": "higher"} for j in range(8)],
            rows=[{"label": "r", "cells": [{"value": j + 1} for j in range(8)]}],
        )
        layout = solve(spec)
        assert all(w > 0 for w in layout.col_w), layout.col_w
        avail = layout.width - 2 * CFG.margin_x
        label_w = layout.col_x[0] - CFG.margin_x
        assert abs(label_w + sum(layout.col_w) - avail) < 0.01


class TestAdaptiveWidth:
    """The frame fits its content: cfg.width is the ceiling, not a constant."""

    def test_tiny_matrix_shrinks_to_floor(self) -> None:
        layout = solve(
            MatrixSpec(
                title="",
                columns=[{"id": "v", "label": "V", "kind": "check"}],
                rows=[{"label": "r", "cells": [{"state": "full"}]}],
            )
        )
        assert layout.width == CFG.min_width

    def test_bar_matrix_pins_the_ceiling(self) -> None:
        layout = solve(load_fixture("readcost"))
        assert layout.width == CFG.width

    def test_huge_chip_content_clamps_to_ceiling(self) -> None:
        layout = solve(all_fixture_specs()["connectors"])
        assert layout.width == CFG.width

    def test_masthead_text_floors_the_width(self) -> None:
        narrow = MatrixSpec(
            title="",
            columns=[{"id": "v", "label": "V", "kind": "check"}],
            rows=[{"label": "r", "cells": [{"state": "full"}]}],
        )
        wide_title = narrow.model_copy(update={"title": "An exceptionally long masthead title that must not clip"})
        assert solve(wide_title).width > solve(narrow).width

    def test_benchmark_sits_between_floor_and_ceiling(self) -> None:
        layout = solve(load_fixture("benchmark"))
        assert CFG.min_width < layout.width <= CFG.width


class TestRows:
    def test_uniform_pitch(self) -> None:
        layout = solve(load_fixture("check"))
        assert set(layout.row_h) == {CFG.row_pitch}
        deltas = {round(layout.row_y[i + 1] - layout.row_y[i], 3) for i in range(len(layout.row_y) - 1)}
        assert deltas == {CFG.row_pitch}

    def test_content_rows_vary(self) -> None:
        layout = solve(all_fixture_specs()["connectors"])
        assert max(layout.row_h) > min(layout.row_h)

    def test_soft_cap_shrinks_pitch(self) -> None:
        assert solve(simple(17)).row_h[0] == CFG.row_pitch_compact
        assert solve(simple(16)).row_h[0] == CFG.row_pitch

    def test_hard_cap_raises(self) -> None:
        with pytest.raises(MatrixCapacityError, match="paginate"):
            solve(simple(31))
        with pytest.raises(MatrixCapacityError, match="paginate"):
            solve(simple(2, n_cols=13))

    def test_hard_cap_boundary_renders(self) -> None:
        assert solve(simple(30)).height > 0


class TestCells:
    def test_seam_contract(self) -> None:
        """Every placement carries a concrete kind and its kind-required fields."""
        for name, spec in all_fixture_specs().items():
            layout = solve(spec)
            for cell in layout.cells:
                assert cell.kind in CELL_KIND_SLUGS, (name, cell.kind)
                if cell.kind == "check":
                    assert cell.mark_d.startswith("M") and cell.tone
                elif cell.kind == "dot":
                    assert cell.dot_r > 0
                elif cell.kind == "bar" and cell.track is not None:
                    assert cell.bar_fill is not None and cell.bar_fill.w <= cell.track.w + 0.01
                elif cell.kind == "glyph":
                    assert cell.glyph_paths and cell.glyph_transform

    def test_chip_packing_stays_in_column(self) -> None:
        layout = solve(all_fixture_specs()["connectors"])
        for cell in layout.cells:
            if cell.kind != "chip":
                continue
            for chip in cell.chips:
                assert chip.rect.x >= cell.box.x - 0.01
                assert chip.rect.x + chip.rect.w <= cell.box.x + cell.box.w + 0.01

    def test_uniform_never_strangles_chips(self) -> None:
        """Chip columns always grow rows to fit — a declared UNIFORM cannot
        truncate moderate chip lists to one line (the connectors behavior is
        the standard rendering for every chip column)."""
        spec = MatrixSpec(
            title="T",
            row_height="uniform",
            columns=[
                {"id": "l", "label": "L", "role": "label"},
                {"id": "m", "label": "M", "kind": "chip"},
                {"id": "a", "label": "A", "kind": "pill"},
                {"id": "b", "label": "B", "kind": "pill"},
            ],
            rows=[
                {
                    "label": "many",
                    "cells": [{"chips": [f"metric_{i}" for i in range(19)]}, {"state": "on"}, {"state": "on"}],
                }
            ],
        )
        layout = solve(spec)
        chip_cell = next(c for c in layout.cells if c.kind == "chip")
        assert not any(ch.overflow for ch in chip_cell.chips), "19 chips must wrap, not overflow"
        assert len({round(ch.rect.y, 2) for ch in chip_cell.chips}) > 1
        assert layout.row_h[0] > CFG.row_pitch  # the row grew

    def test_chip_overflow_plus_n_past_row_cap(self) -> None:
        """+N is the cap for EXTREME lists only: when even max_chip_rows
        wrapped lines cannot hold the chips."""
        spec = MatrixSpec(
            title="T",
            columns=[
                {"id": "l", "label": "L", "role": "label"},
                {"id": "m", "label": "M", "kind": "chip"},
                {"id": "a", "label": "A", "kind": "pill"},
                {"id": "b", "label": "B", "kind": "pill"},
            ],
            rows=[
                {
                    "label": "extreme",
                    "cells": [
                        {"chips": [f"dependency_{i}" for i in range(60)]},
                        {"state": "on"},
                        {"state": "on"},
                    ],
                }
            ],
        )
        layout = solve(spec)
        chip_cell = next(c for c in layout.cells if c.kind == "chip")
        overflow = [ch for ch in chip_cell.chips if ch.overflow]
        shown = len(chip_cell.chips) - len(overflow)
        assert len(overflow) == 1
        assert overflow[0].text == f"+{60 - shown}"
        # wrapped to the full row cap before capping
        assert len({round(ch.rect.y, 2) for ch in chip_cell.chips}) == 4

    def test_text_wraps_to_its_full_demand(self) -> None:
        """Text cells wrap by default and the row grows to hold every run —
        there is no line cap and no ellipsis. Short siblings stay single-run."""
        from hyperweave.compose.geometry.text import required_lines

        long = "a commit subject that runs well past a narrow column and keeps going with more words " * 2
        spec = MatrixSpec(
            title="T",
            columns=[{"id": "l", "label": "L", "role": "label"}]
            + [{"id": k, "label": k.upper(), "kind": "text", "width": 120} for k in ("a", "b", "c")],
            rows=[{"label": "r", "cells": [{"value": long}, {"value": "short"}, {"value": "also short"}]}],
        )
        layout = solve(spec)
        wrapped = next(c for c in layout.cells if c.row == 0 and c.col == 0)
        assert len(wrapped.text_lines) == required_lines(
            long.strip(), CFG.cell_voice, wrapped.box.w - 2 * CFG.cell_pad_x
        )
        assert not any(line.text.endswith("…") for line in wrapped.text_lines)
        short = next(c for c in layout.cells if c.row == 0 and c.col == 1)
        assert short.text_lines == () and short.text == "short"
        assert layout.row_h[0] > CFG.row_pitch

    def test_sectioned_labels_take_the_quiet_voice(self) -> None:
        """Sectioned rows are sub-fields: quiet voice, indented under the
        band. Flat rows keep the primary row-title voice."""
        tiers = solve(load_fixture("tiers"))
        tier_label_cls = {c.cls for c in tiers.cells if c.col == -1 and c.kind == "text"}
        assert tier_label_cls == {"rowlabelsub"}
        flat = solve(load_fixture("check"))
        assert {c.cls for c in flat.cells if c.col == -1 and c.kind == "text"} == {"rowlabel"}

    def test_section_bands_and_stripes_run_card_wide(self) -> None:
        """The washes are the one card-wide treatment (specimen: x=8 to
        width-8); every hairline rule stays within the content margins."""
        tiers = solve(load_fixture("tiers"))
        assert {b.band.x for b in tiers.section_bands} == {8.0}
        assert {b.band.w for b in tiers.section_bands} == {tiers.width - 16.0}
        rule = tiers.lines["colheader_rule"]
        assert rule.x1 == CFG.margin_x and rule.x2 == tiers.width - CFG.margin_x
        assert tiers.footer.seam.x1 == CFG.margin_x

    def test_scan_rect_centered(self) -> None:
        """The scan rect centers on the rail; its keyframes sweep ±46% of
        the card width (out past both edges and back)."""
        layout = solve(load_fixture("check"))
        scan = layout.rects["scan"]
        assert scan.x == (layout.width - CFG.scan_w) / 2

    def test_long_label_widens_the_frame_instead_of_truncating(self) -> None:
        """A row label is content: the frame grows to hold it (up to the
        ceiling) and the label column takes its need, so no ellipsis appears
        while lawful slack exists."""
        from hyperweave.compose.geometry.text import measure_voice

        long_label = "An extremely long capability label that cannot possibly fit the label column"
        spec = MatrixSpec(
            title="T",
            columns=[{"id": "v", "label": "V", "kind": "check"}],
            rows=[{"label": long_label, "cells": [{"state": "full"}]}],
        )
        layout = solve(spec)
        label_cell = next(c for c in layout.cells if c.kind == "text" and c.row == 0)
        assert label_cell.text == long_label
        label_w = layout.col_x[0] - CFG.margin_x
        assert measure_voice(long_label, CFG.row_label_voice) + 2 * CFG.cell_pad_x <= label_w + 0.01
        assert layout.diagnostics == ()

    def test_label_wraps_at_the_ceiling_and_says_so(self) -> None:
        """Past the frame ceiling the label column gives ground down to its
        widest word: labels wrap, rows grow, nothing ellipsizes, and the
        solve reports the wrap."""
        label = " ".join(["capability"] * 14)
        spec = MatrixSpec(
            title="T",
            columns=[{"id": "l", "label": "L", "role": "label"}]
            + [{"id": f"c{j}", "label": f"C{j}", "kind": "check"} for j in range(5)],
            rows=[{"label": label, "cells": [{"state": "full"}] * 5}],
        )
        layout = solve(spec)
        assert layout.width == CFG.width
        label_cell = next(c for c in layout.cells if c.kind == "text" and c.row == 0)
        assert len(label_cell.text_lines) > 1
        assert " ".join(t.text for t in label_cell.text_lines) == label
        assert layout.row_h[0] > CFG.row_pitch
        assert "label-column" in [d.rule for d in layout.diagnostics]

    def test_heat_tile_clamps_to_compressed_column(self) -> None:
        """Regression: eight heat columns compress below the 96px tile —
        tiles must clamp to their column instead of overlapping neighbors."""
        spec = MatrixSpec(
            title="Wall",
            columns=[{"id": "l", "label": "L", "role": "label"}]
            + [{"id": f"h{j}", "label": f"H{j}", "kind": "numeric", "polarity": "higher"} for j in range(8)],
            rows=[{"label": "r", "cells": [{"value": 40 + j} for j in range(8)]}],
        )
        layout = solve(spec)
        tiles = [c for c in layout.cells if c.kind == "numeric" and c.heat_tile]
        assert len(tiles) == 8
        for cell in tiles:
            tile = cell.heat_tile
            assert tile is not None
            assert tile.w >= 0.0
            assert tile.x >= layout.col_x[cell.col] - 0.01
            assert tile.x + tile.w <= layout.col_x[cell.col] + layout.col_w[cell.col] + 0.01
            for rect in (cell.heat_track, cell.heat_underline):
                assert rect is None or rect.w >= 0.0

    def test_heat_identical_values_share_neutral_mid(self) -> None:
        spec = MatrixSpec(
            title="T",
            columns=[{"id": "n", "label": "Score", "kind": "numeric", "polarity": "higher"}],
            rows=[{"label": f"r{i}", "cells": [{"value": 5}]} for i in range(3)],
        )
        layout = solve(spec)
        tones = {c.tone for c in layout.cells if c.kind == "numeric"}
        assert len(tones) == 1

    def test_bar_zero_value_keeps_minimum_ink(self) -> None:
        spec = MatrixSpec(
            title="T",
            columns=[{"id": "n", "label": "Tokens", "kind": "bar"}],
            rows=[{"label": "zero", "cells": [{"value": 0}]}, {"label": "big", "cells": [{"value": 100}]}],
        )
        layout = solve(spec)
        bars = [c for c in layout.cells if c.kind == "bar"]
        zero = next(c for c in bars if c.text == "0")
        assert zero.bar_fill is not None and zero.bar_fill.w >= 14.0

    def test_unknown_glyph_id_raises(self) -> None:
        spec = MatrixSpec(
            title="T",
            columns=[{"id": "g", "label": "G", "kind": "glyph"}],
            rows=[{"label": "r", "cells": [{"glyph": "not-a-real-glyph"}]}],
        )
        with pytest.raises(MatrixInputError, match="registry ids only"):
            solve(spec)


class TestOptionalBlocks:
    def test_hero_band_only_when_asked(self) -> None:
        assert solve(load_fixture("check")).hero_band is not None
        assert solve(load_fixture("benchmark")).hero_band is None

    def test_sections_and_tier_spans(self) -> None:
        """Chained tiers project as reach spans: one bar per column from
        the table top to the last included row's center, terminal dot at
        the reach — no per-cell dots, no extent bars."""
        layout = solve(load_fixture("tiers"))
        assert len(layout.section_bands) == 4
        assert layout.extent_bars == ()
        assert len(layout.tier_spans) == 3
        assert all(c.kind != "dot" or c.row == -1 for c in layout.cells)  # no grid dots (legend mark only)
        tops = {span.bar.y for span in layout.tier_spans}
        assert len(tops) == 1  # every span starts at the table's top
        for span in layout.tier_spans:
            assert span.dot_cy == span.bar.y + span.bar.h  # dot closes the bar
        reaches = [span.dot_cy for span in layout.tier_spans]
        assert reaches == sorted(reaches)  # supersets reach further
        assert reaches[-1] == layout.row_y[-1] + layout.row_h[-1] / 2

    def test_broken_chain_keeps_the_dot_grid(self) -> None:
        """A non-nested dot matrix falls back to tier-dot: per-cell dots
        and extent bars, no spans."""
        layout = solve(_break_chain(load_fixture("tiers")))
        assert layout.tier_spans == ()
        assert len(layout.extent_bars) == 3
        assert any(c.kind == "dot" and c.row >= 0 for c in layout.cells)

    def test_axis_only_for_bar(self) -> None:
        layout = solve(load_fixture("readcost"))
        assert layout.axis is not None
        assert [t.text for t in layout.axis.tick_labels] == ["0", "1k", "2k", "3k"]
        assert solve(load_fixture("check")).axis is None

    @pytest.mark.parametrize(
        ("axis_max", "expected"),
        [
            (1.0, ["0", "0.25", "0.5", "0.75", "1"]),
            (3400, ["0", "1k", "2k", "3k"]),
            (2_500_000, ["0", "500k", "1M", "1.5M", "2M", "2.5M"]),
        ],
    )
    def test_axis_ticks_share_the_compact_formatter(self, axis_max: float, expected: list[str]) -> None:
        """Ticks come from the one compact-number formatter in its lowercase-k
        register: fractions keep their digits, millions read ``M``, never ``1000k``."""
        spec = MatrixSpec(
            title="T",
            axis_max=axis_max,
            columns=[{"id": "l", "label": "L", "role": "label"}, {"id": "b", "label": "B", "kind": "bar"}],
            rows=[{"label": "r", "cells": [{"value": axis_max / 2}]}],
        )
        layout = solve(spec)
        assert layout.axis is not None
        assert [t.text for t in layout.axis.tick_labels] == expected

    def test_headline_chip(self) -> None:
        layout = solve(load_fixture("readcost"))
        assert layout.header.headline_chip is not None
        assert layout.header.headline_value is not None
        assert layout.header.headline_value.text == "16x"

    def test_legend_for_check_and_dot(self) -> None:
        assert len(solve(load_fixture("check")).header.key_marks) == 3
        # chained tiers carry the one-entry tier-reach key (mini span + dot)
        tiers = solve(load_fixture("tiers"))
        assert [t.text for t in tiers.header.key_texts] == ["tier reach"]
        assert len(tiers.header.key_marks) == 1
        assert len(tiers.header.key_rects) == 1
        # a non-nested dot grid keeps the included/omitted pair
        assert len(solve(_break_chain(load_fixture("tiers"))).header.key_marks) == 2
        # headline occupies the legend slot
        assert len(solve(load_fixture("readcost")).header.key_marks) == 0

    def test_long_title_clears_the_key_column(self) -> None:
        """A title that would overhang the legend's column from the line
        above shrinks just enough to clear it (with a legibility floor);
        short titles keep the full voice."""
        from hyperweave.compose.geometry.text import measure_voice

        short = solve(load_fixture("check"))
        assert short.title_size == CFG.title_voice.size
        long_spec = load_fixture("check").model_copy(update={"title": "One artifact. Many readers."})
        layout = solve(long_spec)
        assert layout.title_size < CFG.title_voice.size
        assert layout.header.title is not None
        voice = CFG.title_voice.model_copy(update={"size": layout.title_size})
        title_right = layout.header.title.x + measure_voice(long_spec.title.upper(), voice)
        legend_left = min(m.box.x for m in layout.header.key_marks)
        assert title_right <= legend_left + 1.0

    def test_legend_shares_descriptor_line_when_it_fits(self) -> None:
        """The legend rides the subtitle's line whenever the pair can share
        at the ceiling — identity left, key right, one masthead band (the
        g3 specimen)."""
        layout = solve(load_fixture("check"))
        assert layout.header.rule is not None and layout.header.subtitle is not None
        assert {t.y for t in layout.header.key_texts} == {layout.header.subtitle.y}
        assert layout.header.rule.y1 == CFG.masthead_h + 0.5

    def test_legend_drops_to_own_line_only_past_the_ceiling(self) -> None:
        """Only a subtitle + legend pair that cannot share even at the
        ceiling moves the key one line pitch down (the masthead grows by
        exactly that line)."""
        long_sub = (
            "a deliberately verbose descriptor that keeps going and going until "
            "the shared line cannot exist at the nine-hundred pixel ceiling at all"
        )
        layout = solve(load_fixture("check").model_copy(update={"subtitle": long_sub}))
        assert layout.header.subtitle is not None
        assert {t.y for t in layout.header.key_texts} == {layout.header.subtitle.y + CFG.desc_line_h}
        assert layout.header.rule is not None
        assert layout.header.rule.y1 == CFG.masthead_h + CFG.desc_line_h + 0.5

    def test_wide_solve_keeps_legend_inline(self) -> None:
        """A wide solve keeps the legend on the shared descriptor line —
        the specimen gestalt."""
        wide = load_fixture("check").model_copy(
            update={"title": "An exceptionally long masthead title that forces a wide solve"}
        )
        layout = solve(wide)
        assert {t.y for t in layout.header.key_texts} == {54.0 + CFG.desc_line_h}
        assert layout.header.rule is not None
        assert layout.header.rule.y1 == CFG.masthead_h + 0.5

    def test_no_subtitle_legend_inherits_descriptor_slot(self) -> None:
        """No subtitle: the legend takes the released descriptor line — the
        masthead keeps its natural height with no stranded band, regardless
        of title width."""
        for title in ("Formats", "Format comparison across every surface"):
            layout = solve(load_fixture("check").model_copy(update={"subtitle": "", "title": title}))
            assert {t.y for t in layout.header.key_texts} == {54.0 + CFG.desc_line_h}, title
            assert layout.header.rule is not None
            assert layout.header.rule.y1 == CFG.masthead_h + 0.5

    def test_hero_lane_runs_through_score_band(self) -> None:
        """With a summary row the hero lane extends through the score band
        — the winner's verdict sits inside its highlighted region. Without
        one it stops at the last row (the g3 specimen)."""
        layout = solve(load_fixture("check"))
        assert layout.hero_band is not None and layout.summary is not None
        assert layout.hero_band.y + layout.hero_band.h > layout.summary.rule.y1
        bare = load_fixture("check").model_copy(update={"summary_row": None, "summary_label": ""})
        ns = solve(bare)
        assert ns.hero_band is not None
        assert ns.hero_band.y + ns.hero_band.h == ns.row_y[-1] + ns.row_h[-1]

    def test_no_subtitle_no_legend_collapses_descriptor_line(self) -> None:
        """No subtitle and no legend (pill columns carry no key): the
        descriptor line releases its geometry — the rail rides up."""
        layout = solve(load_fixture("plans").model_copy(update={"subtitle": ""}))
        assert layout.header.key_texts == ()
        assert layout.header.rule is not None
        assert layout.header.rule.y1 == CFG.masthead_h - CFG.desc_line_h + 0.5

    def test_masthead_collapses_without_title(self) -> None:
        """Empty title/subtitle/headline → the masthead zone releases its
        space: no rail, no scan, no legend, table starts near the top."""
        bare = MatrixSpec(
            title="",
            columns=[{"id": "v", "label": "V", "kind": "check"}],
            rows=[{"label": "r", "cells": [{"state": "full"}]}],
        )
        titled = bare.model_copy(update={"title": "Titled"})
        collapsed = solve(bare)
        full = solve(titled)
        assert collapsed.header.title is None
        assert collapsed.header.rule is None
        assert collapsed.header.scan is None
        assert collapsed.header.key_marks == ()
        assert collapsed.row_y[0] < full.row_y[0]
        assert collapsed.height < full.height
        assert full.header.title is not None and full.header.scan is not None

    def test_summary_content_widens_columns(self) -> None:
        """Regression: summary cells occupy the same columns as the data —
        'agent corpora' under a 9px dot column must widen the column, never
        cram. Every summary run fits inside its solved column."""
        from hyperweave.compose.geometry.text import measure_voice

        layout = solve(load_fixture("tiers"))
        summary_cells = [c for c in layout.cells if c.row == 9 and c.text]
        assert len(summary_cells) == 3
        voices = {
            "sumvalhero": CFG.summary_hero_voice,
            "sumval": CFG.summary_value_voice,
            "sumtext": CFG.summary_text_voice,
        }
        for cell in summary_cells:
            max_w = layout.col_w[cell.col] - 2 * CFG.cell_pad_x + 0.01
            assert measure_voice(cell.text, voices[cell.cls]) <= max_w, cell.text

    def test_summary_band_gestalt(self) -> None:
        """Score band reads bigger than the body: hero value+qualifier in
        the genome accent, larger hero voice."""
        layout = solve(load_fixture("check"))
        summary_cells = [c for c in layout.cells if c.row == 7]
        hero = next(c for c in summary_cells if c.cls == "sumvalhero")
        others = [c for c in summary_cells if c.cls == "sumval"]
        assert len(others) == 3
        assert hero.text_fill == "var(--dna-signal)"
        assert hero.sub_fill == "var(--dna-signal)"
        assert all(c.text_fill == "" for c in others)
        assert all(c.sub_cls == "sumqual" for c in summary_cells)

    def test_minimum_1x1(self) -> None:
        layout = solve(
            MatrixSpec(
                title="One", columns=[{"id": "v", "label": "V"}], rows=[{"label": "only", "cells": [{"value": 42}]}]
            )
        )
        assert layout.height > 0 and len(layout.cells) >= 2

    def test_auto_kind_rejected_without_inference(self) -> None:
        raw = MatrixSpec(title="T", columns=[{"id": "v", "label": "V"}], rows=[{"label": "r", "cells": [{"value": 1}]}])
        with pytest.raises(MatrixInputError, match="kind=auto"):
            compute_matrix_layout(raw, matrix=CFG, config=load_matrix_config(), glyph_registry=load_glyphs())


class TestRelationalWidths:
    """Every width is a relation over measured ink; no column crushes its
    header, no title leaves its line, no rect goes negative."""

    @staticmethod
    def _header_overruns(layout: MatrixLayout) -> list[float]:
        """Widest rendered header run plus both cell pads minus the column
        width, per data column; wrapped headers render ``lines``; the label
        header leads ``colheaders`` and is skipped."""
        from hyperweave.compose.geometry.text import measure_voice

        headers = list(layout.colheaders)[-len(layout.col_w) :]
        overruns = []
        for col, w in zip(headers, layout.col_w, strict=True):
            runs = [t.text for t in col.lines] if col.lines else [col.label.text]
            ink = max(measure_voice(run, CFG.colhead_voice) for run in runs)
            if col.sublabel is not None:
                ink = max(ink, measure_voice(col.sublabel.text, CFG.colhead_sub_voice))
            overruns.append(ink + 2 * CFG.cell_pad_x - w)
        return overruns

    @pytest.mark.parametrize("name", ["check", "tiers", "readcost", "plans", "benchmark", "connectors"])
    def test_every_column_holds_its_header(self, name: str) -> None:
        layout = solve(all_fixture_specs()[name])
        assert max(self._header_overruns(layout), default=0.0) <= 0.01, name

    def test_flexible_columns_hold_long_headers_under_deficit(self) -> None:
        """Chip and check columns headed by long labels keep their header ink
        when the naturals exceed the frame and the solver shrinks — the
        crushed-headers defect (`EXECUTIONPARADIGMS GOODMULTI-TURN SAFE`)."""
        spec = MatrixSpec(
            title="Execution paradigms",
            columns=[
                {"id": "feat", "label": "FEATURE", "role": "label"},
                {"id": "ast", "label": "EMBEDDED AST SEED", "kind": "chip"},
                {"id": "turn", "label": "TURN 1 LOOKS GOOD", "kind": "check"},
                {"id": "safe", "label": "MULTI-TURN SAFE", "kind": "check"},
            ],
            rows=[
                {
                    "label": "Deterministic AST pass with a long qualifying phrase",
                    "cells": [
                        {"chips": ["Deterministic", "Solver", "JSON Schema", "Replay"]},
                        {"state": "full"},
                        {"state": "full"},
                    ],
                },
                {
                    "label": "Stateful tool execution",
                    "cells": [{"chips": ["Sandbox"]}, {"state": "partial"}, {"state": "full"}],
                },
            ],
        )
        layout = solve(spec)
        assert max(self._header_overruns(layout)) <= 0.01
        avail = layout.width - 2 * CFG.margin_x
        assert abs((layout.col_x[0] - CFG.margin_x) + sum(layout.col_w) - avail) < 0.01

    def test_geometry_compresses_before_text_and_the_solve_says_so(self) -> None:
        """Eight heat tiles cannot all be 110 wide at the ceiling: the tiles
        shrink toward their header ink and the compression is reported."""
        spec = MatrixSpec(
            title="Wall",
            columns=[{"id": "l", "label": "L", "role": "label"}]
            + [{"id": f"h{j}", "label": f"H{j}", "kind": "numeric", "polarity": "higher"} for j in range(8)],
            rows=[{"label": "r", "cells": [{"value": 40 + j} for j in range(8)]}],
        )
        layout = solve(spec)
        assert max(self._header_overruns(layout)) <= 0.01
        assert "column-compressed" in [d.rule for d in layout.diagnostics]

    def test_headers_that_cannot_fit_the_frame_refuse_by_name(self) -> None:
        """A header wraps at word boundaries; only a single word wider than
        the frame can hold is a true capacity failure, and it refuses by name."""
        spec = MatrixSpec(
            title="T",
            columns=[{"id": "l", "label": "L", "role": "label"}]
            + [{"id": f"c{j}", "label": f"UNBREAKABLEHEADERWORDNUMBER{j}", "kind": "check"} for j in range(6)],
            rows=[{"label": "r", "cells": [{"state": "full"}] * 6}],
        )
        with pytest.raises(MatrixCapacityError, match="narrow the widest columns"):
            solve(spec)

    def test_headline_chip_that_cannot_fit_refuses_by_name(self) -> None:
        """A chip wider than the masthead can hold never escapes the frame or
        overlaps the title: the solve refuses with the measured need, the
        room it had, and the value and label widths that make up the need."""
        spec = MatrixSpec(
            title="Realtime autonomous agent fleet telemetry",
            headline={"value": "99.98%", "label": "System availability SLA " * 6},
            columns=[{"id": "l", "label": "L", "role": "label"}, {"id": "v", "label": "V", "kind": "text"}],
            rows=[{"label": "r", "cells": [{"value": "v"}]}],
        )
        with pytest.raises(MatrixCapacityError) as excinfo:
            solve(spec)
        message = str(excinfo.value)
        assert re.search(r"headline chip needs \d+px \(value \d+px, label \d+px\)", message), message
        assert re.search(r"\d+px is available beside the title", message), message

    def test_headline_chip_keeps_the_title_at_least_an_ellipsis(self) -> None:
        """Just inside the refusal the title still renders at its floor size,
        ellipsized and reported, clear of the chip by the 24px gap."""
        from hyperweave.compose.geometry.text import measure_voice

        spec = MatrixSpec(
            title="Realtime autonomous agent fleet telemetry",
            headline={"value": "99.98%", "label": "System availability service level agreement for the fleet"},
            columns=[{"id": "l", "label": "L", "role": "label"}, {"id": "v", "label": "V", "kind": "text"}],
            rows=[{"label": "r", "cells": [{"value": "v"}]}],
        )
        layout = solve(spec)
        assert layout.header.title is not None and layout.header.headline_chip is not None
        assert layout.header.headline_chip.x >= CFG.margin_x - 0.01
        voice = CFG.title_voice.model_copy(update={"size": layout.title_size})
        title_right = layout.header.title.x + measure_voice(layout.header.title.text, voice)
        assert title_right <= layout.header.headline_chip.x - 24.0 + 0.01
        assert layout.header.title.text.endswith("…")
        assert "masthead-title" in [d.rule for d in layout.diagnostics]

    def test_declared_widths_grow_to_their_content_floor_and_say_so(self) -> None:
        """A declared width narrower than the column's content floor is raised
        to the floor and the solve reports it; no chip is ever ellipsized to
        honor a number."""
        spec = MatrixSpec(
            title="T",
            columns=[{"id": "l", "label": "L", "role": "label"}]
            + [{"id": f"c{j}", "label": f"C{j}", "kind": "chip", "width": 70} for j in range(3)],
            rows=[{"label": "r", "cells": [{"chips": ["none (opaque html)", "ok"]}] * 3}],
        )
        layout = solve(spec)
        chips = [c for c in layout.cells if c.kind == "chip"]
        assert len(chips) == 3
        for cell in chips:
            assert cell.box.w > 70.0
            assert all(not chip.text.endswith("…") for chip in cell.chips)
            for chip in cell.chips:
                assert chip.rect.x >= cell.box.x - 0.01
                assert chip.rect.x + chip.rect.w <= cell.box.x + cell.box.w + 0.01
        raised = [d for d in layout.diagnostics if d.rule == "declared-width"]
        assert len(raised) == 1
        assert raised[0].measured.count("70px to") == 3

    def test_declared_widths_that_cannot_fit_the_frame_refuse_by_name(self) -> None:
        """Eight declared-narrow chip columns whose content floors exceed the
        ceiling refuse by name instead of rendering eight columns of ``none…``."""
        spec = MatrixSpec(
            title="T",
            columns=[{"id": "l", "label": "L", "role": "label"}]
            + [{"id": f"c{j}", "label": f"C{j}", "kind": "chip", "width": 70} for j in range(8)],
            rows=[{"label": "r", "cells": [{"chips": ["none (opaque html)", "ok"]}] * 8}],
        )
        with pytest.raises(MatrixCapacityError, match="narrow the widest columns"):
            solve(spec)

    def test_wide_headers_wrap_instead_of_refusing(self) -> None:
        """Six long text headers on a 900px frame wrap to two runs inside their
        own columns; the header band grows and nothing truncates."""
        spec = MatrixSpec(
            title="Ledger",
            columns=[
                {"id": "d", "label": "DEFECT IDENTIFIED", "role": "label"},
                {"id": "s", "label": "SURFACE / TOPO", "kind": "chip"},
                {"id": "v", "label": "VIOLATED GEOMETRIC INVARIANT", "kind": "text"},
                {"id": "m", "label": "MEASURED DELTA", "kind": "text"},
                {"id": "r", "label": "ROOT CAUSE FILE & LINE", "kind": "text"},
                {"id": "sev", "label": "SEVERITY", "kind": "pill"},
            ],
            rows=[
                {
                    "label": "Column Header Smashing",
                    "cells": [
                        {"chips": ["matrix"]},
                        {"value": "col_w >= header_ink_w + 2*pad_x"},
                        {"value": "88.4px"},
                        {"value": "matrix/layout.py"},
                        {"value": "high"},
                    ],
                }
            ],
        )
        layout = solve(spec)
        assert max(self._header_overruns(layout)) <= 0.01
        assert max(len(h.lines) for h in layout.colheaders) >= 2
        assert not any(t.text.endswith("…") for h in layout.colheaders for t in h.lines)
        collapsed_masthead = CFG.masthead_h - CFG.desc_line_h  # no subtitle, no legend line
        assert layout.row_y[0] >= collapsed_masthead + CFG.colheader_h + (CFG.colhead_voice.size + 4.0) - 0.01

    def test_pill_keeps_its_value_at_every_state(self) -> None:
        """A pill labels its state: a supplied value renders in the state's
        tint for none and off too; only a valueless none pill draws the dash."""
        spec = MatrixSpec(
            title="T",
            columns=[{"id": "l", "label": "L", "role": "label"}, {"id": "s", "label": "SEVERITY", "kind": "pill"}],
            rows=[
                {"label": "a", "cells": [{"value": "CRITICAL", "state": "none"}]},
                {"label": "b", "cells": [{"value": "HIGH", "state": "partial"}]},
                {"label": "c", "cells": [{"state": "none"}]},
            ],
        )
        pills = [c for c in solve(spec).cells if c.kind == "pill"]
        assert [c.text for c in pills] == ["CRITICAL", "HIGH", "—"]
        assert pills[0].pill is not None and pills[0].mark_state == "none"
        assert pills[2].pill is None

    def test_glyph_column_never_compresses_below_its_mark(self) -> None:
        geometry = load_matrix_config()["cell_geometry"]
        spec = MatrixSpec(
            title="T",
            columns=[{"id": "l", "label": "L", "role": "label"}, {"id": "g", "label": "", "kind": "glyph"}]
            + [{"id": f"c{j}", "label": f"A LONG HEADER LABEL {j}", "kind": "text"} for j in range(6)],
            rows=[{"label": "r", "cells": [{"glyph": "github"}] + [{"value": "some value text"}] * 6}],
        )
        layout = solve(spec)
        assert layout.col_w[0] >= geometry["glyph"]["size"] + 2 * CFG.cell_pad_x - 0.01

    def test_single_oversized_chip_stays_inside_its_cell(self) -> None:
        """A caller-declared width narrower than the widest single chip yields
        to the chip's intrinsic floor: the column grows and the chip stays
        whole inside its cell."""
        spec = MatrixSpec(
            title="T",
            columns=[
                {"id": "l", "label": "L", "role": "label"},
                {"id": "c", "label": "C", "kind": "chip", "width": 70},
            ],
            rows=[{"label": "r", "cells": [{"chips": ["none (opaque html)", "ok"]}]}],
        )
        layout = solve(spec)
        cell = next(c for c in layout.cells if c.kind == "chip")
        for chip in cell.chips:
            assert chip.rect.x >= cell.box.x - 0.01
            assert chip.rect.x + chip.rect.w <= cell.box.x + cell.box.w + 0.01
        assert cell.chips[0].text == "none (opaque html)"
        assert cell.box.w >= cell.chips[0].rect.w + 2 * CFG.cell_pad_x - 0.01

    def test_title_takes_the_largest_size_that_fits(self) -> None:
        """The fitted title size floors to the tenth-pixel grid and is re-measured:
        a size rounded 0.03px high used to ellipsize a title that fit whole."""
        from hyperweave.compose.geometry.text import measure_voice

        title = "Pair Programming with HyperWeave: The Agent Perspective"
        spec = MatrixSpec(
            title=title,
            columns=[{"id": "l", "label": "L", "role": "label"}, {"id": "v", "label": "V", "kind": "text"}],
            rows=[{"label": "r", "cells": [{"value": "v"}]}],
        )
        layout = solve(spec)
        assert layout.header.title is not None
        assert layout.header.title.text == title.upper()
        assert layout.title_size == 24.8
        voice = CFG.title_voice.model_copy(update={"size": layout.title_size})
        assert measure_voice(title.upper(), voice) <= layout.width - 2 * CFG.margin_x + 0.01
        bigger = CFG.title_voice.model_copy(update={"size": round(layout.title_size + 0.1, 1)})
        assert (
            measure_voice(title.upper(), bigger) > layout.width - 2 * CFG.margin_x
            or layout.title_size == CFG.title_voice.size
        )

    @pytest.mark.parametrize(
        "probe",
        [
            "mat-audit-capabilities",
            "mat-audit-prompt-generators",
            "mat-audit-agent-experience",
            "mat-audit-defect-ledger",
        ],
    )
    def test_audit_matrices_render_contained_and_whole(self, probe: str) -> None:
        """The four matrices the audit rendered: every header run inside its
        column with both pads, every drawn primitive inside its cell, and no
        ellipsis anywhere except a title that has reached its size floor."""
        import json
        from pathlib import Path

        from hyperweave.compose.geometry.text import measure_voice

        payload = json.loads(
            (Path(__file__).parents[1] / "fixtures" / "spatial" / "probes" / f"{probe}.json").read_text()
        )
        layout = solve(MatrixSpec(**payload["compose"]["matrix"]))
        assert max(self._header_overruns(layout)) <= 0.01
        for cell in layout.cells:
            x0, x1 = cell.box.x - 0.01, cell.box.x + cell.box.w + 0.01
            rects = [cell.track, cell.bar_fill, cell.pill, cell.heat_tile, cell.heat_track, cell.heat_underline]
            rects.extend(chip.rect for chip in cell.chips)
            assert all(x0 <= r.x and r.x + r.w <= x1 for r in rects if r is not None), (probe, cell.row, cell.col)
            runs = [cell.text, cell.sub_text, *(t.text for t in cell.text_lines), *(t.text for t in cell.sub_lines)]
            runs.extend(chip.text for chip in cell.chips)
            assert not any(r.endswith("…") for r in runs), (probe, cell.row, cell.col, runs)
        if layout.header.title is not None and layout.header.title.text.endswith("…"):
            assert layout.title_size == CFG.title_size_floor
        else:
            voice = CFG.title_voice.model_copy(update={"size": layout.title_size})
            assert layout.header.title is None or (
                layout.header.title.x + measure_voice(layout.header.title.text, voice)
                <= layout.width - CFG.margin_x + 0.01
            )

    def test_title_clears_the_headline_chip(self) -> None:
        from hyperweave.compose.geometry.text import measure_voice

        spec = MatrixSpec(
            title="Realtime autonomous agent fleet telemetry and orchestration",
            headline={"value": "99.98%", "label": "System availability SLA"},
            columns=[
                {"id": "node", "label": "COMPUTE NODE", "role": "label"},
                {"id": "stat", "label": "HEALTH", "kind": "check"},
                {"id": "reg", "label": "REGION", "kind": "text"},
            ],
            rows=[{"label": "Worker node 01", "cells": [{"state": "full"}, {"value": "us-east"}]}],
        )
        layout = solve(spec)
        assert layout.header.title is not None and layout.header.headline_chip is not None
        voice = CFG.title_voice.model_copy(update={"size": layout.title_size})
        title_right = layout.header.title.x + measure_voice(layout.header.title.text, voice)
        assert title_right <= layout.header.headline_chip.x + 0.01
        assert title_right <= layout.width - CFG.margin_x + 0.01

    def test_title_without_furniture_still_fits_the_content_box(self) -> None:
        from hyperweave.compose.geometry.text import measure_voice

        spec = MatrixSpec(
            title="Pair programming with the compositor from the agent perspective at length",
            columns=[{"id": "l", "label": "L", "role": "label"}, {"id": "v", "label": "V", "kind": "check"}],
            rows=[{"label": "r", "cells": [{"state": "full"}]}],
        )
        layout = solve(spec)
        assert layout.header.title is not None
        voice = CFG.title_voice.model_copy(update={"size": layout.title_size})
        title_right = layout.header.title.x + measure_voice(layout.header.title.text, voice)
        assert title_right <= layout.width - CFG.margin_x + 0.01
        assert layout.title_size >= CFG.title_size_floor

    def test_summary_label_sizes_the_label_column(self) -> None:
        from hyperweave.compose.geometry.text import measure_voice

        spec = MatrixSpec(
            title="Format comparison",
            summary_label="OVERALL SUITABILITY SCORE ACROSS TOOLCHAIN",
            columns=[{"id": "cap", "label": "CAPABILITY", "role": "label"}]
            + [{"id": f"c{j}", "label": f"C{j}", "kind": "check"} for j in range(3)],
            rows=[{"label": "Renders", "cells": [{"state": "full"}] * 3}],
            summary_row=[{"value": "9/10"}, {"value": "6/10"}, {"value": "4/10"}],
        )
        layout = solve(spec)
        assert layout.summary is not None and layout.summary.label is not None
        label_w = layout.col_x[0] - CFG.margin_x
        assert measure_voice(layout.summary.label.text, CFG.colhead_voice) + 2 * CFG.cell_pad_x <= label_w + 0.01
        assert layout.summary.label.text == spec.summary_label

    def test_bar_axis_grades_the_bar_track(self) -> None:
        spec = MatrixSpec(
            title="Tokens per tool",
            columns=[{"id": "tool", "label": "TOOL", "role": "label"}, {"id": "tok", "label": "TOKENS", "kind": "bar"}],
            rows=[
                {"label": "parse_schema", "cells": [{"value": 3420}]},
                {"label": "execute", "cells": [{"value": 1800}]},
            ],
        )
        layout = solve(spec)
        assert layout.axis is not None
        track = next(c.track for c in layout.cells if c.kind == "bar" and c.track is not None)
        axis_right = max(line.x1 for line in layout.axis.grid_lines)
        assert axis_right <= track.x + track.w + 0.01
        # The tick for the maximum value lands on the full bar's end.
        full = next(c for c in layout.cells if c.kind == "bar" and c.text.startswith("3,420"))
        assert full.bar_fill is not None
        assert abs((full.bar_fill.x + full.bar_fill.w) - (track.x + track.w)) <= 0.01

    def test_no_rect_is_ever_negative(self) -> None:
        spec = MatrixSpec(
            title="Heat under pressure",
            columns=[{"id": "m", "label": "MODEL", "role": "label"}]
            + [{"id": f"c{j}", "label": f"C{j}", "kind": "chip"} for j in range(11)]
            + [{"id": "score", "label": "SCORE", "kind": "numeric", "polarity": "higher"}],
            rows=[
                {"label": "A", "cells": [{"chips": ["x"]} for _ in range(11)] + [{"value": 91.2}]},
                {"label": "B", "cells": [{"chips": ["y"]} for _ in range(11)] + [{"value": 42.0}]},
            ],
        )
        layout = solve(spec)
        for cell in layout.cells:
            rects = [
                cell.box,
                cell.track,
                cell.bar_fill,
                cell.pill,
                cell.heat_tile,
                cell.heat_track,
                cell.heat_underline,
            ]
            rects.extend(chip.rect for chip in cell.chips)
            assert all(r.w >= 0.0 and r.h >= 0.0 for r in rects if r is not None), cell

    def test_sectioned_labels_at_their_exact_need_never_ellipsize(self) -> None:
        """The label column's need is whole pixels, so a label whose ink equals
        the budget to the last bit still renders whole (the `Diagram (diagram/…`
        knife edge on the capabilities matrix)."""
        labels = ["Diagram (diagram/1)", "Matrix (matrix/1)", "Receipt (telemetry)", "Badge & Strip"]
        spec = MatrixSpec(
            title="Capabilities",
            sections=["Core"],
            columns=[{"id": "s", "label": "SURFACE", "role": "label"}, {"id": "v", "label": "VERBS", "kind": "chip"}],
            rows=[{"label": lb, "section": "Core", "cells": [{"chips": ["compose"]}]} for lb in labels],
        )
        layout = solve(spec)
        rendered = [c.text for c in layout.cells if c.col == -1 and c.kind == "text"]
        assert rendered == labels

    def test_authored_note_paragraphs_stay_inside_their_row(self) -> None:
        note = "\n".join(f"paragraph {k}" for k in range(5))
        spec = MatrixSpec(
            title="T",
            columns=[{"id": "l", "label": "L", "role": "label"}, {"id": "t", "label": "TEXT", "kind": "text"}],
            rows=[{"label": "r", "cells": [{"value": "value", "note": note}]}],
        )
        layout = solve(spec)
        cell = next(c for c in layout.cells if c.kind == "text" and c.col == 0)
        bottom = max((t.y for t in cell.sub_lines), default=cell.sub_y) + CFG.row_sub_voice.size * 0.25
        assert bottom <= cell.box.y + cell.box.h + 0.01
