"""Matrix input coercion + conservative inference contracts."""

from __future__ import annotations

import json

import pytest

from hyperweave.compose.matrix.infer import infer_matrix
from hyperweave.compose.matrix.input import (
    build_connector_registry_matrix,
    build_tokens_matrix,
    coerce_matrix_input,
    matrix_preset_names,
    resolve_matrix_preset,
)
from hyperweave.config.loader import load_connector_registry
from hyperweave.core.matrix import (
    Align,
    CellKind,
    MatrixInputError,
    MatrixSpec,
    Polarity,
    RowHeight,
)
from hyperweave.core.models import ComposeSpec
from tests.conftest import FIXTURES_DIR

MATRIX_FIXTURES = FIXTURES_DIR / "matrix"


def load_fixture(name: str) -> MatrixSpec:
    return MatrixSpec.model_validate(json.loads((MATRIX_FIXTURES / f"{name}.json").read_text()))


def all_fixture_specs() -> dict[str, MatrixSpec]:
    """The six canonical specs: five files + the generated connector matrix."""
    specs = {path.stem: load_fixture(path.stem) for path in sorted(MATRIX_FIXTURES.glob("*.json"))}
    specs["connectors"] = build_connector_registry_matrix(load_connector_registry())
    return specs


class TestCoercion:
    def test_caller_spec_passthrough(self) -> None:
        table = load_fixture("check")
        spec = ComposeSpec(type="matrix", matrix=table)
        assert coerce_matrix_input(None, spec) is table

    def test_connector_registry_adapter(self) -> None:
        spec = ComposeSpec(type="matrix", connector_data={"matrix_adapter": "connector-registry"})
        table = coerce_matrix_input(spec.connector_data, spec)
        assert len(table.rows) == len(load_connector_registry())
        assert table.columns[1].kind is CellKind.CHIP
        assert table.row_height is RowHeight.CONTENT
        assert table.rows[0].glyph == "github" and table.rows[0].sublabel == "gh:"
        # the registry adapter authors kinds explicitly — nothing left AUTO
        assert all(c.kind is not CellKind.AUTO for c in table.columns[1:])

    def test_unknown_adapter_raises(self) -> None:
        spec = ComposeSpec(type="matrix", connector_data={"matrix_adapter": "nope"})
        with pytest.raises(MatrixInputError, match="unknown matrix adapter"):
            coerce_matrix_input(spec.connector_data, spec)

    def test_no_input_raises(self) -> None:
        with pytest.raises(MatrixInputError, match="requires a table"):
            coerce_matrix_input(None, ComposeSpec(type="matrix"))

    def test_tokens_matrix(self) -> None:
        from hyperweave.serve.data_tokens import ResolvedToken

        tokens = [
            ResolvedToken(kind="live", label="STARS", value="1.2k", provider="github", raw_value=1234),
            ResolvedToken(kind="kv", label="PHASE", value="alpha"),
            ResolvedToken(kind="text", label="", value="ignored free text"),
        ]
        table = build_tokens_matrix(tokens)
        assert [r.label for r in table.rows] == ["STARS", "PHASE"]
        assert table.rows[0].cells[0].value == 1234  # raw value preferred
        assert table.rows[0].glyph == "github"

    def test_presets(self) -> None:
        assert "connectors" in matrix_preset_names()
        assert resolve_matrix_preset("connectors") == {"matrix_adapter": "connector-registry"}
        with pytest.raises(MatrixInputError, match="unknown matrix preset"):
            resolve_matrix_preset("nope")


