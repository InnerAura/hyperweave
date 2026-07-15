"""Registry contract: unknown-name, bad-payload, and HwError pass-through."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from hyperweave.core.errors import HwError, HwErrorCode
from hyperweave.surfaces.registry import (
    CallContext,
    Capability,
    all_capabilities,
    dispatch,
    get_capability,
    register,
)

_CTX = CallContext(surface="test")


async def test_unknown_capability_raises_type_unknown() -> None:
    with pytest.raises(HwError) as exc:
        await dispatch("does-not-exist", {}, _CTX)
    assert exc.value.code is HwErrorCode.TYPE_UNKNOWN
    assert "does-not-exist" in exc.value.message


async def test_bad_payload_raises_spec_invalid_with_pydantic_detail() -> None:
    # `extract` requires `source`; omit it → SPEC_INVALID carrying the errors.
    with pytest.raises(HwError) as exc:
        await dispatch("extract", {}, _CTX)
    assert exc.value.code is HwErrorCode.SPEC_INVALID
    errors = exc.value.detail.get("errors")
    assert isinstance(errors, list) and errors
    assert any(e.get("loc") == ("source",) for e in errors)


async def test_handler_hwerror_propagates_unchanged() -> None:
    # A well-formed payload whose source cannot resolve → the verb's own
    # HwError (ENVELOPE_CORRUPT) propagates through dispatch untouched.
    with pytest.raises(HwError) as exc:
        await dispatch("verify", {"source": "not-an-svg-and-not-a-cached-digest"}, _CTX)
    assert exc.value.code is HwErrorCode.ENVELOPE_CORRUPT


async def test_register_requires_mcp_tool_or_note() -> None:
    class _In(BaseModel):
        x: str = ""

    async def _handler(_model: BaseModel, _ctx: CallContext) -> dict[str, object]:
        return {}

    with pytest.raises(ValueError, match="mcp_note"):
        register(
            Capability(
                name="_probe_no_mcp",
                summary="probe",
                input_model=_In,
                handler=_handler,
                output_note="{}",
                mcp_tool=None,
                mcp_note="",
            )
        )


def test_roster_is_the_expected_set() -> None:
    names = {c.name for c in all_capabilities()}
    assert names == {"compose", "validate", "extract", "verify", "transform", "diff", "query", "discover"}
    # Every capability is retrievable by name.
    for name in names:
        assert get_capability(name) is not None
