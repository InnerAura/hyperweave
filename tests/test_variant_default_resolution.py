"""Variant default resolution — Phase 3.

An empty ``ComposeSpec.variant`` resolves per-frame via the paradigm's
``frame_variant_defaults`` map. Cellular paradigm declares
``badge=blue, strip=bifamily, ...`` — so the user can compose without
specifying variant and get the canonical cellular treatment per frame.
"""

from __future__ import annotations

from hyperweave.compose.resolver import resolve
from hyperweave.core.models import ComposeSpec


def _variant_in_context(frame_type: str, explicit_variant: str = "") -> str:
    spec = ComposeSpec(
        type=frame_type,
        genome_id="automata",
        title="TEST",
        value="v0.1",
        variant=explicit_variant,
    )
    resolved = resolve(spec)
    return str(resolved.frame_context.get("variant", ""))


def test_badge_default_is_blue_under_cellular() -> None:
    assert _variant_in_context("badge") == "blue"


def test_icon_default_is_blue_under_cellular() -> None:
    assert _variant_in_context("icon") == "blue"


def test_strip_default_is_bifamily_under_cellular() -> None:
    assert _variant_in_context("strip") == "bifamily"


def test_marquee_horizontal_default_is_bifamily() -> None:
    assert _variant_in_context("marquee-horizontal") == "bifamily"


def test_explicit_variant_overrides_default() -> None:
    assert _variant_in_context("strip", explicit_variant="blue") == "blue"
    assert _variant_in_context("badge", explicit_variant="purple") == "purple"
