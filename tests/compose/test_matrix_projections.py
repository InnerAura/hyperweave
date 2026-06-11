"""Matrix projections: payload losslessness, hwz/1 envelope canon, markdown."""

from __future__ import annotations

import json

import pytest

from hyperweave.compose.matrix_infer import infer_matrix
from hyperweave.compose.matrix_project import (
    ENVELOPE_ROW_CAP,
    PAYLOAD_SCHEMA,
    derive_subvariant,
    matrix_desc,
    matrix_envelope_data,
    matrix_payload_json,
    to_markdown,
)
from hyperweave.core.envelope import (
    ENVELOPE_VERSION,
    OPTIONAL_KEYS,
    REQUIRED_KEYS,
    build_envelope,
    envelope_id,
    envelope_json,
    validate_envelope,
)
from hyperweave.core.matrix import MatrixSpec
from tests.compose.test_matrix_input import all_fixture_specs, load_fixture


def build(spec: MatrixSpec, **kw: str) -> dict[str, object]:
    payload = matrix_payload_json(spec)
    sub = derive_subvariant(infer_matrix(spec))
    return build_envelope(
        kind="matrix",
        title=spec.title,
        intent=kw.get("intent", "test"),
        data=matrix_envelope_data(spec, subvariant=sub),
        frames=[{"t": "matrix", "l": spec.title}],
        payload_json=payload,
        genome_label="primer.porcelain",
        version="0.4.0a2",
        created="2026-06-09T12:00:00+00:00",
        state="stable",
    )


class TestPayload:
    @pytest.mark.parametrize("name", ["check", "tiers", "readcost", "plans", "benchmark", "connectors"])
    def test_lossless_round_trip(self, name: str) -> None:
        spec = all_fixture_specs()[name]
        restored = MatrixSpec.model_validate(json.loads(matrix_payload_json(spec)))
        assert restored == spec

    def test_payload_schema_id(self) -> None:
        assert PAYLOAD_SCHEMA == "matrix/1"

    def test_cdata_hazard_is_neutralized_losslessly(self) -> None:
        spec = MatrixSpec(
            title="contains ]]> hazard",
            columns=[{"id": "v", "label": "V"}],
            rows=[{"label": "row ]]> too", "cells": [{"value": "x"}]}],
        )
        payload = matrix_payload_json(spec)
        assert "]]>" not in payload
        restored = MatrixSpec.model_validate(json.loads(payload))
        assert restored.title == "contains ]]> hazard"
        assert restored.rows[0].label == "row ]]> too"


class TestEnvelopeCanon:
    """GATE 1: the canonical hwz/1 shape, asserted exactly."""

    def test_exact_top_level_key_set(self) -> None:
        env = build(load_fixture("check"))
        keys = set(env.keys())
        assert keys >= REQUIRED_KEYS
        assert keys - REQUIRED_KEYS <= OPTIONAL_KEYS
        # emission order is canonical: v leads, prov closes
        ordered = list(env.keys())
        assert ordered[0] == "v" and ordered[-1] == "prov"

    def test_no_ttok_anywhere(self) -> None:
        env = build(load_fixture("check"))
        assert "ttok" not in env
        with pytest.raises(ValueError, match="unknown top-level keys"):
            validate_envelope({**env, "ttok": 99})

    def test_id_recomputable_from_payload(self) -> None:
        spec = load_fixture("benchmark")
        env = build(spec)
        assert env["id"] == envelope_id(matrix_payload_json(spec))

    def test_validates_and_round_trips_json(self) -> None:
        env = build(load_fixture("tiers"))
        validate_envelope(env)
        assert json.loads(envelope_json(env)) == env
        assert env["v"] == ENVELOPE_VERSION

    def test_nothing_matrix_specific_at_top_level(self) -> None:
        env = build(all_fixture_specs()["connectors"])
        assert "subvariant" not in env and "cols" not in env and "rows" not in env
        data = env["data"]
        assert isinstance(data, dict) and "subvariant" in data and "cols" in data

    def test_rows_total_always_present_and_caps_self_describe(self) -> None:
        small = matrix_envelope_data(load_fixture("check"), subvariant="check")
        assert small["rows_total"] == 7 and len(small["rows"]) == 7
        big = infer_matrix(
            MatrixSpec(
                title="Big",
                columns=[{"id": "v", "label": "V"}],
                rows=[{"label": f"row {i}", "cells": [{"value": i}]} for i in range(20)],
            )
        )
        capped = matrix_envelope_data(big, subvariant="table")
        assert len(capped["rows"]) == ENVELOPE_ROW_CAP
        assert capped["rows_total"] == 20

    def test_prov_shape(self) -> None:
        env = build(load_fixture("check"))
        prov = env["prov"]
        assert isinstance(prov, dict)
        assert set(prov.keys()) == {"by", "ver", "genome", "ts"}
        assert prov["by"] == "hyperweave"
        assert prov["ts"] == "2026-06-09T12:00:00+00:00"


