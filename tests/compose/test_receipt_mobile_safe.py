"""BUG-004 — the receipt must not blur on mobile.

A filter on the full text-bearing card group forces mobile Safari/Chrome to
rasterize the whole subtree (text included) into a resolution-capped offscreen
buffer — the uniform blur. The lift shadow must be cast from a separate
silhouette rect, leaving the content group unfiltered. Principle: never apply a
filter to a group containing text/sharp geometry.
"""

from __future__ import annotations

import re

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec

from .test_receipt_primer import SPECIMEN_PAYLOAD


def _light_receipt() -> str:
    # porcelain is a light-substrate primer variant — where the lift shadow renders
    return compose(
        ComposeSpec(type="receipt", genome_id="primer", variant="porcelain", telemetry_data=SPECIMEN_PAYLOAD)
    ).svg


def test_lift_filter_is_on_a_lone_rect_not_a_group() -> None:
    svg = _light_receipt()
    # the lift shadow still renders (the card is lifted)
    assert "-lift)" in svg
    # the element carrying the lift filter is a <rect>, never a <g>
    m = re.search(r"<(\w+)[^>]*filter=\"url\(#[^)]*-lift\)\"", svg)
    assert m is not None and m.group(1) == "rect"
    assert re.search(r"<g[^>]*filter=\"url\(#[^)]*-lift\)\"", svg) is None


def test_receipt_uses_no_subtree_rasterizing_filters() -> None:
    svg = _light_receipt()
    # blur/specular over a small card is the mobile-raster trigger — drop-shadow only
    assert "feGaussianBlur" not in svg
    assert "feSpecularLighting" not in svg
