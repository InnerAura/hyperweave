"""Surface Modes IR — the two format axes and the three named presets.

A frame meets its host surface one of three ways, spanned by two orthogonal
axes: ``ground`` (does the artifact paint its own background?) and ``palette``
(one baked scheme, or a light/dark pair via ``prefers-color-scheme``?). Their
live combinations get one collective name — ``surface`` — with three presets:

    plate — opaque · fixed    — carries its own ground, ignores reader theme.
    inlay — bare   · adaptive — no ground, borrows the host, re-inks to theme.
    twin  — opaque · adaptive — a light face and a dark face; contained card.

The fourth corner (bare · fixed) is a trap: transparent but theme-blind, so ink
tuned for one scheme lands on a host that may be the other. It ships to nothing
and the model validator rejects it.

This module is a leaf: it imports only ``core.base`` and stdlib so
``core/matrix.py`` and ``core/diagram.py`` can nest ``SurfaceSpec`` on their
specs without an import cycle. The visual-projection math (chroma classifier,
token flipping, re-grounding, adaptive CSS) lives in ``compose/surface_modes.py``
— this module is pure schema.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from hyperweave.core.base import FrozenModel


class Ground(StrEnum):
    """Does the artifact paint its own background?

    ``opaque`` carries a ground; ``bare`` is transparent and borrows the host
    surface (the projection drops the single backdrop element).
    """

    OPAQUE = "opaque"
    BARE = "bare"


class PaletteMode(StrEnum):
    """One baked palette, or a light/dark pair driven by the reader's theme?

    ``fixed`` bakes one scheme (identical everywhere). ``adaptive`` emits a
    near scheme plus a ``@media (prefers-color-scheme)`` far scheme.
    """

    FIXED = "fixed"
    ADAPTIVE = "adaptive"


# The three shippable presets, each an (ground, palette) pair. The fourth corner
# (bare · fixed) is intentionally ABSENT — it is the trap. Used both to expand a
# ``surface=<name>`` sugar into axes and to name the axes back to a preset.
SURFACE_PRESETS: dict[str, tuple[Ground, PaletteMode]] = {
    "plate": (Ground.OPAQUE, PaletteMode.FIXED),
    "inlay": (Ground.BARE, PaletteMode.ADAPTIVE),
    "twin": (Ground.OPAQUE, PaletteMode.ADAPTIVE),
}


class SurfaceSpec(FrozenModel):
    """Resolved surface identity carried in a frame IR (matrix/diagram).

    Additive on the frame specs and excluded from serialization when it equals
    the plate default, so pre-existing payloads stay byte-identical. When a
    non-plate surface serializes into the payload, the artifact's content
    address changes — plate/inlay/twin of one table are distinct artifacts by
    construction, and a twin's two faces each carry their ``face`` (self-
    describing beats dedup).
    """

    ground: Ground = Field(default=Ground.OPAQUE, description="opaque (own ground) | bare (borrow host)")
    palette: PaletteMode = Field(default=PaletteMode.FIXED, description="fixed (one scheme) | adaptive (light/dark)")
    face: str = Field(
        default="",
        description=(
            "Which face of an adaptive twin this artifact is: '' (adaptive, both "
            "faces in one SVG), 'light', or 'dark' (a single baked face for a "
            "<picture> source). Faces are plain plates and rasterize fine."
        ),
        pattern="^(|light|dark)$",
    )

    @model_validator(mode="after")
    def _reject_trap(self) -> SurfaceSpec:
        """bare · fixed with NO face is the trap corner — transparent but
        theme-blind. With an explicit ``face`` it is theme-COMMITTED, not
        blind: the caller names the scheme for a known host ground — the
        terminal-inlay face (inks composited over the terminal), and the
        raster leg of an inlay <picture> pair."""
        if self.ground is Ground.BARE and self.palette is PaletteMode.FIXED and not self.face:
            raise ValueError(
                "surface ground=bare with palette=fixed is the trap corner "
                "(transparent but theme-blind); choose a preset: plate "
                "(opaque·fixed), inlay (bare·adaptive), twin (opaque·adaptive) "
                "— or commit to a scheme with face=light|dark (the bare inlay face)"
            )
        return self


def expand_surface_preset(surface: str, ground: str, palette: str) -> SurfaceSpec:
    """Resolve the ``surface`` sugar and/or explicit axes into a SurfaceSpec.

    ``surface=<name>`` (plate/inlay/twin) expands to its axes. Explicit
    ``ground``/``palette`` may be supplied instead; supplying both a preset name
    AND an axis that contradicts it is a conflict (raises ``ValueError``). Empty
    everywhere resolves to plate (the opaque·fixed default). The trap corner is
    rejected by the SurfaceSpec validator.
    """
    name = (surface or "").strip().lower()
    g_raw = (ground or "").strip().lower()
    p_raw = (palette or "").strip().lower()

    if name:
        if name not in SURFACE_PRESETS:
            raise ValueError(f"unknown surface preset {name!r}; choose from {sorted(SURFACE_PRESETS)}")
        preset_ground, preset_palette = SURFACE_PRESETS[name]
        if g_raw and g_raw != preset_ground.value:
            raise ValueError(f"surface={name!r} implies ground={preset_ground.value!r}, but ground={g_raw!r} was given")
        if p_raw and p_raw != preset_palette.value:
            raise ValueError(
                f"surface={name!r} implies palette={preset_palette.value!r}, but palette={p_raw!r} was given"
            )
        return SurfaceSpec(ground=preset_ground, palette=preset_palette)

    resolved_ground = Ground(g_raw) if g_raw else Ground.OPAQUE
    resolved_palette = PaletteMode(p_raw) if p_raw else PaletteMode.FIXED
    return SurfaceSpec(ground=resolved_ground, palette=resolved_palette)


def preset_name(ground: Ground, palette: PaletteMode) -> str:
    """Name an (ground, palette) pair back to its preset slug, or '' for the trap."""
    for name, (g, p) in SURFACE_PRESETS.items():
        if g is ground and p is palette:
            return name
    return ""
