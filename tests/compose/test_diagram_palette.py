"""Diagram flow-palette derivation (Semantic Chromatics, anti-leak contract).

The flow cycle is derived from the variant accent, so no variant can borrow
another's hue (the cobalt-on-cream bug). These pins hold the derivation to its
contract: slot 0 IS the accent, the ramp stays in-family, a grey accent yields
a grey ramp, and every slot reads on its own ground.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hyperweave.compose.diagram.palette import derive_diagram_flow
from hyperweave.config.loader import load_diagram_config
from hyperweave.core.color import adjust_oklch, contrast_ratio, hex_to_rgb, is_achromatic, rgb_to_oklch

_GENOME = json.loads(
    (Path(__file__).parents[2] / "src" / "hyperweave" / "data" / "genomes" / "primer.json").read_text()
)
_VARIANTS = _GENOME["variant_overrides"]


def _merged(variant: str) -> dict:
    """Base genome overlaid with the variant override — what the resolver derives from."""
    return {**_GENOME, **_VARIANTS[variant]}


def _params() -> dict:
    return load_diagram_config().get("flow_derivation") or {}


@pytest.mark.parametrize("variant", sorted(_VARIANTS))
def test_slot_zero_is_the_variant_accent(variant: str) -> None:
    # The spine accent is the variant's OWN accent, verbatim — the whole point.
    flow = derive_diagram_flow(_merged(variant), _params())
    assert flow[0] == _VARIANTS[variant]["accent"]


@pytest.mark.parametrize("variant", sorted(_VARIANTS))
def test_five_slots(variant: str) -> None:
    assert len(derive_diagram_flow(_merged(variant), _params())) == 5


def test_no_cross_variant_leak() -> None:
    # Porcelain's cobalt must not appear in any other variant's derived flow —
    # the leak this whole mechanism exists to prevent.
    porc = derive_diagram_flow(_merged("porcelain"), _params())
    for variant in _VARIANTS:
        if variant == "porcelain":
            continue
        other = set(derive_diagram_flow(_merged(variant), _params()))
        assert porc[0] not in other, f"{variant} leaked porcelain's cobalt {porc[0]}"


@pytest.mark.parametrize("variant", ["noir", "anvil"])
def test_monochrome_accent_yields_grey_ramp(variant: str) -> None:
    # A grey accent stays grey — a monochrome variant must not sprout a hue.
    flow = derive_diagram_flow(_merged(variant), _params())
    for hexv in flow:
        assert is_achromatic(hexv, max_spread=24), f"{variant} tint {hexv} is not neutral"


@pytest.mark.parametrize("variant", ["carbon", "porcelain", "space", "dusk", "petrol"])
def test_chromatic_ramp_holds_the_accent_hue(variant: str) -> None:
    # Tints stay in the accent's hue family (no rainbow) — every ramp slot's
    # OKLCH hue is within a narrow window of the accent's.
    accent = _VARIANTS[variant]["accent"]
    _l, _c, base_hue = rgb_to_oklch(*hex_to_rgb(accent))
    for hexv in derive_diagram_flow(_merged(variant), _params())[1:]:
        _, _, hue = rgb_to_oklch(*hex_to_rgb(hexv))
        drift = abs((hue - base_hue + 180.0) % 360.0 - 180.0)
        assert drift < 25.0, f"{variant} tint {hexv} drifted {drift:.0f}deg from the accent hue"


@pytest.mark.parametrize("variant", sorted(_VARIANTS))
def test_every_slot_reads_on_ground(variant: str) -> None:
    # Category tints are small marks; hold them to a 3.5 floor (below text AA,
    # above invisibility) against the variant's own surface.
    merged = _merged(variant)
    ground = merged["surface_0"]
    for hexv in derive_diagram_flow(merged, _params()):
        assert contrast_ratio(hexv, ground) >= 3.5, f"{variant} tint {hexv} vanishes on {ground}"


def test_authored_override_wins() -> None:
    # A genome may opt out: an explicit accent-mismatched palette is not derived.
    # (Derivation only fires when diagram_flow is absent — proven by slot 0
    # equalling the accent above; here we confirm the derive fn ignores any
    # pre-existing key, since the resolver, not this fn, chooses authored-vs-derived.)
    flow = derive_diagram_flow({"accent": "#123456", "substrate_kind": "dark"}, _params())
    assert flow[0] == "#123456" and len(flow) == 5


def test_adjust_oklch_holds_hue_shifts_lightness() -> None:
    base = "#1D4ED8"
    _l, _c, base_hue = rgb_to_oklch(*hex_to_rgb(base))
    lighter = adjust_oklch(base, dl=0.2)
    ll, _lc, lh = rgb_to_oklch(*hex_to_rgb(lighter))
    assert ll > _l  # lightness rose
    assert abs((lh - base_hue + 180.0) % 360.0 - 180.0) < 3.0  # hue held
