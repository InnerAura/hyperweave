"""Variant default resolution — v0.3.0 compositional tones + pairing grammar.

An empty ``ComposeSpec.variant`` resolves per-frame via the paradigm's
``frame_variant_defaults`` map. Cellular paradigm declares every frame's
default as ``teal`` (the canonical solo flagship). Pairing is opt-in via
``ComposeSpec.pair`` — ``?variant=teal&pair=violet`` reproduces the prior
bifamily aesthetic on strip/divider while leaving badge/stats/chart/marquee
to render solo teal regardless of pair.
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


def test_badge_default_is_teal_under_cellular() -> None:
    assert _variant_in_context("badge") == "teal"


def test_icon_default_is_teal_under_cellular() -> None:
    assert _variant_in_context("icon") == "teal"


def test_strip_default_is_teal_under_cellular() -> None:
    assert _variant_in_context("strip") == "teal"


def test_marquee_horizontal_default_is_teal() -> None:
    assert _variant_in_context("marquee-horizontal") == "teal"


def test_explicit_variant_overrides_default() -> None:
    assert _variant_in_context("strip", explicit_variant="teal") == "teal"
    assert _variant_in_context("badge", explicit_variant="violet") == "violet"
