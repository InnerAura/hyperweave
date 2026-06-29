"""--font-mode: embed (default) | cdn | system (alpha.5 font work)."""

from __future__ import annotations

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec


def _svg(font_mode: str) -> str:
    return compose(
        ComposeSpec(
            type="strip",
            genome_id="primer",
            title="readme-ai",
            value="STARS:2.9k,FORKS:278",
            font_mode=font_mode,
        )
    ).svg


def test_embed_is_self_contained_base64() -> None:
    svg = _svg("embed")
    assert "@font-face" in svg and "base64" in svg


def test_cdn_uses_google_import_not_base64() -> None:
    svg = _svg("cdn")
    assert "fonts.googleapis.com" in svg
    assert "base64" not in svg


def test_system_embeds_no_fonts() -> None:
    svg = _svg("system")
    assert "@font-face" not in svg
    assert "base64" not in svg


def test_cdn_and_system_are_much_lighter_than_embed() -> None:
    embed, cdn, system = _svg("embed"), _svg("cdn"), _svg("system")
    assert len(cdn) < len(embed) // 2  # the base64 font blob dominates embed
    assert len(system) < len(embed) // 2
