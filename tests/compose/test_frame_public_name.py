"""stats→card public-name promotion at the compose + config layer.

The internal frame id (``stats``) stays everywhere — the FrameType value, the
payload schema id, the template key. Only the PUBLIC-name emission sites
(``data-hw-frame``, ``<hw:frame>``, the envelope ``k``) read ``card``. Every
other frame is identity-mapped (public name == internal id).
"""

from __future__ import annotations

import json
import re

from hyperweave.compose.engine import compose
from hyperweave.config.loader import frame_public_name, load_frame_aliases
from hyperweave.core.models import ComposeSpec

MOCK_STATS = {
    "username": "eli64s",
    "name": "Test User",
    "stars_total": 12847,
    "commits_total": 500,
    "prs_total": 40,
    "issues_total": 12,
    "streak_days": 9,
}


def _frame_marker(svg: str) -> str | None:
    m = re.search(r'data-hw-frame="([^"]+)"', svg)
    return m.group(1) if m else None


def _type_marker(svg: str) -> str | None:
    m = re.search(r'data-hw-type="([^"]+)"', svg)
    return m.group(1) if m else None


def _hw_frame(svg: str) -> str | None:
    m = re.search(r"<hw:frame>([^<]+)</hw:frame>", svg)
    return m.group(1) if m else None


def _envelope_k(svg: str) -> str | None:
    m = re.search(r"<hw:envelope[^>]*><!\[CDATA\[(.*?)\]\]>", svg, re.DOTALL)
    if not m:
        return None
    return json.loads(m.group(1)).get("k")


def _payload_schema(svg: str) -> str | None:
    m = re.search(r'<hw:payload[^>]*schema="([^"]+)"', svg)
    return m.group(1) if m else None


# ── Config: the alias table + resolver ───────────────────────────────────────


def test_frame_aliases_is_sparse_and_maps_stats_to_card() -> None:
    aliases = load_frame_aliases()
    assert aliases == {"stats": "card"}, "only the aliased frame belongs in the table"


def test_frame_public_name_resolves_alias_and_identity_maps_the_rest() -> None:
    assert frame_public_name("stats") == "card"
    # Every unaliased frame identity-maps.
    for internal in ("badge", "strip", "icon", "divider", "marquee", "chart", "matrix", "diagram", "receipt"):
        assert frame_public_name(internal) == internal


# ── Emission: stats artifact reads "card" at the public sites ────────────────


def test_stats_artifact_emits_public_card_name_at_all_three_sites() -> None:
    svg = compose(ComposeSpec(type="stats", genome_id="chrome", stats_username="eli64s", connector_data=MOCK_STATS)).svg
    assert _frame_marker(svg) == "card"
    assert _hw_frame(svg) == "card"
    assert _envelope_k(svg) == "card"


def test_stats_artifact_keeps_internal_id_on_type_and_schema() -> None:
    """data-hw-type and the payload schema id stay ``stats`` (internal identity;
    diff compat — the payload schema id is untouched)."""
    svg = compose(ComposeSpec(type="stats", genome_id="chrome", stats_username="eli64s", connector_data=MOCK_STATS)).svg
    assert _type_marker(svg) == "stats"
    assert _payload_schema(svg) == "stats/1"


def test_card_input_alias_produces_identical_public_emission() -> None:
    """``type='card'`` canonicalizes to the internal ``stats`` frame and emits the
    same public name — the input alias and the internal id are interchangeable."""
    spec = ComposeSpec(type="card", genome_id="chrome", stats_username="eli64s", connector_data=MOCK_STATS)
    assert spec.type == "stats"
    svg = compose(spec).svg
    assert _frame_marker(svg) == "card"
    assert _envelope_k(svg) == "card"


# ── Every other frame is unchanged (identity-mapped) ─────────────────────────


def test_badge_frame_is_identity_mapped() -> None:
    svg = compose(ComposeSpec(type="badge", genome_id="brutalist", title="BUILD", value="passing")).svg
    assert _frame_marker(svg) == "badge"
    assert _hw_frame(svg) == "badge"
    assert _envelope_k(svg) == "badge"
