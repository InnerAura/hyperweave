"""Test-only helpers for constructing bypass state.

These helpers exist ONLY for test fixtures that need to construct
genomes that would fail the production
``validate_genome_against_paradigms`` check (e.g. a minimal genome for a
smoke test that doesn't declare chrome-specific fields).

Production code paths MUST NOT import from this module. Grep
``build_partial_genome_for_testing`` to audit usage.
"""

from __future__ import annotations

from typing import Any


def build_partial_genome_for_testing(**overrides: Any) -> dict[str, Any]:
    """Build a minimal genome dict that bypasses paradigm-requirement checks.

    Returns a plain dict (not a validated ``GenomeSpec``) so the caller
    can feed it into compose paths that accept ``genome_override``
    without tripping :func:`hyperweave.compose.validate_paradigms.validate_genome_against_paradigms`.

    The returned genome is sufficient for :class:`GenomeSpec` Pydantic
    construction (all required fields populated with neutral placeholders)
    but does not declare any chrome-paradigm-specific chromatic fields,
    so tests that route it through a ``chrome`` template will produce
    empty gradients rather than chrome-horizon specimen colors — the
    deliberate safe failure mode.
    """
    defaults: dict[str, Any] = {
        "id": overrides.get("id", "test-partial"),
        "name": overrides.get("name", "Test Partial Genome"),
        "category": overrides.get("category", "dark"),
        "profile": overrides.get("profile", "brutalist"),
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
    return defaults
