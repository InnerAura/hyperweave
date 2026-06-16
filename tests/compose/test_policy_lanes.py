"""End-to-end policy lane enforcement tests."""

from __future__ import annotations

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec


def test_normal_regime_non_cim_motion_renders_static_artifact() -> None:
    svg = compose(
        ComposeSpec(
            type="badge",
            genome_id="brutalist",
            title="build",
            value="passing",
            motion="dual-orbit",
            regime="normal",
        )
    ).svg

    assert 'data-hw-motion="static"' in svg
    assert 'motion="static"' in svg
    assert "hw-motion-dual-orbit" not in svg
    assert '<animate attributeName="stroke-dashoffset"' not in svg


def test_permissive_regime_keeps_non_cim_motion_overlay() -> None:
    svg = compose(
        ComposeSpec(
            type="badge",
            genome_id="brutalist",
            title="build",
            value="passing",
            motion="dual-orbit",
            regime="permissive",
        )
    ).svg

    assert 'data-hw-motion="dual-orbit"' in svg
    assert "hw-motion-dual-orbit" in svg
    assert '<animate attributeName="stroke-dashoffset"' in svg
