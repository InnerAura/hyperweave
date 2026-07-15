"""Diagram communication-palette derivation (Semantic Chromatics).

The diagram flow palette is DERIVED from the variant accent, never authored
per variant — a copied ``diagram_flow`` array leaks one variant's hue onto
another (the cobalt-on-cream bug: porcelain's blue rendered on every light
variant because the array was pasted verbatim). Deriving from the accent
makes that leak structurally impossible: the only input is the variant's own
identity.

Slot 0 is the SPINE accent — the variant accent verbatim, so the spine reads
in the variant's own hue on every ground (cream brown, carbon orange, petrol
teal), never a universal blue. Slots 1+ are an in-family TINT RAMP: the accent
HUE and CHROMA are held while the LIGHTNESS steps across a substrate-appropriate
legibility band. A grey accent (noir, anvil) therefore yields a grey ramp — a
monochrome variant stays monochrome — and a chromatic accent yields tints of
its own hue, so categories differentiate by tint, never by a clashing second
hue. Lanes read the ramp as category tints; every other topology binds slot 0
alone (the single spine accent).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hyperweave.core.color import hex_to_rgb, oklch_to_rgb, rgb_to_hex, rgb_to_oklch

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

# Substrate-keyed lightness bands the tint ramp spans (OKLCH L, 0..1). On a
# light ground tints must stay dark enough to read (upper bound ~0.50 keeps
# every slot >= WCAG AA against the pale surface); on a dark ground they must
# stay light enough (lower bound ~0.60). Overridable via engine YAML.
_DEFAULT_BANDS: dict[str, tuple[float, float]] = {"light": (0.24, 0.50), "dark": (0.60, 0.85)}
_DEFAULT_SLOTS = 5


def derive_diagram_flow(genome: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[str]:
    """The variant's flow palette, derived from its accent (see module doc).

    ``genome`` is the variant-MERGED genome dict, so ``accent`` and
    ``substrate_kind`` are the resolved variant's. ``params`` is the engine
    ``flow_derivation`` block (slot count + substrate bands); absent keys fall
    back to module defaults, so a genome that opts into the diagram frame never
    has to author palette geometry — the accent is the whole input.
    """
    params = params or {}
    accent = str(genome.get("accent") or "#888888")
    slots = int(params.get("slots", _DEFAULT_SLOTS))
    bands = params.get("bands") or _DEFAULT_BANDS
    substrate = str(genome.get("substrate_kind") or "light")
    band = bands.get(substrate) or _DEFAULT_BANDS.get(substrate) or _DEFAULT_BANDS["light"]
    lo, hi = float(band[0]), float(band[1])
    _lightness, chroma, hue = rgb_to_oklch(*hex_to_rgb(accent))
    flow = [accent]
    steps = max(slots - 1, 1)
    for i in range(1, slots):
        # Even ramp lo -> hi across the derived slots; chroma + hue held, so a
        # grey accent stays grey and a chromatic one keeps its family.
        t = (i - 1) / (steps - 1) if steps > 1 else 0.0
        r, g, b = oklch_to_rgb(lo + (hi - lo) * t, chroma, hue)
        flow.append(rgb_to_hex(r, g, b))
    return flow
