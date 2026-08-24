"""Spec construction and bytes-to-disk, shared by every gallery generator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec

REPO = Path(__file__).resolve().parents[2]
OUTPUTS = REPO / "outputs"


# Galleries render with CDN fonts. An embedded woff2 subset is 15-35 KB per
# artifact and roughly HALVES to DOUBLES the file — across ~820 gallery
# artifacts that is tens of megabytes of base64 whose only job is offline
# self-containment, which a local review gallery does not need. The committed
# specimens under assets/examples/ keep `embed`: those are what other people's
# READMEs load, and they must carry their own type.
GALLERY_FONT_MODE = "cdn"


def spec(
    frame_type: str,
    genome: str,
    title: str = "",
    value: str = "",
    state: str = "active",
    glyph: str = "",
    **kwargs: Any,
) -> ComposeSpec:
    """A ComposeSpec from the five fields most artifacts vary, plus the rest.

    The positional five are the ones a gallery declaration actually reads as
    content; everything else (variant, size, shape, divider_variant, surface
    axes, payloads) arrives by keyword under its own ComposeSpec field name —
    no second vocabulary to learn or keep in sync.

    Font delivery defaults to :data:`GALLERY_FONT_MODE`; pass ``font_mode``
    explicitly to override for one artifact.
    """
    kwargs.setdefault("font_mode", GALLERY_FONT_MODE)
    return ComposeSpec(type=frame_type, genome_id=genome, title=title, value=value, state=state, glyph=glyph, **kwargs)


def render(compose_spec: ComposeSpec) -> str:
    """The artifact's SVG."""
    return compose(compose_spec).svg


def write(path: Path, svg: str) -> None:
    """Write ``svg``, creating parents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg)
