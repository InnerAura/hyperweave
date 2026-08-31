"""The static projection's motion claims describe the projection, not the source.

``svg-static`` strips every animation; the ``claims`` pass makes the whole
motion claim set follow — a projected file that ships zero animation must not
keep declaring ``paint-ok`` / ``cim-compliant="false"`` /
``data-hw-motion="animated"`` (the underclaim twin of the chart-tier fix).
"""

from __future__ import annotations

import re

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec
from hyperweave.formats import project
from hyperweave.render.css_finish import rendered_animated_properties

_ANIMATED_DIAGRAM = ComposeSpec(
    type="diagram",
    genome_id="primer",
    diagram={
        "topology": "pipeline",
        "title": "Claims",
        "nodes": [{"label": "A"}, {"label": "B", "role": "hero"}, {"label": "C"}],
    },
)


def test_static_projection_rewrites_the_complete_motion_claim_set() -> None:
    live = compose(_ANIMATED_DIAGRAM).svg
    # Precondition: the live source really is the animated paint-ok case.
    assert 'performance="paint-ok"' in live
    assert 'data-hw-motion="animated"' in live

    static = project(live, "svg-static", face="dark").data.decode("utf-8")

    assert "@keyframes" not in static
    assert "<animate" not in static
    assert not rendered_animated_properties(static)

    assert 'data-hw-motion="static"' in static
    assert 'performance="composite-only"' in static
    assert 'cim-compliant="true"' in static
    assert 'performance="paint-ok"' not in static
    assert re.search(r'<hw:environment[^>]*motion="static"', static)
    motion_tag = re.search(r"<hw:motion\b[^>]*>", static)
    assert motion_tag
    for claim in ('vocabulary="static"', 'physics="none"', 'timing="none"', 'stagger-regime="none"'):
        assert claim in motion_tag.group(0), claim
    constraints = re.search(r"<hw:constraints-applied>([^<]*)</hw:constraints-applied>", static)
    assert constraints and "cim-compliant" in constraints.group(1)


def test_static_projection_of_border_motion_badge_reads_static() -> None:
    live = compose(
        ComposeSpec(type="badge", genome_id="brutalist", title="X", value="1", motion="rimrun", regime="permissive")
    ).svg
    assert 'performance="paint-ok"' in live
    static = project(live, "svg-static").data.decode("utf-8")
    assert not rendered_animated_properties(static)
    assert 'performance="composite-only"' in static
    assert 'data-hw-motion="static"' in static
