"""The single bundled-spec store — one resolver for CLI and HTTP."""

from __future__ import annotations

import pytest

from hyperweave.compose.bundled_specs import bundled_spec_names, resolve_bundled_spec
from hyperweave.core.errors import HwError, HwErrorCode


def test_matrix_spec_resolves_to_connector_data() -> None:
    """A matrix bundled spec fills connector_data (the adapter payload)."""
    resolved = resolve_bundled_spec("matrix", "connectors")
    assert resolved.field == "connector_data"
    assert isinstance(resolved.value, dict)


def test_diagram_spec_resolves_to_diagram_ir() -> None:
    """A diagram bundled spec fills the diagram IR field."""
    resolved = resolve_bundled_spec("diagram", "rag-pipeline")
    assert resolved.field == "diagram"
    assert "topology" in resolved.value


def test_unknown_name_raises_preset_unknown() -> None:
    with pytest.raises(HwError) as exc:
        resolve_bundled_spec("diagram", "no-such-spec")
    assert exc.value.code is HwErrorCode.PRESET_UNKNOWN
    assert "known diagram specs" in exc.value.fix


def test_frame_without_store_raises_type_unknown() -> None:
    with pytest.raises(HwError) as exc:
        resolve_bundled_spec("badge", "anything")
    assert exc.value.code is HwErrorCode.TYPE_UNKNOWN


def test_names_are_the_same_store_the_resolver_reads() -> None:
    """bundled_spec_names lists exactly what resolve_bundled_spec accepts —
    the CLI and HTTP surfaces read this one store, so they cannot drift."""
    for name in bundled_spec_names("diagram"):
        assert resolve_bundled_spec("diagram", name).field == "diagram"
    for name in bundled_spec_names("matrix"):
        assert resolve_bundled_spec("matrix", name).field == "connector_data"
