"""Embed-snippet builder — single URL vs twin <picture> pair."""

from __future__ import annotations

import pytest

from hyperweave.delivery.embed import embed_snippets


def test_single_url_markdown_and_html() -> None:
    snips = embed_snippets(["https://hyperweave.app/v1/a/abc"], title="Build status", w=148, h=22)
    assert snips["markdown"] == "![Build status](https://hyperweave.app/v1/a/abc)"
    assert '<img src="https://hyperweave.app/v1/a/abc"' in snips["html"]
    assert 'alt="Build status"' in snips["html"]
    assert 'width="148"' in snips["html"] and 'height="22"' in snips["html"]


def test_single_url_omits_zero_dims() -> None:
    snips = embed_snippets(["https://x/a/1"], title="t")
    assert "width=" not in snips["html"] and "height=" not in snips["html"]


def test_twin_pair_builds_picture() -> None:
    """Two URLs (dark, light) → a prefers-color-scheme <picture> in both channels."""
    snips = embed_snippets(["https://x/a/dark.png", "https://x/a/light.png"], title="Twin")
    assert "<picture>" in snips["markdown"]
    assert "prefers-color-scheme: light" in snips["markdown"]
    assert 'srcset="https://x/a/light.png"' in snips["markdown"]
    assert 'src="https://x/a/dark.png"' in snips["markdown"]
    assert "prefers-color-scheme: dark" in snips["html"]


def test_html_escapes_alt_and_url() -> None:
    snips = embed_snippets(["https://x/a/1?a=1&b=2"], title='He said "hi" & <bye>')
    assert "&amp;" in snips["html"]
    assert "&quot;" in snips["html"] or "&#34;" in snips["html"]
    assert "<bye>" not in snips["html"]


def test_empty_urls_raises() -> None:
    with pytest.raises(ValueError, match="at least one url"):
        embed_snippets([])
