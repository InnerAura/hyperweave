"""HwError CLI rendering — per-field detail lines carry a path an agent can
repair against, without disturbing the plain message(+fix) contract other
callers already match on verbatim.
"""

from __future__ import annotations

from hyperweave.compose.surface import build_compose_spec
from hyperweave.core.errors import HwError, HwErrorCode, format_error_loc


def test_message_only_error_renders_byte_identical_to_bare_message() -> None:
    err = HwError(HwErrorCode.SPEC_INVALID, "boom")
    assert err.cli_text() == "boom"


def test_message_and_fix_error_renders_byte_identical_to_old_contract() -> None:
    err = HwError(HwErrorCode.SPEC_INVALID, "boom", fix="do the thing")
    assert err.cli_text() == "boom\n  fix: do the thing"


def test_format_error_loc_indexes_bind_to_the_preceding_segment() -> None:
    assert format_error_loc(("edges", 0, "source")) == "edges[0].source"
    assert format_error_loc(("title",)) == "title"


def test_pydantic_errors_render_as_indented_dotted_paths() -> None:
    errors = [
        {"type": "missing", "loc": ("edges", 0, "source"), "msg": "Field required"},
        {"type": "missing", "loc": ("edges", 0, "target"), "msg": "Field required"},
    ]
    err = HwError(HwErrorCode.SPEC_INVALID, "invalid diagram spec: 2 error(s)", detail={"errors": errors})
    lines = err.cli_text().splitlines()
    assert lines[0] == "invalid diagram spec: 2 error(s)"
    assert lines[1] == "  edges[0].source: Field required"
    assert lines[2] == "  edges[0].target: Field required"


def test_extra_forbidden_field_renders_as_unknown_field_not_pydantic_prose() -> None:
    errors = [{"type": "extra_forbidden", "loc": ("edges", 0, "from"), "msg": "Extra inputs are not permitted"}]
    err = HwError(HwErrorCode.SPEC_INVALID, "invalid diagram spec: unknown field", detail={"errors": errors})
    assert "edges[0].from: unknown field" in err.cli_text()


def test_detail_lines_cap_at_eight_with_a_remainder_count() -> None:
    errors = [{"type": "missing", "loc": ("a", i), "msg": "Field required"} for i in range(11)]
    err = HwError(HwErrorCode.SPEC_INVALID, "invalid x spec", detail={"errors": errors})
    lines = err.cli_text().splitlines()
    detail_lines = [line for line in lines[1:] if line.startswith("  a[")]
    assert len(detail_lines) == 8
    assert lines[-1] == "  ... and 3 more"


def test_fix_still_renders_last_after_detail_lines() -> None:
    errors = [{"type": "missing", "loc": ("title",), "msg": "Field required"}]
    err = HwError(HwErrorCode.SPEC_INVALID, "invalid badge spec", fix="add a title", detail={"errors": errors})
    assert err.cli_text().splitlines()[-1] == "  fix: add a title"


def test_diagram_spec_field_error_surfaces_an_indexed_field_path() -> None:
    """A misspelled edge field (a stand-in for the verified Mermaid-shaped
    from/to report) must name the exact field, not just a violation count —
    robust to a from/to alias landing at the model layer, since ``sourc`` is
    never a legal alias for anything."""
    kwargs = {
        "type": "diagram",
        "genome_id": "primer",
        "diagram": {
            "topology": "pipeline",
            "title": "T",
            "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            "edges": [{"sourc": "a", "target": "b"}],
        },
    }
    try:
        build_compose_spec(kwargs, "diagram")
    except HwError as exc:
        assert "edges[0]" in exc.message
        text = exc.cli_text()
        assert "edges[0].source: Field required" in text
        assert "edges[0].sourc: unknown field" in text
    else:
        raise AssertionError("expected HwError for a misspelled edge field")
