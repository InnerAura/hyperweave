"""Tests for the unified data-token grammar.

Covers parsing (text / kv / live tokens, escape rules, malformed input
rejection) and resolution (concurrent fetch via mocked
``connectors.fetch_metric``, failure degradation, min-TTL aggregation).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from hyperweave.serve.data_tokens import (
    DataToken,
    ResolvedToken,
    format_for_marquee,
    format_for_value,
    parse_data_tokens,
    resolve_data_tokens,
)

# ===========================================================================
# parse_data_tokens — single-token kinds
# ===========================================================================


def test_parse_text_token() -> None:
    tokens = parse_data_tokens("text:NEW RELEASE")
    assert tokens == [DataToken(kind="text", payload="NEW RELEASE")]


def test_parse_kv_token() -> None:
    tokens = parse_data_tokens("kv:VERSION=0.6.9")
    assert tokens == [DataToken(kind="kv", key="VERSION", literal_value="0.6.9")]


def test_parse_gh_live_token() -> None:
    tokens = parse_data_tokens("gh:anthropics/claude-code.stars")
    assert tokens == [
        DataToken(
            kind="live",
            provider="github",  # gh aliases to github
            identifier="anthropics/claude-code",
            metric="stars",
        )
    ]


def test_parse_pypi_live_token() -> None:
    tokens = parse_data_tokens("pypi:hyperweave.downloads")
    assert tokens == [DataToken(kind="live", provider="pypi", identifier="hyperweave", metric="downloads")]


def test_parse_arxiv_token_with_dotted_identifier() -> None:
    """The parser splits on the LAST dot so dotted arxiv IDs survive."""
    tokens = parse_data_tokens("arxiv:2310.06825.citations")
    assert tokens == [DataToken(kind="live", provider="arxiv", identifier="2310.06825", metric="citations")]


# ===========================================================================
# parse_data_tokens — multi-token + escape rules
# ===========================================================================


def test_parse_multi_token_mixed_kinds() -> None:
    tokens = parse_data_tokens("text:NEW RELEASE,gh:anthropics/claude-code.stars,kv:VERSION=0.6.9")
    assert len(tokens) == 3
    assert tokens[0].kind == "text"
    assert tokens[1].kind == "live"
    assert tokens[2].kind == "kv"


def test_parse_text_token_with_escaped_comma() -> None:
    """\\, inside text payload survives URL-decoded comma escape."""
    tokens = parse_data_tokens(r"text:Hello\, world")
    assert tokens == [DataToken(kind="text", payload="Hello, world")]


def test_parse_text_token_with_escaped_backslash() -> None:
    """\\\\ unescapes to a single backslash."""
    tokens = parse_data_tokens(r"text:path\\to\\thing")
    assert tokens == [DataToken(kind="text", payload=r"path\to\thing")]


def test_parse_kv_value_with_escaped_comma() -> None:
    """\\, inside kv: VALUE survives the escape rule."""
    tokens = parse_data_tokens(r"kv:LIST=a\,b\,c")
    assert tokens == [DataToken(kind="kv", key="LIST", literal_value="a,b,c")]


def test_parse_escaped_comma_then_real_separator() -> None:
    """Mix escaped commas with token-separator commas."""
    tokens = parse_data_tokens(r"text:Hello\, world,gh:owner/repo.stars")
    assert len(tokens) == 2
    assert tokens[0] == DataToken(kind="text", payload="Hello, world")
    assert tokens[1].kind == "live"


def test_parse_empty_input_returns_empty_list() -> None:
    assert parse_data_tokens("") == []


def test_parse_skips_whitespace_only_segments() -> None:
    tokens = parse_data_tokens("text:hello,,text:world")
    assert len(tokens) == 2


# ===========================================================================
# parse_data_tokens — failure cases
# ===========================================================================


def test_parse_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="unknown token kind"):
        parse_data_tokens("foobar:something.metric")


def test_parse_rejects_kv_without_equals() -> None:
    with pytest.raises(ValueError, match="missing '='"):
        parse_data_tokens("kv:JUSTKEYNOEQ")


def test_parse_rejects_kv_with_empty_key() -> None:
    with pytest.raises(ValueError, match="empty KEY"):
        parse_data_tokens("kv:=value")


def test_parse_rejects_live_without_dot() -> None:
    with pytest.raises(ValueError, match=r"missing '\.'"):
        parse_data_tokens("gh:owner/repo")


def test_parse_rejects_token_missing_colon() -> None:
    with pytest.raises(ValueError, match="missing ':'"):
        parse_data_tokens("noseparator")


def test_parse_rejects_trailing_backslash() -> None:
    with pytest.raises(ValueError, match="trailing backslash"):
        parse_data_tokens("text:hello\\")


def test_parse_rejects_invalid_escape_sequence() -> None:
    with pytest.raises(ValueError, match="invalid escape"):
        parse_data_tokens(r"text:hello\nworld")


# ===========================================================================
# resolve_data_tokens — fetches concurrently, degrades on failure
# ===========================================================================


@pytest.mark.asyncio
async def test_resolve_text_and_kv_dont_fetch() -> None:
    """text: and kv: tokens resolve without touching the connector."""
    tokens = parse_data_tokens("text:NEW,kv:VERSION=0.6.9")
    with patch("hyperweave.connectors.fetch_metric", new_callable=AsyncMock) as mock_fetch:
        resolved, ttl = await resolve_data_tokens(tokens)
    mock_fetch.assert_not_called()
    assert resolved[0] == ResolvedToken(kind="text", label="", value="NEW", ttl=0)
    assert resolved[1] == ResolvedToken(kind="kv", label="VERSION", value="0.6.9", ttl=0)
    assert ttl == 300  # default when no live tokens


@pytest.mark.asyncio
async def test_resolve_live_token_fetches_via_connector() -> None:
    tokens = parse_data_tokens("gh:owner/repo.stars")
    fake_response: dict[str, Any] = {"value": 12345, "ttl": 300}
    with patch(
        "hyperweave.connectors.fetch_metric",
        new_callable=AsyncMock,
        return_value=fake_response,
    ) as mock_fetch:
        resolved, ttl = await resolve_data_tokens(tokens)
    mock_fetch.assert_called_once_with("github", "owner/repo", "stars")
    assert resolved[0] == ResolvedToken(kind="live", label="STARS", value="12345", ttl=300)
    assert ttl == 300


@pytest.mark.asyncio
async def test_resolve_failed_live_token_degrades_to_dashes() -> None:
    """A connector exception yields value='--' with the short failure TTL."""
    tokens = parse_data_tokens("gh:owner/repo.stars")
    with patch(
        "hyperweave.connectors.fetch_metric",
        new_callable=AsyncMock,
        side_effect=Exception("timeout"),
    ):
        resolved, ttl = await resolve_data_tokens(tokens)
    assert resolved[0].value == "--"
    assert resolved[0].ttl == 60
    assert ttl == 60  # min_ttl tracks the failure


@pytest.mark.asyncio
async def test_resolve_min_ttl_across_multiple_live() -> None:
    """min_ttl is the minimum across live tokens; non-live tokens contribute 0/skipped."""
    tokens = parse_data_tokens("gh:a/b.stars,pypi:c.version,text:HELLO")

    async def fake_fetch(provider: str, identifier: str, metric: str) -> dict[str, Any]:
        if provider == "github":
            return {"value": "1", "ttl": 600}
        if provider == "pypi":
            return {"value": "2", "ttl": 120}
        return {"value": "?", "ttl": 0}

    with patch(
        "hyperweave.connectors.fetch_metric",
        new_callable=AsyncMock,
        side_effect=fake_fetch,
    ):
        resolved, min_ttl = await resolve_data_tokens(tokens)
    assert min_ttl == 120  # pypi's TTL is the minimum
    assert len(resolved) == 3
    assert resolved[2].kind == "text"  # text token preserved at end


# ===========================================================================
# Output formatters
# ===========================================================================


def test_format_for_value_joins_kv_and_live() -> None:
    resolved = [
        ResolvedToken(kind="live", label="STARS", value="1234", ttl=300),
        ResolvedToken(kind="kv", label="VERSION", value="0.6.9", ttl=0),
    ]
    assert format_for_value(resolved) == "STARS:1234,VERSION:0.6.9"


def test_format_for_value_emits_text_payload_unlabeled() -> None:
    resolved = [
        ResolvedToken(kind="text", label="", value="NEW RELEASE", ttl=0),
        ResolvedToken(kind="live", label="STARS", value="1234", ttl=300),
    ]
    assert format_for_value(resolved) == "NEW RELEASE,STARS:1234"


def test_format_for_marquee_assigns_role_per_kind() -> None:
    resolved = [
        ResolvedToken(kind="text", label="", value="NEW", ttl=0),
        ResolvedToken(kind="live", label="STARS", value="12345", ttl=300),
        ResolvedToken(kind="kv", label="VERSION", value="0.6.9", ttl=0),
    ]
    items = format_for_marquee(resolved)
    assert len(items) == 3
    assert items[0]["role"] == "text"
    assert items[0]["text"] == "NEW"
    assert items[1]["role"] == "live"
    assert items[1]["text"] == "STARS 12345"
    assert items[1]["label"] == "STARS"
    assert items[1]["raw_value"] == "12345"
    assert items[2]["role"] == "kv"
    assert items[2]["text"] == "VERSION 0.6.9"
