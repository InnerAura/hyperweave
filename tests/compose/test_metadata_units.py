"""Metadata coordinate spaces and the rhythm token are declared honestly.

Two truth defects this file pins closed:

- ``hw:spec size`` is the CSS-px render size while ``hw:regions`` bboxes live
  in user (viewBox) units; on a display-scaled frame (diagram) the two spaces
  differ by the display factor. Both sides now declare their space, and the
  regions sidecar carries the viewBox so the scale is recoverable.
- ``duration-base`` implied the artifact's animation clocks derived from it;
  they don't (template literals / diagram-derived). The attribute is now
  ``rhythm-base`` — the genome rhythm token, which is what it always carried.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

from hyperweave.compose.engine import compose
from hyperweave.config.loader import get_loader
from hyperweave.core.models import ComposeSpec

_HW = "{https://hyperweave.app/hw/v1.0}"

_DIAGRAM = ComposeSpec(
    type="diagram",
    genome_id="primer",
    diagram={
        "topology": "pipeline",
        "title": "Units",
        "nodes": [{"label": "A"}, {"label": "B", "role": "hero"}, {"label": "C"}],
    },
)


def _metadata(svg: str) -> ET.Element:
    root = ET.fromstring(svg)
    meta = root.find("{http://www.w3.org/2000/svg}metadata")
    assert meta is not None
    return meta


def test_spec_size_declares_px_and_matches_render_size() -> None:
    svg = compose(_DIAGRAM).svg
    root = ET.fromstring(svg)
    spec = _metadata(svg).find(f"{_HW}artifact/{_HW}spec")
    assert spec is not None
    assert spec.get("size-units") == "px"
    assert spec.get("size") == f"{root.get('width')}x{root.get('height')}"


def test_regions_declare_user_units_and_the_viewbox() -> None:
    svg = compose(_DIAGRAM).svg
    root = ET.fromstring(svg)
    regions = _metadata(svg).find(f"{_HW}regions")
    assert regions is not None
    assert regions.get("units") == "user"
    assert regions.get("viewbox") == root.get("viewBox")
    # A scaled diagram's render size differs from its user space — exactly the
    # ambiguity the declarations resolve.
    _, _, vb_w, vb_h = (float(v) for v in str(root.get("viewBox")).split())
    for region in json.loads(regions.text or "[]"):
        x, y, w, h = region["bbox"]
        assert 0 <= x <= vb_w and 0 <= y <= vb_h, f"{region['id']}: bbox outside user space"
        assert x + w <= vb_w + 1 and y + h <= vb_h + 1


def test_rhythm_base_replaces_duration_base() -> None:
    svg = compose(ComposeSpec(type="badge", genome_id="primer", title="X", value="1")).svg
    assert "duration-base" not in svg
    motion = _metadata(svg).find(f"{_HW}aesthetic/{_HW}motion")
    assert motion is not None
    assert motion.get("rhythm-base") == get_loader().genomes["primer"]["rhythm_base"]


def test_every_frame_declares_size_units() -> None:
    """The declaration is universal, not diagram-only."""
    for frame, kwargs in (("badge", {"title": "X", "value": "1"}), ("icon", {})):
        svg = compose(ComposeSpec(type=frame, genome_id="primer", **kwargs)).svg
        assert re.search(r'<hw:spec size="\d+x\d+" size-units="px"', svg), frame
