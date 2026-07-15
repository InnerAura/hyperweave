"""SurfaceSpec IR + preset expansion + the trap corner.

The two format axes (ground x palette) span four corners; three are presets
(plate/inlay/twin) and the fourth (bare · fixed) is a trap that ships to
nothing. These tests lock the enums, the preset table, the expansion sugar with
its conflict detection, and trap rejection at BOTH the SurfaceSpec and the
ComposeSpec boundary (a raw ComposeSpec built with the axes directly must fail
loud, not just the preset sugar path).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hyperweave.core.models import ComposeSpec
from hyperweave.core.surface_spec import (
    SURFACE_PRESETS,
    Ground,
    PaletteMode,
    SurfaceSpec,
    expand_surface_preset,
    preset_name,
)

# ── the three presets ──────────────────────────────────────────────────────


def test_presets_are_the_three_live_corners() -> None:
    """Exactly plate/inlay/twin; the fourth corner is intentionally absent."""
    assert set(SURFACE_PRESETS) == {"plate", "inlay", "twin"}
    assert SURFACE_PRESETS["plate"] == (Ground.OPAQUE, PaletteMode.FIXED)
    assert SURFACE_PRESETS["inlay"] == (Ground.BARE, PaletteMode.ADAPTIVE)
    assert SURFACE_PRESETS["twin"] == (Ground.OPAQUE, PaletteMode.ADAPTIVE)


@pytest.mark.parametrize("name", ["plate", "inlay", "twin"])
def test_preset_name_round_trips(name: str) -> None:
    ground, palette = SURFACE_PRESETS[name]
    assert preset_name(ground, palette) == name


def test_preset_name_of_trap_is_empty() -> None:
    """The trap corner has no preset name."""
    assert preset_name(Ground.BARE, PaletteMode.FIXED) == ""


# ── SurfaceSpec defaults + trap ─────────────────────────────────────────────


def test_default_surfacespec_is_plate() -> None:
    s = SurfaceSpec()
    assert s.ground is Ground.OPAQUE
    assert s.palette is PaletteMode.FIXED
    assert s.face == ""


def test_surfacespec_rejects_trap() -> None:
    with pytest.raises(ValidationError, match="trap corner"):
        SurfaceSpec(ground=Ground.BARE, palette=PaletteMode.FIXED)


def test_surfacespec_face_pattern() -> None:
    assert SurfaceSpec(palette=PaletteMode.ADAPTIVE, face="light").face == "light"
    with pytest.raises(ValidationError):
        SurfaceSpec(palette=PaletteMode.ADAPTIVE, face="sideways")


def test_surfacespec_is_frozen() -> None:
    s = SurfaceSpec()
    with pytest.raises(ValidationError):
        s.ground = Ground.BARE  # type: ignore[misc]


# ── expand_surface_preset ───────────────────────────────────────────────────


def test_expand_empty_is_plate() -> None:
    s = expand_surface_preset("", "", "")
    assert (s.ground, s.palette) == (Ground.OPAQUE, PaletteMode.FIXED)


@pytest.mark.parametrize(
    ("name", "ground", "palette"),
    [
        ("plate", Ground.OPAQUE, PaletteMode.FIXED),
        ("inlay", Ground.BARE, PaletteMode.ADAPTIVE),
        ("twin", Ground.OPAQUE, PaletteMode.ADAPTIVE),
    ],
)
def test_expand_preset_name(name: str, ground: Ground, palette: PaletteMode) -> None:
    s = expand_surface_preset(name, "", "")
    assert (s.ground, s.palette) == (ground, palette)


def test_expand_explicit_axes() -> None:
    s = expand_surface_preset("", "bare", "adaptive")
    assert (s.ground, s.palette) == (Ground.BARE, PaletteMode.ADAPTIVE)


def test_expand_unknown_preset_raises() -> None:
    with pytest.raises(ValueError, match="unknown surface preset"):
        expand_surface_preset("frosted", "", "")


def test_expand_conflict_ground_raises() -> None:
    """surface=twin (opaque) with ground=bare is a conflict."""
    with pytest.raises(ValueError, match="implies ground"):
        expand_surface_preset("twin", "bare", "")


def test_expand_conflict_palette_raises() -> None:
    """surface=plate (fixed) with palette=adaptive is a conflict."""
    with pytest.raises(ValueError, match="implies palette"):
        expand_surface_preset("plate", "", "adaptive")


def test_expand_preset_with_matching_axis_ok() -> None:
    """A redundant-but-consistent axis is allowed."""
    s = expand_surface_preset("inlay", "bare", "adaptive")
    assert (s.ground, s.palette) == (Ground.BARE, PaletteMode.ADAPTIVE)


def test_expand_trap_axes_rejected() -> None:
    with pytest.raises(ValueError, match="trap corner"):
        expand_surface_preset("", "bare", "fixed")


# ── ComposeSpec surface props + trap ────────────────────────────────────────


def test_composespec_surface_props_default_empty() -> None:
    cs = ComposeSpec(type="matrix", genome_id="primer")
    assert cs.ground == ""
    assert cs.palette == ""
    assert cs.surface_face == ""


def test_composespec_rejects_trap_axes() -> None:
    """The trap is caught at ComposeSpec too, not just via the preset sugar."""
    with pytest.raises(ValidationError, match="trap corner"):
        ComposeSpec(type="matrix", genome_id="primer", ground="bare", palette="fixed")


@pytest.mark.parametrize(
    ("ground", "palette"),
    [("opaque", "fixed"), ("bare", "adaptive"), ("opaque", "adaptive"), ("", "")],
)
def test_composespec_accepts_valid_axis_combos(ground: str, palette: str) -> None:
    cs = ComposeSpec(type="matrix", genome_id="primer", ground=ground, palette=palette)
    assert cs.ground == ground
    assert cs.palette == palette


def test_composespec_surface_face_pattern() -> None:
    cs = ComposeSpec(type="matrix", genome_id="primer", palette="adaptive", surface_face="dark")
    assert cs.surface_face == "dark"
    with pytest.raises(ValidationError):
        ComposeSpec(type="matrix", genome_id="primer", surface_face="upside-down")


# ── The face exemption: bare · fixed WITH a face is theme-committed ──────────


def test_bare_fixed_with_face_is_legal() -> None:
    """The terminal-inlay face: an explicit face commits the scheme for a
    known host ground, so the trap's theme-blind rationale does not apply."""
    s = SurfaceSpec(ground=Ground.BARE, palette=PaletteMode.FIXED, face="dark")
    assert s.face == "dark"


def test_bare_fixed_without_face_still_traps() -> None:
    with pytest.raises(ValueError, match="trap corner"):
        SurfaceSpec(ground=Ground.BARE, palette=PaletteMode.FIXED)


def test_compose_spec_face_exemption_mirrors() -> None:
    """ComposeSpec's twin validator carries the same exemption (raw-axes
    callers bypass the preset sugar but not the trap)."""
    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(type="badge", genome_id="primer", ground="bare", palette="fixed", surface_face="light")
    assert spec.surface_face == "light"
    with pytest.raises(ValueError, match="trap corner"):
        ComposeSpec(type="badge", genome_id="primer", ground="bare", palette="fixed")
