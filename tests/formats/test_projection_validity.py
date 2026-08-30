"""Every projection parses before its surface reports success (Invariant 14's
projection clause).

The postcondition lives once in ``project()``: the composed source is validated
as a precondition, every configured svg-static pass is validated with
``detail.pass`` naming the offender, and png/webp rasterize only the validated
intermediate. A failure is a typed engine fault (``PROJECTION_INVALID``, 500) —
never a written file, never a zero exit, never a caller error.

The corpus pin composes every bundled diagram preset and projects it — the
acceptance set that started at 239 malformed projections across the local
corpus and must stay at zero. Parse is asserted, never bytes (the entropy pack
makes byte counts a property of the run, not the artifact).
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from hyperweave.compose.engine import compose
from hyperweave.config.loader import load_diagram_presets
from hyperweave.core.errors import HwError, HwErrorCode
from hyperweave.core.models import ComposeSpec
from hyperweave.formats import FormatId, project


def _assert_parses(text: str) -> None:
    ET.fromstring(text)


class TestPostconditionAttribution:
    def test_malformed_source_names_source(self) -> None:
        with pytest.raises(HwError) as exc:
            project("<svg><unclosed", FormatId.SVG)
        assert exc.value.code is HwErrorCode.PROJECTION_INVALID
        assert exc.value.detail["pass"] == "source"
        assert exc.value.http_status == 500

    def test_broken_pass_is_named(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Seed a corrupting pass: attribution must name it, not report a generic
        # parse crash and not blame the caller.
        from hyperweave.formats import static

        monkeypatch.setitem(static._PASSES, "vars", lambda s: s + "<broken")
        svg = compose(ComposeSpec(type="badge", title="X", value="Y")).svg
        with pytest.raises(HwError) as exc:
            project(svg, FormatId.SVG_STATIC)
        assert exc.value.code is HwErrorCode.PROJECTION_INVALID
        assert exc.value.detail["pass"] == "vars"

    def test_malformed_source_never_projects_static(self) -> None:
        with pytest.raises(HwError) as exc:
            project("<svg><g style=", FormatId.SVG_STATIC)
        assert exc.value.detail["pass"] == "source"


class TestPresetCorpusPin:
    """Anything that composes clean projects clean — the solver ↔ projection
    cross-plane invariant, pinned across every bundled preset."""

    @pytest.mark.parametrize("preset", sorted(load_diagram_presets()))
    def test_every_bundled_preset_projects_parseable_static(self, preset: str) -> None:
        spec = load_diagram_presets()[preset]
        svg = compose(
            ComposeSpec(type="diagram", genome_id="primer", ground="opaque", palette="fixed", diagram=spec)
        ).svg
        _assert_parses(svg)  # Invariant 14, composed source
        projection = project(svg, FormatId.SVG_STATIC)
        static = projection.data.decode("utf-8")
        _assert_parses(static)
        assert "var(--" not in static
        assert "@keyframes" not in static
        assert "<animate" not in static

    def test_inline_animation_declarations_are_gone_not_just_style_blocks(self) -> None:
        # The check a <style>-only fix would fail: engine output carries inline
        # animation shorthand on elements; a static projection ships none, in
        # style attributes and <style> blocks alike.
        import re

        spec = load_diagram_presets()["loop-retry-budget"]
        svg = compose(
            ComposeSpec(type="diagram", genome_id="primer", ground="opaque", palette="fixed", diagram=spec)
        ).svg
        assert re.search(r'style="[^"]*animation', svg), "premise: live artifact animates inline"
        static = project(svg, FormatId.SVG_STATIC).data.decode("utf-8")
        decl = re.compile(r"(?<![-\w])animation(?:-[a-z]+)*\s*:")
        assert not re.search(r'style="[^"]*animation[^"]*"', static)
        assert not decl.search(static.split("<style")[0])
        for style_body in re.findall(r"<style\b[^>]*>(.*?)</style>", static, re.DOTALL):
            body = re.sub(r"/\*.*?\*/", "", style_body, flags=re.DOTALL)
            assert not decl.search(body), "an animation declaration survived inside a <style> body"
