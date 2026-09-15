"""Test-only helpers: inline genomes and the rendered text layer.

``build_minimal_genome_for_testing`` emits a COMPLETE minimal genome — one
that passes the full custom-genome boundary (GenomeSpec grammar, the
cross-validation battery, the profile contract) exactly like a registry
genome. There is no bypass shape anymore: since the P0 injection fix,
``ComposeSpec.genome_override`` validates every inline genome, so a partial
dict fails closed on every surface.

Production code paths MUST NOT import from this module. Grep
``build_minimal_genome_for_testing`` to audit usage.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

_CHROMATIC_PREFIXES = ("#", "rgba(", "rgb(", "linear-gradient", "radial-gradient")


def build_minimal_genome_for_testing(**overrides: Any) -> dict[str, Any]:
    """Build the smallest genome dict that survives the override boundary.

    All required GenomeSpec fields carry neutral placeholders that clear the
    flat profile contract's WCAG pairs; ``roles`` is auto-derived from the
    final chromatic values so ``validate_genome_roles`` /
    ``validate_genome_chromatic_coverage`` hold whatever colors a caller
    overrides in. No chrome-paradigm chromatic fields are declared, so tests
    routing it through a ``chrome`` template still get empty gradients — the
    deliberate safe failure mode.
    """
    defaults: dict[str, Any] = {
        "id": overrides.get("id", "test-partial"),
        "name": overrides.get("name", "Test Partial Genome"),
        "category": overrides.get("category", "dark"),
        "profile": overrides.get("profile", "flat"),
        "surface_0": "#1a1a1a",
        "surface_1": "#222222",
        "surface_2": "#0a0a0a",
        "ink": "#eeeeee",
        "ink_secondary": "#aaaaaa",
        "ink_on_accent": "#111111",
        "accent": "#888888",
        "accent_complement": "#999999",
        "accent_signal": "#22C55E",
        "accent_warning": "#F59E0B",
        "accent_error": "#EF4444",
        "stroke": "#444444",
        "shadow_color": "#000000",
        "shadow_opacity": "0.20",
        "glow": "0px",
        "corner": "0",
        "rhythm_base": "2.618s",
        "density": "0.5",
        "compatible_motions": ["static"],
        "paradigms": {},
    }
    defaults.update(overrides)
    if "roles" not in defaults:
        chromatic = [
            key
            for key, value in defaults.items()
            if key != "roles" and isinstance(value, str) and value.startswith(_CHROMATIC_PREFIXES)
        ]
        defaults["roles"] = {"core": chromatic}
    return defaults


def rendered_text(svg: str) -> str:
    """Every string the SVG paints, joined — the text layer only.

    Provenance timestamps, digests, and base64 font bytes are volatile and can
    spell any digit run; assertions about what a reader sees must look here.
    """
    ns = "{http://www.w3.org/2000/svg}"
    return "\n".join(el.text for el in ET.fromstring(svg).iter() if el.tag in (f"{ns}text", f"{ns}tspan") and el.text)
