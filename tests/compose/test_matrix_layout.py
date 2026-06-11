"""Matrix layout solver invariants — geometry the templates rely on."""

from __future__ import annotations

import pytest

from hyperweave.compose.matrix_infer import infer_matrix
from hyperweave.compose.matrix_layout import compute_matrix_layout
from hyperweave.compose.matrix_records import MatrixLayout  # noqa: TC001 (runtime return type)
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

    def test_text_overflow_wraps_then_caps(self) -> None:
        """Text cells wrap by default — the row grows in content mode; the
        ellipsis appears only on the final permitted line once content
        exceeds max_lines. Short siblings stay single-run."""
        long = "a commit subject that runs well past a narrow column and keeps going with more words " * 2
        spec = MatrixSpec(
            title="T",
            columns=[{"id": "l", "label": "L", "role": "label"}]
            + [{"id": k, "label": k.upper(), "kind": "text", "width": 120} for k in ("a", "b", "c")],
            rows=[{"label": "r", "cells": [{"value": long}, {"value": "short"}, {"value": "also short"}]}],
        )
        layout = solve(spec)
        geometry = load_matrix_config()["cell_geometry"]
        max_lines = int(geometry["text"]["max_lines"])
        wrapped = next(c for c in layout.cells if c.row == 0 and c.col == 0)
        assert len(wrapped.text_lines) == max_lines
        assert wrapped.text_lines[-1].text.endswith("…")
        assert all(not line.text.endswith("…") for line in wrapped.text_lines[:-1])
        short = next(c for c in layout.cells if c.row == 0 and c.col == 1)
        assert short.text_lines == () and short.text == "short"
        assert layout.row_h[0] > CFG.row_pitch  # the row grew to fit the stack

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

    def test_label_truncation_is_measured(self) -> None:
        from hyperweave.compose.matrix_cells import measure_voice

        long_label = "An extremely long capability label that cannot possibly fit the label column"
        spec = MatrixSpec(
            title="T",
            columns=[{"id": "v", "label": "V", "kind": "check"}],
            rows=[{"label": long_label, "cells": [{"state": "full"}]}],
        )
        layout = solve(spec)
        label_cell = next(c for c in layout.cells if c.kind == "text" and c.row == 0)
        assert label_cell.text.endswith("…")
        max_w = label_cell.box.w - 2 * CFG.cell_pad_x
        assert measure_voice(label_cell.text, CFG.row_label_voice) <= max_w

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
            assert tile.x >= layout.col_x[cell.col] - 0.01
            assert tile.x + tile.w <= layout.col_x[cell.col] + layout.col_w[cell.col] + 0.01

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

    def test_legend_shares_descriptor_line_when_it_fits(self) -> None:
        """The legend rides the subtitle's line whenever the pair can share
        at the ceiling — identity left, key right, one masthead band (the
        g3 specimen) — even on compact frames, where only the title steps
        down."""
        layout = solve(load_fixture("check"))
        assert layout.width < CFG.compact_below
        assert layout.title_voice_size == CFG.title_compact_size
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
        """At or above the compact threshold the legend stays on the shared
        descriptor line and the title keeps its full voice — the specimen
        gestalt."""
        wide = load_fixture("check").model_copy(
            update={"title": "An exceptionally long masthead title that forces a wide solve"}
        )
        layout = solve(wide)
        assert layout.width >= CFG.compact_below
        assert layout.title_voice_size == CFG.title_voice.size
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
        from hyperweave.compose.matrix_cells import measure_voice

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
