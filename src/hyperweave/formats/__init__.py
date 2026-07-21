"""Output formats — deterministic projections of the ONE composed SVG artifact.

A composed artifact is a single SVG. Every other format is a pure projection of
it: ``svg-static`` flattens ``var(--dna-*)`` to hex and strips motion;
``png``/``webp`` rasterize that static projection. There is no second render
system — the pixels always derive from the same bytes.

Public API:

- :class:`FormatId` — the closed format set (svg | svg-static | png | webp | gif | ansi).
- :class:`Projection` — bytes + media type + extension.
- :func:`project` — svg → a Projection in the requested format.
- :func:`raster_available` — whether png/webp can be produced (the ``[raster]`` extra).

``gif`` is a known id with no path today (raises ``FORMAT_UNAVAILABLE``): resvg
has no time-sampled animation capture, and the browserless engines that do
(takumi) take a JSX/HTML tree, not an arbitrary SVG.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from hyperweave.core.errors import HwError, HwErrorCode

# Fix text shared by the adaptive-guard on every flatten/raster path (WC's guard,
# relocated here). An adaptive artifact's far face lives entirely in the scoped
# --dna-* vars, so flattening bakes one scheme and the flip is gone.
_ADAPTIVE_FIX = (
    "use surface=plate, faces for a <picture> pair, or commit to one scheme with "
    "--face dark|light (an inlay face is bare + theme-committed and rasterizes with alpha)"
)


class FormatId(StrEnum):
    """The closed output-format set."""

    SVG = "svg"
    SVG_STATIC = "svg-static"
    PNG = "png"
    WEBP = "webp"
    GIF = "gif"
    ANSI = "ansi"


# Formats whose bytes are SVG text vs raster.
_SVG_FORMATS = {FormatId.SVG, FormatId.SVG_STATIC}
_RASTER_FORMATS = {FormatId.PNG, FormatId.WEBP}
# Formats that flatten var()→hex (the static passes) — an adaptive artifact
# cannot survive these, so the guard rejects them.
_FLATTENING_FORMATS = {FormatId.SVG_STATIC, FormatId.PNG, FormatId.WEBP}

_MEDIA_TYPE: dict[FormatId, str] = {
    FormatId.ANSI: "text/plain; charset=utf-8",
    FormatId.SVG: "image/svg+xml",
    FormatId.SVG_STATIC: "image/svg+xml",
    FormatId.PNG: "image/png",
    FormatId.WEBP: "image/webp",
    FormatId.GIF: "image/gif",
}

# Filename suffix per format (the derived-store key + the /v1/a/{digest}.{ext} URL).
_EXT: dict[FormatId, str] = {
    FormatId.ANSI: "txt",
    FormatId.SVG: "svg",
    FormatId.SVG_STATIC: "static.svg",
    FormatId.PNG: "png",
    FormatId.WEBP: "webp",
    FormatId.GIF: "gif",
}


@dataclass(frozen=True)
class Projection:
    """A rendered format: the bytes, its media type, and its filename extension.

    ``diagnostics`` declares what a flattening projection dropped (animated
    elements stripped, motion-only elements removed) — report-only counts,
    never part of the artifact bytes."""

    data: bytes
    media_type: str
    ext: str
    diagnostics: dict[str, int] = field(default_factory=dict)

    @property
    def is_text(self) -> bool:
        """True when the bytes are text for a terminal (svg/ansi), not raster."""
        return self.media_type.startswith("text/") or self.media_type == "image/svg+xml"


def raster_available() -> bool:
    """True when png/webp can be produced (the ``[raster]`` extra is installed)."""
    from hyperweave.formats import raster

    return raster.available()


def is_flattening(fmt: FormatId | str) -> bool:
    """True when ``fmt`` bakes vars to hex (svg-static/png/webp) — an adaptive
    artifact cannot survive it, so callers may commit a DEFAULTED adaptive
    surface to its plate before projecting."""
    fid = fmt if isinstance(fmt, FormatId) else parse_format(fmt)
    return fid in _FLATTENING_FORMATS


def parse_format(value: str) -> FormatId:
    """Coerce a format string to a :class:`FormatId`, raising SPEC_INVALID."""
    try:
        return FormatId(value)
    except ValueError as exc:
        raise HwError(
            HwErrorCode.SPEC_INVALID,
            f"unknown format {value!r}",
            fix=f"choose from {[f.value for f in FormatId]}",
        ) from exc


def _is_adaptive(svg: str, *, is_face: bool) -> bool:
    """True when ``svg`` is an adaptive artifact that must not be flattened.

    Detection reads the artifact's own ``data-hw-adapt="adaptive"`` root attribute
    (emitted by the adaptive template path). A face render carries ``data-hw-face``
    instead and is a plain plate, so it is exempt — the ``is_face`` flag lets a
    caller that knows the render is a face skip the check even before the attribute
    lands. This is the honest, self-describing seam: the guard reads the artifact,
    not a side channel.
    """
    if is_face:
        return False
    return 'data-hw-adapt="adaptive"' in svg


def project(svg: str, fmt: FormatId | str, *, max_width: int | None = None, is_face: bool = False) -> Projection:
    """Project a composed SVG into ``fmt``.

    ``svg`` (live), ``svg-static`` (flattened + de-animated), ``png``/``webp``
    (rasterized from the static projection). An adaptive-palette source is
    rejected for every flattening format unless it is a face render. ``gif``
    always raises ``FORMAT_UNAVAILABLE``; png/webp raise it when the ``[raster]``
    extra is absent.
    """
    fid = fmt if isinstance(fmt, FormatId) else parse_format(fmt)

    if fid is FormatId.GIF:
        raise HwError(
            HwErrorCode.FORMAT_UNAVAILABLE,
            "gif output is not available",
            fix="use png for a static image or svg for motion",
        )

    if fid in _FLATTENING_FORMATS and _is_adaptive(svg, is_face=is_face):
        raise HwError(
            HwErrorCode.SPEC_INVALID,
            f"an adaptive-palette artifact cannot be flattened for format={fid.value!r}",
            fix=_ADAPTIVE_FIX,
        )

    if fid is FormatId.ANSI:
        # §12.2: the structural character-grid projection — derived from the
        # artifact's own region sidecar + payload, never from pixels.
        from hyperweave.formats.ansi import project_ansi

        try:
            grid = project_ansi(svg)
        except ValueError as exc:
            raise HwError(
                HwErrorCode.FORMAT_UNAVAILABLE,
                str(exc),
                fix="ansi projects the diagram frame's region tree; compose a diagram artifact",
            ) from exc
        return Projection(grid.encode("utf-8"), _MEDIA_TYPE[fid], _EXT[fid])

    if fid is FormatId.SVG:
        return Projection(svg.encode("utf-8"), _MEDIA_TYPE[fid], _EXT[fid])

    if fid is FormatId.SVG_STATIC:
        static, counts = _static_svg_counted(svg)
        return Projection(static.encode("utf-8"), _MEDIA_TYPE[fid], _EXT[fid], diagnostics=counts)

    # png / webp — rasterize the static projection (resvg cannot resolve var()).
    from hyperweave.formats import raster

    if not raster.available():
        raise HwError(
            HwErrorCode.FORMAT_UNAVAILABLE,
            f"{fid.value} output requires the raster extra",
            fix="install hyperweave[raster]",
        )
    static, counts = _static_svg_counted(svg)
    data = raster.rasterize(static, fid.value, max_width=max_width)
    return Projection(data, _MEDIA_TYPE[fid], _EXT[fid], diagnostics=counts)


def _static_svg_counted(svg: str) -> tuple[str, dict[str, int]]:
    """Apply the ``svg-static`` pass pipeline (vars→hex, strip motion) + counts."""
    from hyperweave.config.loader import load_output_format_pipelines
    from hyperweave.formats.static import run_passes_counted

    passes = load_output_format_pipelines().get(FormatId.SVG_STATIC.value, ["vars", "noanim"])
    return run_passes_counted(svg, passes)


def format_ext(fmt: FormatId) -> str:
    """Filename extension for a format (the derived-store key suffix)."""
    return _EXT[fmt]


__all__ = [
    "FormatId",
    "Projection",
    "format_ext",
    "is_flattening",
    "parse_format",
    "project",
    "raster_available",
]
