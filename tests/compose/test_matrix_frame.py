"""Matrix frame end-to-end: compose() output contracts and the user gates."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from hyperweave.compose.engine import compose
from hyperweave.compose.matrix.cells import measure_voice
from hyperweave.compose.matrix.infer import infer_matrix
from hyperweave.compose.matrix.layout import _column_statistics, compute_matrix_layout
from hyperweave.config.loader import load_glyphs, load_matrix_config, load_paradigms
from hyperweave.core.envelope import envelope_id, validate_envelope
from hyperweave.core.matrix import (
    CellKind,
    ColRole,
    MatrixCell,
    MatrixColumn,
    MatrixRow,
    MatrixSpec,
    Polarity,
)
from hyperweave.core.models import ComposeSpec
from tests.compose.test_matrix_input import all_fixture_specs, load_fixture

PRIMER_VARIANTS = ("noir", "carbon", "space", "anvil", "porcelain", "cream", "dusk", "petrol")

_PAYLOAD_RE = re.compile(r"<hw:payload[^>]*><!\[CDATA\[(.*?)\]\]></hw:payload>", re.S)
_ENVELOPE_RE = re.compile(r"<hw:envelope[^>]*><!\[CDATA\[(.*?)\]\]></hw:envelope>", re.S)
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

CELLS_DIR = Path(__file__).resolve().parents[2] / "src" / "hyperweave" / "templates" / "frames" / "matrix" / "cells"


def compose_fixture(name: str, variant: str = "porcelain", **kw: object) -> str:
    return compose(
        ComposeSpec(type="matrix", genome_id="primer", variant=variant, matrix=all_fixture_specs()[name], **kw)
    ).svg


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
        return datetime(2026, 6, 9, 12, 0, 0, tzinfo=UTC)


class TestByteDeterminism:
    """GATE 2: identical spec → identical bytes; uid is a content hash."""

    def test_identical_bytes_with_pinned_clock(self) -> None:
        spec = ComposeSpec(type="matrix", genome_id="primer", variant="porcelain", matrix=load_fixture("check"))
        with patch("hyperweave.compose.context.datetime", _FrozenDatetime):
            first = compose(spec).svg
            second = compose(spec).svg
        assert first == second

    def test_no_random_tokens(self) -> None:
        svg = compose_fixture("check")
        assert not _UUID_RE.search(svg), "uuid leaked into matrix SVG"

    def test_uid_stable_across_runs_distinct_across_specs(self) -> None:
        a1 = re.search(r'id="(hw-[0-9a-f]{8})-clip"', compose_fixture("check"))
        a2 = re.search(r'id="(hw-[0-9a-f]{8})-clip"', compose_fixture("check"))
        b = re.search(r'id="(hw-[0-9a-f]{8})-clip"', compose_fixture("check", variant="noir"))
        c = re.search(r'id="(hw-[0-9a-f]{8})-clip"', compose_fixture("tiers"))
        assert a1 and a2 and b and c
        assert a1.group(1) == a2.group(1)
        assert len({a1.group(1), b.group(1), c.group(1)}) == 3


class TestEmbeddedProjections:
    """GATE 1 on the actual SVG bytes."""

    def test_payload_extracts_and_round_trips(self) -> None:
        """The embedded payload is the POST-INFERENCE spec — every column
        kind concrete, alignment resolved — so a consumer can re-render it
        without re-running inference."""
        from hyperweave.compose.matrix.infer import infer_matrix

        svg = compose_fixture("benchmark")
        match = _PAYLOAD_RE.search(svg)
        assert match is not None
        restored = MatrixSpec.model_validate(json.loads(match.group(1)))
        assert restored == infer_matrix(load_fixture("benchmark"))

    def test_payload_present_at_every_tier(self) -> None:
        for tier in (1, 2, 3):
            svg = compose_fixture("check", metadata_tier=tier)
            assert "<hw:payload" in svg, f"tier {tier}"
            assert 'schema="matrix/1"' in svg

    def test_envelope_validates_and_agrees_with_payload(self) -> None:
        svg = compose_fixture("check")
        payload = _PAYLOAD_RE.search(svg)
        envelope_match = _ENVELOPE_RE.search(svg)
        assert payload and envelope_match
        env = json.loads(envelope_match.group(1))
        validate_envelope(env)
        assert env["id"] == envelope_id(payload.group(1))
        created = re.search(r"<hw:created>([^<]+)</hw:created>", svg)
        assert created and env["prov"]["ts"] == created.group(1)
        assert env["prov"]["genome"] == "primer.porcelain"
        assert env["k"] == "matrix" and "ttok" not in env

    def test_markdown_on_result_never_in_svg(self) -> None:
        result = compose(ComposeSpec(type="matrix", genome_id="primer", matrix=load_fixture("check")))
        assert result.markdown.startswith("**Format comparison**")
        assert "| CAPABILITY |" not in result.svg

    def test_non_matrix_frames_unaffected(self) -> None:
        badge = compose(ComposeSpec(type="badge", title="BUILD", value="passing"))
        assert "<hw:payload" not in badge.svg
        assert "<hw:envelope" not in badge.svg
        assert badge.markdown == ""


class TestCellRegistry:
    def test_partials_biject_with_cell_kinds(self) -> None:
        """The registry is a directory: cells/*.j2 ↔ CellKind, exactly."""
        partials = {p.stem for p in CELLS_DIR.glob("*.j2")}
        kinds = {k.value for k in CellKind if k is not CellKind.AUTO}
        assert partials == kinds

    def test_check_only_matrix_leaks_no_other_kind(self) -> None:
        """Directive 5: unused CellPlacement channels never emit markup."""
        svg = compose_fixture("check")
        assert 'data-hw-cell="check-' in svg
        for forbidden in (
            'data-hw-cell="bar"',
            'data-hw-cell="pill-',
            'data-hw-cell="glyph"',
            'data-hw-cell="numeric-heat"',
            'data-hw-cell="dot-',
        ):
            assert forbidden not in svg, forbidden

    def test_dot_only_matrix_leaks_no_check(self) -> None:
        svg = compose_fixture("tiers")
        assert 'data-hw-cell="dot-' in svg
        assert 'data-hw-cell="check-' not in svg
        assert 'data-hw-cell="pill-' not in svg


class TestAccessibilityAndCim:
    @pytest.mark.parametrize("name", ["check", "connectors", "readcost"])
    def test_a11y_contract(self, name: str) -> None:
        svg = compose_fixture(name)
        for needle in ('role="img"', "aria-labelledby", "<title", "<desc", "xmlns:hw"):
            assert needle in svg, needle
        assert "prefers-reduced-motion" in svg
        assert "forced-colors: active" in svg
        assert "<script" not in svg

    def test_self_contained_fonts(self) -> None:
        svg = compose_fixture("check")
        assert 'data-hw-fonts="self-contained"' in svg
        assert svg.count("@font-face") >= 2  # inter + jetbrains-mono

    def test_cim_keyframes_compositor_only(self) -> None:
        svg = compose_fixture("check")
        for block in re.findall(r"@keyframes[^{]+\{(.*?)\}\s*\}", svg, re.S):
            assert not re.search(r"\b(cx|cy|r|d|width|height|x|y)\s*:", block), block
        assert "translateX" in svg  # the scan rail animates transform only

    def test_root_attributes(self) -> None:
        svg = compose_fixture("check")
        assert 'data-hw-frame="matrix"' in svg
        assert 'data-hw-subvariant="check"' in svg
        assert 'data-hw-genome="primer"' in svg


class TestChromaticCoverage:
    def test_all_eight_variants_render_with_their_signal(self) -> None:
        loader_genome = json.loads(
            (Path(__file__).resolve().parents[2] / "src/hyperweave/data/genomes/primer.json").read_text()
        )
        for variant in PRIMER_VARIANTS:
            svg = compose_fixture("check", variant=variant)
            accent = loader_genome["variant_overrides"][variant]["accent"]
            assert f"--dna-signal:{accent}" in svg.replace("; ", ";").replace(": ", ":"), variant

    def test_semantic_hexes_identical_across_poles(self) -> None:
        """Indicators are genome-invariant: byte-identical hues on porcelain
        AND noir (one hue for both poles, never per-mode pairs)."""
        light = compose_fixture("check", variant="porcelain")
        dark = compose_fixture("check", variant="noir")
        for hexv in ("#15803D", "#B45309", "#DC2626"):
            assert hexv in light and hexv in dark, hexv

    def test_glyph_tint_selection_reaches_payload_and_pixels(self) -> None:
        """``glyph_tint`` resolves into the table IR (the payload records
        what rendered) and the benchmark's explicit ``row_glyph_tint``
        outranks the caller selection."""
        plain = compose_fixture("connectors")
        full = compose_fixture("connectors", glyph_tint="full")
        assert plain != full  # color masters actually changed the pixels
        payload = json.loads(_PAYLOAD_RE.search(full).group(1))
        assert payload["row_glyph_tint"] == "full"
        # benchmark declares row_glyph_tint=brand explicitly — caller loses
        branded = compose_fixture("benchmark", glyph_tint="ink")
        payload = json.loads(_PAYLOAD_RE.search(branded).group(1))
        assert payload["row_glyph_tint"] == "brand"

    def test_evenodd_mark_carries_fill_rule(self) -> None:
        """A registry fill_rule reaches the rendered group — the evenodd
        marks break without it."""
        spec = {
            "title": "Editors",
            "columns": [
                {"id": "t", "label": "TOOL", "role": "label"},
                {"id": "m", "label": "MARK", "kind": "glyph"},
            ],
            "rows": [{"label": "VS Code", "cells": [{"glyph": "vscode"}]}],
        }
        svg = compose(ComposeSpec(type="matrix", genome_id="primer", matrix=spec)).svg
        assert 'fill-rule="evenodd"' in svg

    def test_unsupported_genome_raises_clear_error(self) -> None:
        with pytest.raises(ValueError, match="matrix frame is not supported by genome 'brutalist'"):
            compose(ComposeSpec(type="matrix", genome_id="brutalist", matrix=load_fixture("check")))


class TestReasoningMetadata:
    def test_tradeoffs_substantive(self) -> None:
        svg = compose_fixture("check", metadata_tier=3)
        match = re.search(r"<hw:tradeoffs>(.*?)</hw:tradeoffs>", svg, re.S)
        assert match is not None
        assert len(match.group(1).strip()) > 20


class TestFooterClearance:
    """Footer notes and the brand mark never overlap, for ANY notes length.
    The width solver reserves footer space; when the ceiling clamps that
    reservation away the notes truncate to clear the brand by ``footer_gap``."""

    _LONG_NOTES = (
        "SWE-bench Verified % (vendor + independent, varies by harness/scaffold) · "
        "price USD per million tokens · current flagships as of jun 13 2026 · "
        "sources: vals.ai · artificialanalysis.ai · model cards · plus a deliberately "
        "long tail to push the footer past the width ceiling and clamp the reservation"
    )

    def _footer(self, notes: str) -> tuple[float, float, str]:
        """(notes ink right edge, brand ink left edge, rendered notes text)."""
        config = load_matrix_config()
        cfg = load_paradigms()["primer"].matrix
        spec = MatrixSpec(
            title="Frontier benchmarks",
            columns=[
                MatrixColumn(id="model", label="Model", role=ColRole.LABEL),
                MatrixColumn(id="swe", label="SWE-bench", kind=CellKind.NUMERIC, polarity=Polarity.HIGHER, unit="%"),
                MatrixColumn(id="inp", label="Input", kind=CellKind.NUMERIC, polarity=Polarity.LOWER, unit="$"),
            ],
            rows=[
                MatrixRow(label="Fable 5", cells=[MatrixCell(value=95.0), MatrixCell(value=10.0)]),
                MatrixRow(label="Opus 4.8", cells=[MatrixCell(value=88.6), MatrixCell(value=5.0)]),
                MatrixRow(label="DeepSeek V4-Pro", cells=[MatrixCell(value=80.6), MatrixCell(value=0.44)]),
            ],
            notes=notes,
        )
        spec = infer_matrix(spec, config=config)
        lay = compute_matrix_layout(spec, matrix=cfg, config=config, glyph_registry=load_glyphs())
        assert lay.footer is not None
        assert lay.footer.notes is not None and lay.footer.brand is not None
        notes_right = lay.footer.notes.x + measure_voice(lay.footer.notes.text, cfg.foot_voice)
        brand_left = lay.footer.brand.x - measure_voice(lay.footer.brand.text, cfg.foot_brand_voice)
        return notes_right, brand_left, lay.footer.notes.text

    def test_long_notes_truncate_and_clear_brand(self) -> None:
        cfg = load_paradigms()["primer"].matrix
        notes_right, brand_left, text = self._footer(self._LONG_NOTES)
        # The overrunning string was truncated rather than placed at full length.
        assert text != self._LONG_NOTES
        assert text.endswith("…")
        # A real clearance gap separates the two — not a tuned offset.
        assert notes_right <= brand_left + 0.51
        assert brand_left - notes_right >= cfg.footer_gap - 0.6

    def test_short_notes_untouched_and_clear(self) -> None:
        short = "two sources · jun 2026"
        notes_right, brand_left, text = self._footer(short)
        # Notes that fit are placed verbatim — truncation is a no-op.
        assert text == short
        assert notes_right <= brand_left + 0.51


class TestGaugePolarity:
    """The gauge FILL is polarity-aware, mirroring the heat COLOUR. LOWER
    columns fill fuller for LOWER values (cheapest fullest); HIGHER and NONE
    columns keep the raw-magnitude fill unchanged."""

    def _stats(
        self,
    ) -> tuple[list[MatrixColumn], dict[tuple[int, int], float], dict[tuple[int, int], float]]:
        config = load_matrix_config()
        cfg = load_paradigms()["primer"].matrix
        spec = MatrixSpec(
            title="Polarity probe",
            columns=[
                MatrixColumn(id="model", label="Model", role=ColRole.LABEL),
                MatrixColumn(id="score", label="Score", kind=CellKind.NUMERIC, polarity=Polarity.HIGHER),
                MatrixColumn(id="price", label="Price", kind=CellKind.NUMERIC, polarity=Polarity.LOWER, unit="$"),
                MatrixColumn(id="count", label="Count", kind=CellKind.NUMERIC, polarity=Polarity.NONE),
            ],
            rows=[
                MatrixRow(label="A", cells=[MatrixCell(value=90.0), MatrixCell(value=10.0), MatrixCell(value=5.0)]),
                MatrixRow(label="B", cells=[MatrixCell(value=80.0), MatrixCell(value=2.0), MatrixCell(value=3.0)]),
            ],
        )
        spec = infer_matrix(spec, config=config)
        data_cols = [c for c in spec.columns if c.role is not ColRole.LABEL]
        cells_by_col = [[row.cells[j] for row in spec.rows] for j in range(len(data_cols))]
        heat_t, axis_frac, _ = _column_statistics(spec, data_cols, cells_by_col, cfg=cfg)
        return data_cols, axis_frac, heat_t

    def test_lower_inverts_higher_and_none_unchanged(self) -> None:
        data_cols, axis_frac, _ = self._stats()
        idx = {c.id: j for j, c in enumerate(data_cols)}
        assert data_cols[idx["price"]].polarity is Polarity.LOWER  # inference kept it
        sj, pj, nj = idx["score"], idx["price"], idx["count"]
        # HIGHER: the larger value fills fuller (row A, 90 > 80).
        assert axis_frac[(0, sj)] > axis_frac[(1, sj)]
        # LOWER (price): the cheaper value fills FULLER (row B, 2 < 10) — the fix.
        assert axis_frac[(1, pj)] > axis_frac[(0, pj)]
        # NONE: the raw-magnitude formula, byte-for-byte (max→full, min→stub).
        assert axis_frac[(0, nj)] == 0.12 + 0.88 * 1.0
        assert axis_frac[(1, nj)] == 0.12 + 0.88 * 0.0

    def test_fill_agrees_with_heat_colour(self) -> None:
        # Fill and tint favour the SAME row in a LOWER column — the gauge never
        # fights its colour. Row B (cheapest) maximises both.
        data_cols, axis_frac, heat_t = self._stats()
        pj = next(j for j, c in enumerate(data_cols) if c.id == "price")
        fullest = max(range(2), key=lambda i: axis_frac[(i, pj)])
        greenest = max(range(2), key=lambda i: heat_t[(i, pj)])
        assert fullest == greenest == 1