class TestSubvariant:
    def test_derivation(self) -> None:
        expected = {
            "check": "check",
            "tiers": "tier-span",
            "readcost": "bar-scale",
            "plans": "pill-tags",
            "benchmark": "numeric-heat",
            "connectors": "registry",
        }
        specs = all_fixture_specs()
        for name, sub in expected.items():
            assert derive_subvariant(infer_matrix(specs[name])) == sub, name

    def test_dot_projection_splits_on_chain(self) -> None:
        """Chained inclusion sets project as tier-span; a non-nested dot
        grid keeps tier-dot. Category first, projection second."""
        from hyperweave.core.matrix import MatrixCell, is_chain

        chained = infer_matrix(load_fixture("tiers"))
        assert is_chain(chained)
        # Break the chain: a row included in tier 1 but not tier 3.
        rows = list(chained.rows)
        cells = list(rows[0].cells)
        cells[0] = MatrixCell(state="on")
        cells[2] = MatrixCell(state="off")
        rows[0] = rows[0].model_copy(update={"cells": cells})
        broken = chained.model_copy(update={"rows": rows})
        assert not is_chain(broken)
        assert derive_subvariant(broken) == "tier-dot"

    def test_is_chain_guards(self) -> None:
        """The chain predicate demands two-plus all-dot columns and no
        partial states — anything else keeps the grid."""
        from hyperweave.core.matrix import MatrixCell, MatrixSpec, is_chain

        single = MatrixSpec(
            title="T",
            columns=[{"id": "l", "label": "L", "role": "label"}, {"id": "a", "label": "A", "kind": "dot"}],
            rows=[{"label": "r", "cells": [{"state": "on"}]}],
        )
        assert not is_chain(single)
        chained = infer_matrix(load_fixture("tiers"))
        rows = list(chained.rows)
        cells = list(rows[0].cells)
        cells[0] = MatrixCell(state="partial")
        rows[0] = rows[0].model_copy(update={"cells": cells})
        assert not is_chain(chained.model_copy(update={"rows": rows}))


class TestMarkdown:
    def test_check_glyph_mapping(self) -> None:
        md = to_markdown(infer_matrix(load_fixture("check")))
        assert "| CAPABILITY | SVG | PNG | HTML | Markdown |" in md
        assert "✓" in md and "~" in md and "✗" in md
        assert "**SCORE**" in md and "9.5 (complete)" in md

    def test_dot_and_sections(self) -> None:
        md = to_markdown(infer_matrix(load_fixture("tiers")))
        assert "●" in md and "○" in md
        assert "**Identity & provenance**" in md

    def test_bar_carries_unit(self) -> None:
        md = to_markdown(infer_matrix(load_fixture("readcost")))
        assert "3,420 tok" in md

    def test_chips_full_list_no_overflow(self) -> None:
        md = to_markdown(infer_matrix(all_fixture_specs()["connectors"]))
        # markdown carries the FULL chip list — overflow is a rendering concern
        assert "deploy_frequency, lead_time, change_failure_rate, mttr" in md

    def test_alignment_row(self) -> None:
        # heat columns center; the GFM align row mirrors the resolved aligns
        md = to_markdown(infer_matrix(load_fixture("benchmark")))
        assert "|:---|:---:|:---:|:---:|:---:|:---:|" in md.replace(" ", "")


class TestDesc:
    def test_generated_from_ir(self) -> None:
        desc = matrix_desc(load_fixture("check"), subvariant="check")
        assert "check matrix" in desc and "7 rows by 4 columns" in desc
        assert "hw:payload" in desc
