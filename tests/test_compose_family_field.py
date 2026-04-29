"""ComposeSpec.family field — Phase 1 wiring validation.

Scope: field accepts the 4 allowed values ("", "blue", "purple", "bifamily"),
rejects any other string. Cross-surface parity (CLI/HTTP/MCP) is covered
by smoke tests in those suites; this file locks the model-level contract.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hyperweave.core.models import ComposeSpec


def test_family_defaults_to_empty() -> None:
    """Empty default = 'frame-type default, resolved at paradigm time'."""
    spec = ComposeSpec(type="badge")
    assert spec.family == ""


@pytest.mark.parametrize("value", ["", "blue", "purple", "bifamily"])
def test_family_accepts_allowed_values(value: str) -> None:
    spec = ComposeSpec(type="badge", family=value)
    assert spec.family == value


@pytest.mark.parametrize("value", ["teal", "amethyst", "BLUE", "Purple", "green"])
def test_family_rejects_unknown_values(value: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ComposeSpec(type="badge", family=value)
    message = str(exc_info.value)
    assert "family" in message