class TestInference:
    def test_kind_inference_table(self) -> None:
        table = infer_matrix(
            MatrixSpec(
                title="T",
                columns=[
                    {"id": "label", "label": "L", "role": "label"},
                    {"id": "checks", "label": "V"},
                    {"id": "chips", "label": "C"},
                    {"id": "glyphs", "label": "G"},
                    {"id": "bools", "label": "B"},
                    {"id": "nums", "label": "N"},
                    {"id": "text", "label": "T"},
                ],
                rows=[
                    {
                        "label": "r1",
                        "cells": [
                            {"state": "full"},
                            {"chips": ["a", "b"]},
                            {"glyph": "github"},
                            {"value": True},
                            {"value": 1.5},
                            {"value": "prose"},
                        ],
                    },
                    {
                        "label": "r2",
                        "cells": [
                            {"state": "none"},
                            {"chips": ["c"]},
                            {"glyph": "pypi"},
                            {"value": False},
                            {"value": "2.5"},
                            {"value": "more"},
                        ],
                    },
                ],
            )
        )
        kinds = [c.kind for c in table.columns[1:]]
        assert kinds == [
            CellKind.CHECK,
            CellKind.CHIP,
            CellKind.GLYPH,
            CellKind.PILL,
            CellKind.NUMERIC,
            CellKind.TEXT,
        ]

    def test_bar_and_dot_never_inferred(self) -> None:
        # numbers infer NUMERIC (never BAR); short enums stay TEXT (never DOT)
        table = infer_matrix(
            MatrixSpec(
                title="T",
                columns=[{"id": "n", "label": "Tokens"}, {"id": "tier", "label": "Tier"}],
                rows=[
                    {"label": "a", "cells": [{"value": 100}, {"value": "lo"}]},
                    {"label": "b", "cells": [{"value": 900}, {"value": "hi"}]},
                ],
            )
        )
        assert table.columns[0].kind is CellKind.NUMERIC
        assert table.columns[1].kind is CellKind.TEXT

    def test_rhetoric_never_inferred(self) -> None:
        # winner-shaped data: one column dominates — still no hero/headline/summary
        table = infer_matrix(
            MatrixSpec(
                title="T",
                columns=[{"id": "a", "label": "Score A"}, {"id": "b", "label": "Score B"}],
                rows=[{"label": "r", "cells": [{"value": 99}, {"value": 1}]}],
            )
        )
        assert table.hero_column is None
        assert table.headline is None
        assert table.summary_row is None
        assert not any(row.emphasis for row in table.rows)

    def test_polarity_keywords(self) -> None:
        table = infer_matrix(
            MatrixSpec(
                title="T",
                columns=[
                    {"id": "lat", "label": "Latency", "sublabel": "ms"},
                    {"id": "score", "label": "Score"},
                    {"id": "name", "label": "Name"},
                    {"id": "explicit", "label": "Latency", "polarity": "higher"},
                ],
                rows=[{"label": "r", "cells": [{"value": 1}, {"value": 2}, {"value": 3}, {"value": 4}]}],
            )
        )
        assert table.columns[0].polarity is Polarity.LOWER
        assert table.columns[1].polarity is Polarity.HIGHER
        assert table.columns[2].polarity is Polarity.NONE
        # explicit polarity survives inference untouched
        assert table.columns[3].polarity is Polarity.HIGHER

    def test_alignment_defaults(self) -> None:
        # Heat-bearing numeric columns center (the tile is a centered object,
        # the header shares its axis); PLAIN numeric stays right-aligned.
        table = infer_matrix(load_fixture("benchmark"))
        label_col = table.columns[0]
        assert label_col.align is Align.LEFT
        assert all(c.align is Align.CENTER for c in table.columns[1:])
        plain = infer_matrix(
            MatrixSpec(
                title="T",
                columns=[{"id": "n", "label": "Amount"}],
                rows=[{"label": "r", "cells": [{"value": 7}]}],
            )
        )
        assert plain.columns[0].polarity is Polarity.NONE
        assert plain.columns[0].align is Align.RIGHT

    def test_scattered_empty_cells_do_not_flip_kind(self) -> None:
        table = infer_matrix(
            MatrixSpec(
                title="T",
                columns=[{"id": "n", "label": "Count"}],
                rows=[
                    {"label": "a", "cells": [{"value": 5}]},
                    {"label": "b", "cells": [{}]},
                    {"label": "c", "cells": [{"value": 7}]},
                ],
            )
        )
        assert table.columns[0].kind is CellKind.NUMERIC


class TestGenericity:
    def test_all_fixtures_share_one_field_set(self) -> None:
        """Directive 6: no fixture-specific field anywhere — every canonical
        spec validates against the identical MatrixSpec schema."""
        field_set = set(MatrixSpec.model_fields)
        for name, spec in all_fixture_specs().items():
            assert set(spec.model_dump().keys()) <= field_set, name
            # round-trips through the schema unchanged
            assert MatrixSpec.model_validate(spec.model_dump(mode="json")) == spec, name
