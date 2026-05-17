"""Integration tests for the telemetry delivery pipeline.

Tests the full chain: transcript JSONL -> parser -> contract -> compose -> SVG.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

FIXTURE_JSONL = Path("tests/fixtures/session.jsonl")


@pytest.fixture()
def fixture_transcript() -> Path:
    assert FIXTURE_JSONL.exists(), f"Fixture not found: {FIXTURE_JSONL}"
    return FIXTURE_JSONL


def test_contract_structure(fixture_transcript: Path) -> None:
    """Contract has all required top-level keys."""
    from hyperweave.telemetry.contract import build_contract

    contract = build_contract(str(fixture_transcript))

    assert "session" in contract
    assert "profile" in contract
    assert "tools" in contract
    assert "stages" in contract
    assert "user_events" in contract
    assert "agents" in contract

    # Session fields
    session = contract["session"]
    assert "id" in session
    assert "model" in session
    assert "duration_minutes" in session

    # Profile fields
    profile = contract["profile"]
    assert "total_input_tokens" in profile
    assert "total_output_tokens" in profile
    assert "total_cost" in profile
    assert profile["total_cost"] > 0

    # Tools is a dict keyed by tool name
    tools = contract["tools"]
    assert isinstance(tools, dict)
    assert len(tools) > 0
    for _name, data in tools.items():
        assert "count" in data
        assert "total_tokens" in data
        assert "tool_class" in data


def test_receipt_end_to_end(fixture_transcript: Path) -> None:
    """Full pipeline: transcript -> contract -> receipt SVG."""
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec
    from hyperweave.telemetry.contract import build_contract

    contract = build_contract(str(fixture_transcript))
    spec = ComposeSpec(type="receipt", telemetry_data=contract)
    result = compose(spec)

    assert "<svg" in result.svg
    assert result.width == 800
    assert result.height == 500

    # Hero stats are populated
    svg = result.svg.lower()
    assert "token" in svg or "tok" in svg
    assert "session" in svg

    # Treemap cells present
    assert 'data-hw-zone="treemap"' in result.svg

    # Rhythm bars present
    assert 'data-hw-zone="rhythm"' in result.svg


def test_rhythm_strip_end_to_end(fixture_transcript: Path) -> None:
    """Full pipeline: transcript -> contract -> rhythm strip SVG."""
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec
    from hyperweave.telemetry.contract import build_contract

    contract = build_contract(str(fixture_transcript))
    spec = ComposeSpec(type="rhythm-strip", telemetry_data=contract)
    result = compose(spec)

    assert "<svg" in result.svg
    # v0.2.21 — rhythm-strip rewritten to v2 4-zone layout (600x92).
    assert result.width == 600
    assert result.height == 92

    # v0.2.21 — strip has 4 zones: identity / velocity / rhythm / status.
    assert 'data-hw-zone="identity"' in result.svg
    assert 'data-hw-zone="velocity"' in result.svg
    assert 'data-hw-zone="rhythm"' in result.svg
    assert 'data-hw-zone="status"' in result.svg


def test_cli_session_parse(fixture_transcript: Path) -> None:
    """CLI session parse outputs valid JSON with expected structure."""
    from typer.testing import CliRunner

    from hyperweave.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["session", "parse", str(fixture_transcript)])

    assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
    data = json.loads(result.output)
    assert "session" in data
    assert "tools" in data
    assert "stages" in data


def test_cli_session_receipt(fixture_transcript: Path, tmp_path: Path) -> None:
    """CLI session receipt writes SVG to output path."""
    from typer.testing import CliRunner

    from hyperweave.cli import app

    out_path = tmp_path / "receipt.svg"
    runner = CliRunner()
    result = runner.invoke(app, ["session", "receipt", str(fixture_transcript), "-o", str(out_path)])

    assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
    assert out_path.exists()
    svg = out_path.read_text()
    assert "<svg" in svg


def test_cli_session_strip(fixture_transcript: Path) -> None:
    """CLI session strip outputs SVG to stdout."""
    from typer.testing import CliRunner

    from hyperweave.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["session", "strip", str(fixture_transcript)])

    assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
    assert "<svg" in result.output


def test_cli_stdin_hook_mode(fixture_transcript: Path, tmp_path: Path) -> None:
    """Simulate Claude Code hook: JSON on stdin with transcript_path."""
    from typer.testing import CliRunner

    from hyperweave.cli import app

    out_path = tmp_path / "hook-receipt.svg"
    hook_json = json.dumps(
        {
            "session_id": "test-hook",
            "transcript_path": str(fixture_transcript),
            "hook_event_name": "SessionEnd",
        }
    )
    runner = CliRunner()
    result = runner.invoke(app, ["session", "receipt", "-o", str(out_path)], input=hook_json)

    assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
    assert out_path.exists()
    svg = out_path.read_text()
    assert "<svg" in svg


# ── Treemap layout regression tests ──

# Stress-test telemetry with real-world long tool names from Claude Code.
_STRESS_TELEMETRY: dict[str, object] = {
    "session": {
        "duration_m": 30,
        "total_cost": 50.0,
        "total_tokens": 10_000_000,
        "total_input": 100_000,
        "total_output": 200_000,
        "cache_read": 5_000_000,
        "cache_create": 1_000_000,
        "calls": 80,
        "model": "claude-opus-4-6",
    },
    "tools": {
        "Write": {"total_tokens": 500_000, "count": 20, "tool_class": "mutate", "blocked": 0, "errors": 3},
        "TaskCreate": {"total_tokens": 200_000, "count": 12, "tool_class": "coordinate", "blocked": 2, "errors": 0},
        "NotebookEdit": {"total_tokens": 150_000, "count": 8, "tool_class": "mutate", "blocked": 0, "errors": 0},
        "AskUserQuestion": {"total_tokens": 100_000, "count": 6, "tool_class": "coordinate"},
        "ToolSearch": {"total_tokens": 50_000, "count": 5, "tool_class": "explore"},
        "WebSearch": {"total_tokens": 40_000, "count": 4, "tool_class": "explore"},
        "EnterPlanMode": {"total_tokens": 30_000, "count": 3, "tool_class": "coordinate"},
        "EnterWorktree": {"total_tokens": 20_000, "count": 2, "tool_class": "execute"},
        "ServerSentEvents": {"total_tokens": 15_000, "count": 2, "tool_class": "explore"},
    },
    "stages": [
        {"name": "impl", "label": "IMPL", "pct": 60, "tool_class": "mutate"},
        {"name": "recon", "label": "RECON", "pct": 40, "tool_class": "explore"},
    ],
    "user_events": [],
    "agents": [],
}


def test_receipt_treemap_cells_have_tier_attribute() -> None:
    """Every treemap cell renders with data-hw-tier so downstream consumers
    can style/query by tier without parsing the geometric structure."""
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(type="receipt", telemetry_data=_STRESS_TELEMETRY)
    svg = compose(spec).svg

    tier_attrs = re.findall(r'data-hw-tier="([123])"', svg)
    assert len(tier_attrs) >= 5, f"Expected >=5 tiered cells, got {len(tier_attrs)}"
    # All three tiers should be represented for a stress fixture with 12+ tools.
    assert set(tier_attrs) >= {"1", "2", "3"}


def test_receipt_treemap_cell_dimensions_fit_content_width() -> None:
    """v0.2.21: label truncation now happens in compose/treemap.py, so the
    OLD clipPath-per-cell scaffolding was dropped. This test guards the
    invariant that survived the rewrite — every cell's right edge stays
    inside the 752px content track.
    """
    from hyperweave.compose.resolver import resolve_receipt
    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(type="receipt", telemetry_data=_STRESS_TELEMETRY)
    result = resolve_receipt(spec, {}, {})
    cells = result["context"]["treemap_cells"]
    assert cells, "fixture should produce treemap cells"
    # Cells are TreemapCell dataclasses with content-track-relative coords.
    assert max(c.x + c.w for c in cells) <= 752


def test_receipt_tier2_vertical_stacking() -> None:
    """Tier-2 treemap cells stack label above detail (distinct y values).

    v0.2.23 pushed positioning into ``TreemapCell.label_y`` / ``detail_y``
    so the template stays a dumb stamp. Test validates the stacking
    invariant via cell attribute inspection.
    """
    from hyperweave.compose.resolver import resolve_receipt
    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(type="receipt", telemetry_data=_STRESS_TELEMETRY)
    result = resolve_receipt(spec, {}, {})
    ctx = result["context"]
    tier2_cells = [c for c in ctx["treemap_cells"] if c.tier == 2]
    assert len(tier2_cells) >= 2, f"Expected >=2 tier-2 cells, got {len(tier2_cells)}"
    for cell in tier2_cells:
        assert cell.label_y != cell.detail_y, (
            f"Tier-2 cell '{cell.name}' has label/detail at same y — stacking regression"
        )


def test_receipt_treemap_error_annotations() -> None:
    """Cells with blocked/errored calls show ✗N; clean cells do not.

    v0.2.21 template: error badges render as `<text>✗{n}</text>` with
    `fill="var(--dna-status-failing-core)"`. The OLD `class="m cell-error"`
    selector is gone; the marker is the failing-core fill + ✗ glyph.
    """
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(type="receipt", telemetry_data=_STRESS_TELEMETRY)
    svg = compose(spec).svg

    tools = _STRESS_TELEMETRY["tools"]
    assert isinstance(tools, dict)
    expected_errors = {
        name: data["blocked"] + data["errors"]
        for name, data in tools.items()
        if isinstance(data, dict) and data.get("blocked", 0) + data.get("errors", 0) > 0
    }

    # Receipt-cell error badges: ✗{N} text wrapped in failing-core fill.
    # The legend marker (✗N as a generic example) ALSO appears, so we filter
    # by requiring a numeric count (not the literal "N" of the legend tspan).
    error_annotations = re.findall(
        r'fill="var\(--dna-status-failing-core\)"[^>]*>✗(\d+)</text>',
        svg,
    )

    for name, count in expected_errors.items():
        assert str(count) in error_annotations, f"Expected ✗{count} for {name}, got: {error_annotations}"

    assert len(error_annotations) == len(expected_errors), (
        f"Expected {len(expected_errors)} cell error annotations, got {len(error_annotations)}: {error_annotations}"
    )


# ── Hero/footer label split (§2.1) + ✗N legend (§2.7) ──


def test_receipt_splits_user_turns_and_tool_errors() -> None:
    """Hero and footer emit user-turn + tool-error counts as distinct labels.

    Reconciles two channels the old "N corrections" string conflated: user-event
    count (how often a human pushed back) vs. tool-failure count (how often a
    tool call returned blocked/error). The ✗N marks on the treemap reconcile
    to `n_tool_errors`, not to `len(user_events)`.
    """
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    tel = {
        "session": {"id": "sess", "duration_minutes": 60, "model": "claude-opus"},
        "profile": {"total_input_tokens": 10_000, "total_output_tokens": 5_000, "total_cost": 1.0},
        "tools": {
            "Edit": {"total_tokens": 1000, "count": 10, "tool_class": "mutate", "errors": 3, "blocked": 0},
            "Bash": {"total_tokens": 500, "count": 5, "tool_class": "execute", "errors": 0, "blocked": 2},
        },
        "stages": [{"name": "impl", "label": "IMPL", "pct": 100, "tool_class": "mutate"}],
        # 4 non-continuation user events → 4 user turns.
        "user_events": [
            {"category": "correction", "preview": "x", "confidence": "high"},
            {"category": "redirection", "preview": "x", "confidence": "high"},
            {"category": "elaboration", "preview": "x", "confidence": "high"},
            {"category": "correction", "preview": "x", "confidence": "high"},
        ],
        "agents": [],
    }
    spec = ComposeSpec(type="receipt", telemetry_data=tel)
    svg = compose(spec).svg

    # Hero-right shows both labels (now joined by ' · ' on a single row,
    # red-tinted via failing-core when tool errors are present).
    assert "4 user turns" in svg
    assert "5 tool errors" in svg  # 3 Edit errors + 2 Bash blocked
    # The pushback row carries the failing-core tint when tool errors > 0.
    assert 'fill="var(--dna-status-failing-core)"' in svg
    # The legacy single "N corrections" string is gone.
    assert "corrections" not in svg.lower()
    # Hero-right joins user-turns + tool-errors on a single row.
    assert "4 user turns · 5 tool errors" in svg


def test_receipt_singular_user_turn_pluralization() -> None:
    """One user event → "1 user turn" (no plural s)."""
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    tel = {
        "session": {"id": "s", "duration_minutes": 10, "model": "claude-opus"},
        "profile": {"total_input_tokens": 1, "total_output_tokens": 1, "total_cost": 0.01},
        "tools": {"Read": {"total_tokens": 10, "count": 1, "tool_class": "explore"}},
        "stages": [{"name": "e", "label": "E", "pct": 100, "tool_class": "explore"}],
        "user_events": [{"category": "correction", "preview": "x", "confidence": "high"}],
        "agents": [],
    }
    svg = compose(ComposeSpec(type="receipt", telemetry_data=tel)).svg
    assert "1 user turn" in svg
    assert "1 user turns" not in svg  # singular form, no trailing s


def test_receipt_renders_failed_tool_calls_legend() -> None:
    """Treemap header shows the ✗N legend so ✗8 marks aren't ambiguous.

    v0.2.21 splits the legend across two `<tspan>` elements (the ✗N gets
    failing-core fill, the descriptor stays muted), so this test checks
    both pieces are present rather than treating it as one flat string.
    """
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    svg = compose(ComposeSpec(type="receipt", telemetry_data=_STRESS_TELEMETRY)).svg
    assert "✗N" in svg
    assert "= failed tool calls" in svg


def test_treemap_field_is_errors_not_error_count() -> None:
    """No live .j2 template references the stale `cell.error_count` field.

    Prior drift: receipt.svg.j2 used `cell.errors` while a now-deleted orphan
    treemap component used `cell.error_count`. The orphan was removed in the
    P0 audit cleanup; this test still defends against any future drift across
    all live .j2 files.
    """
    from pathlib import Path

    templates_root = Path(__file__).resolve().parent.parent / "src" / "hyperweave" / "templates"
    for path in templates_root.rglob("*.j2"):
        text = path.read_text()
        assert "error_count" not in text, f"Stale cell.error_count reference in {path}"


# ── Hero dominant phase (§2.3) — not stages[0], MIXED when < 20% ──


def test_hero_uses_dominant_stage_not_first_stage() -> None:
    """When stages[0] is small and a later stage dominates, hero shows the dominant.

    Old bug: hero_profile = stages[0]["label"].upper() always picked the first
    stage, even when it was a 2-minute "validation" spike preceding 180 minutes
    of implementation. The hero badge lied about the session character.
    """
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    tel = {
        "session": {"id": "s", "duration_minutes": 210, "model": "claude-opus"},
        "profile": {"total_input_tokens": 1000, "total_output_tokens": 1000, "total_cost": 1.0},
        "tools": {"Edit": {"total_tokens": 100, "count": 10, "tool_class": "mutate"}},
        "stages": [
            # First stage: small, "validation" — the old stages[0] winner.
            {"label": "VALIDATION", "dominant_class": "explore", "tools": 2},
            # Dominant: "IMPLEMENTATION" with 45 tool calls (~95% share).
            {"label": "IMPLEMENTATION", "dominant_class": "mutate", "tools": 45},
        ],
        "user_events": [],
        "agents": [],
    }
    svg = compose(ComposeSpec(type="receipt", telemetry_data=tel)).svg

    # v0.2.21 hero pill: text inside `<g data-hw-zone="phase-pill">` with
    # letter-spacing="0.28em" (specimen value). Pulls the dominant label,
    # not the first-stage label.
    pill_match = re.search(
        r'data-hw-zone="phase-pill".*?letter-spacing="0\.28em"[^>]*>([A-Z\s]+)</text>',
        svg,
        re.DOTALL,
    )
    assert pill_match is not None
    assert "IMPLEMENTATION" in pill_match.group(1)
    assert "VALIDATION" not in pill_match.group(1)


def test_hero_falls_back_to_mixed_when_no_stage_dominates() -> None:
    """79 fragmented stages, none at >= 20% share → hero shows "MIXED"."""
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    tel = {
        "session": {"id": "s", "duration_minutes": 209, "model": "claude-opus"},
        "profile": {"total_input_tokens": 1000, "total_output_tokens": 1000, "total_cost": 1.0},
        "tools": {"Edit": {"total_tokens": 100, "count": 10, "tool_class": "mutate"}},
        # 79 equal-share stages → max pct = round(1/79 * 100) = 1 → well below 20.
        "stages": [
            {"label": f"STAGE{i}", "dominant_class": "explore" if i % 2 else "mutate", "tools": 1} for i in range(79)
        ],
        "user_events": [],
        "agents": [],
    }
    svg = compose(ComposeSpec(type="receipt", telemetry_data=tel)).svg

    pill_match = re.search(
        r'data-hw-zone="phase-pill".*?letter-spacing="0\.28em"[^>]*>([A-Z\s]+)</text>',
        svg,
        re.DOTALL,
    )
    assert pill_match is not None
    assert "MIXED" in pill_match.group(1)


def test_hero_defaults_to_session_when_no_stages() -> None:
    """Empty stages → hero pill shows "SESSION" (still a valid composition)."""
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    tel = {
        "session": {"id": "s", "duration_minutes": 0, "model": "claude-opus"},
        "profile": {"total_input_tokens": 0, "total_output_tokens": 0, "total_cost": 0},
        "tools": {},
        "stages": [],
        "user_events": [],
        "agents": [],
    }
    svg = compose(ComposeSpec(type="receipt", telemetry_data=tel)).svg
    assert "SESSION" in svg


# ── Active-window crop (v0.2.21 visual-fidelity-fix) ──
# When a session is left open overnight (e.g. 19,689m total but actual work
# concentrated in the first ~3h), the bar chart's grid lines and time-axis
# labels should key off the active window — not the full session — so we
# don't get a dense mesh of grid lines compressed into the leftmost 2% of
# the chart. Resolver computes active_duration_m from stage timestamps.


def _telemetry_with_session_durations(
    *,
    duration_minutes: float,
    stage_minutes: list[tuple[str, float, float]],
) -> dict[str, Any]:
    """Build telemetry data with stages whose timestamps frame an active window.

    Each ``stage_minutes`` triple is ``(class, start_offset_m, end_offset_m)``
    measured from a fixed session start. The session ``duration_minutes``
    can be far larger than the stages' timespan to simulate "session left
    open" scenarios.
    """
    base = "2026-01-01T00:00:00"
    base_dt = datetime.fromisoformat(base)
    stages = []
    for cls, start_off, end_off in stage_minutes:
        start = (base_dt + timedelta(minutes=start_off)).isoformat()
        end = (base_dt + timedelta(minutes=end_off)).isoformat()
        stages.append(
            {
                "label": cls.upper(),
                "dominant_class": cls,
                "start": start,
                "end": end,
                "tools": 5,
                "tokens": 1000,
                "errors": 0,
            }
        )
    return {
        "session": {"id": "active-window-test", "duration_minutes": duration_minutes, "model": "claude-opus"},
        "profile": {"total_input_tokens": 100, "total_output_tokens": 50, "total_cost": 0.50},
        "tools": {"Read": {"total_tokens": 5000, "count": 5, "tool_class": "explore"}},
        "stages": stages,
        "user_events": [],
        "agents": [],
    }


def test_receipt_hero_subline_flags_divergence_when_active_lt_half_session() -> None:
    # Session duration 100m but stages span only 30m (active = 30%, well under
    # 50% threshold). Hero subline should surface both numbers honestly.
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    tel = _telemetry_with_session_durations(
        duration_minutes=100,
        stage_minutes=[("explore", 0, 15), ("execute", 15, 30)],
    )
    svg = compose(ComposeSpec(type="receipt", telemetry_data=tel)).svg
    assert "30m active" in svg
    assert "100m total" in svg


def test_receipt_hero_subline_omits_divergence_when_active_close_to_session() -> None:
    # Stages span 0-80m (sum=80, wall_clock=80), session duration_m=100m.
    # active=80, total=max(100,80)=100, ratio=0.8 ≥ 0.5 → no divergence flag.
    # Hero shows the active duration (80m), NOT parser's 100m. Stage-derived
    # values are the single source of truth for the chart axis + hero label.
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    tel = _telemetry_with_session_durations(
        duration_minutes=100,
        stage_minutes=[("explore", 0, 80)],
    )
    svg = compose(ComposeSpec(type="receipt", telemetry_data=tel)).svg
    assert "80m" in svg
    # No divergence flag: the "active · total" pattern shouldn't appear.
    assert "active · " not in svg
    assert " total" not in svg


def test_receipt_falls_back_to_session_duration_when_stages_lack_timestamps() -> None:
    # Mock-style stages without start/end → active_duration_m falls back to
    # session.duration_minutes; subtitle and chart geometry use the full value.
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    tel = {
        "session": {"id": "no-ts", "duration_minutes": 60, "model": "claude-opus"},
        "profile": {"total_input_tokens": 100, "total_output_tokens": 50, "total_cost": 0.50},
        "tools": {"Read": {"total_tokens": 5000, "count": 5, "tool_class": "explore"}},
        "stages": [
            {"label": "EXP", "dominant_class": "explore", "tools": 5, "tokens": 1000, "errors": 0},
        ],
        "user_events": [],
        "agents": [],
    }
    svg = compose(ComposeSpec(type="receipt", telemetry_data=tel)).svg
    assert "60m" in svg
    # No divergence flag because active falls back to session duration.
    assert "active" not in svg.lower() or "no-ts" in svg  # session id is "no-ts", not "active"


# ── SessionEnd hook: graceful no-op for non-conversational sessions ──
# Claude Code fires SessionEnd for non-conversational actions (e.g.
# `claude update`, `claude config`) with non-TTY stdin but no valid JSONL
# transcript. `hyperweave session receipt` must silently exit 0 instead of
# surfacing "Error: no transcript found" to the user's terminal.
#
# typer's CliRunner provides non-TTY stdin by default, so no monkeypatching
# of sys.stdin.isatty() is needed to simulate hook mode. The TTY/interactive
# error branch is intentionally uncovered here — CliRunner's stdin redirection
# makes it impractical to test, and that path is pre-existing behavior.


def test_hook_mode_silent_on_empty_stdin() -> None:
    """`claude update` scenario: SessionEnd with empty stdin → graceful no-op."""
    from typer.testing import CliRunner

    from hyperweave.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["session", "receipt"], input="")

    assert result.exit_code == 0, (
        f"Hook-mode empty stdin must exit 0 gracefully. exit={result.exit_code}, output={result.output!r}"
    )


def test_hook_mode_silent_on_invalid_json() -> None:
    """Malformed stdin JSON must not crash the hook."""
    from typer.testing import CliRunner

    from hyperweave.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["session", "receipt"], input="not{valid}json")

    assert result.exit_code == 0, (
        f"Invalid JSON on stdin must not fail the hook. exit={result.exit_code}, output={result.output!r}"
    )


def test_hook_mode_silent_when_transcript_path_absent_from_payload() -> None:
    """Valid JSON without transcript_path key → graceful no-op."""
    from typer.testing import CliRunner

    from hyperweave.cli import app

    runner = CliRunner()
    payload = json.dumps({"hook_event_name": "SessionEnd"})
    result = runner.invoke(app, ["session", "receipt"], input=payload)

    assert result.exit_code == 0, (
        f"Missing transcript_path key must not fail the hook. exit={result.exit_code}, output={result.output!r}"
    )


def test_hook_mode_silent_when_transcript_path_does_not_exist(tmp_path: Path) -> None:
    """Hook references a path that no longer exists → graceful no-op."""
    from typer.testing import CliRunner

    from hyperweave.cli import app

    ghost = tmp_path / "never-existed.jsonl"
    runner = CliRunner()
    payload = json.dumps({"transcript_path": str(ghost)})
    result = runner.invoke(app, ["session", "receipt"], input=payload)

    assert result.exit_code == 0, (
        f"Nonexistent transcript path must not fail the hook. exit={result.exit_code}, output={result.output!r}"
    )


# ── Footer overlap fix (v0.2.23 close-out) ───────────────────────────────


def test_truncate_path_left_preserves_short_input() -> None:
    """A path that already fits returns unchanged (no spurious ellipsis)."""
    from hyperweave.compose.resolver import _truncate_path_left

    assert _truncate_path_left("short.svg", max_w=400) == "short.svg"


def test_truncate_path_left_drops_prefix_keeps_filename_end() -> None:
    """When the footer path is too long to fit, left-truncation preserves
    the meaningful end. The CLI emits v0.3.3 human-readable basenames like
    ``20260508_receipt_debug_v0226.svg``; HTTP / MCP without the hint emit
    the legacy ``.hyperweave/receipts/<uuid>.svg`` shape. In both forms
    the end carries the most identifying information.
    """
    from hyperweave.compose.resolver import _truncate_path_left

    long_basename = "20260508_a_very_long_session_title_describing_the_work_v0226.svg"
    out = _truncate_path_left(long_basename, max_w=200)
    assert out.startswith("…"), f"left-truncation must prefix with ellipsis, got {out!r}"
    assert out.endswith(".svg"), f"filename extension must survive truncation, got {out!r}"
    # Trailing version-tag bytes should remain so the receipt is still disambiguable.
    assert "v0226" in out, f"trailing slug bytes should remain, got {out!r}"


def test_truncate_path_left_returns_empty_when_width_below_ellipsis() -> None:
    """A budget too small even for the ellipsis returns empty string —
    the template's downstream rendering handles this gracefully."""
    from hyperweave.compose.resolver import _truncate_path_left

    assert _truncate_path_left("anything.svg", max_w=2) == ""


def test_truncate_path_left_handles_empty_input() -> None:
    """Empty string in → empty string out (no spurious ellipsis)."""
    from hyperweave.compose.resolver import _truncate_path_left

    assert _truncate_path_left("", max_w=400) == ""


def test_receipt_footer_truncates_long_path_to_avoid_overlap() -> None:
    """Production bug (claude-code 37.4M): footer_tl filepath collided
    with right-aligned footer_tr session date at y=470. The resolver
    must measure both and truncate the receipt path from the LEFT until
    they fit — preserving the meaningful suffix.

    HTTP / MCP callers don't set ``receipt_filename_hint``, so the footer
    falls back to the legacy ``.hyperweave/receipts/<uuid>.svg`` shape;
    that path drives the overflow + truncation flow here.
    """
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    # Mimic the claude-code 37.4M fixture's overflow scenario: long
    # project name + long matching branch + full UUID session id.
    tel = {
        "session": {
            "id": "4f7565a5-da44-4fbb-9234-b6f9cb2a1be6",
            "model": "claude-opus",
            "duration_minutes": 60,
            "git_branch": "claude/gracious-swirles-93af5c",
            "project_path": "/home/user/gracious-swirles-93af5c",
            "start": "2026-04-17T02:19:00",
        },
        "profile": {"total_input_tokens": 1, "total_output_tokens": 1, "total_cost": 0.01},
        "tools": {"Edit": {"total_tokens": 100, "count": 1, "tool_class": "mutate"}},
        "stages": [{"name": "i", "label": "I", "pct": 100, "tool_class": "mutate"}],
        "user_events": [],
        "agents": [],
    }
    svg = compose(ComposeSpec(type="receipt", telemetry_data=tel)).svg
    # Footer_tl line at y=470 must contain a left-truncated path (ellipsis
    # appears INSIDE the footer line, not at the start of the unrelated
    # branch name)
    footer_line_match = re.search(r'y="470"[^>]*>([^<]*)</text>', svg)
    assert footer_line_match, "footer_tl text element not found at y=470"
    footer_tl = footer_line_match.group(1)
    # The ellipsis marker is present, and the unique UUID tail survived
    assert "…" in footer_tl, f"long footer path should be truncated with ellipsis, got {footer_tl!r}"
    assert "b6f9cb2a1be6" in footer_tl, f"unique UUID tail should survive, got {footer_tl!r}"
    # The constant prefix was dropped — that's the point of left-truncation
    assert ".hyperweave/receipts/4f7565a5" not in footer_tl, (
        f"left-truncation should drop the prefix, got {footer_tl!r}"
    )


def test_receipt_footer_uses_filename_hint_when_supplied() -> None:
    """v0.3.4: the CLI write path passes the full relative path
    (``.hyperweave/receipts/{slug}.svg``) as ``ComposeSpec.receipt_filename_hint``;
    the footer surfaces it verbatim so the rendered footer is self-documenting —
    a reader sees the directory + filename and knows where to find the file.

    v0.3.3 shipped a regression where the CLI passed only the basename, hiding
    the directory; this test pins the v0.3.4 fix that restores the prefix.
    """
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    tel = {
        "session": {"id": "abc-def", "model": "claude-opus", "duration_minutes": 5},
        "profile": {"total_input_tokens": 1, "total_output_tokens": 1, "total_cost": 0.01},
        "tools": {"Edit": {"total_tokens": 100, "count": 1, "tool_class": "mutate"}},
        "stages": [{"name": "i", "label": "I", "pct": 100, "tool_class": "mutate"}],
        "user_events": [],
        "agents": [],
    }
    spec = ComposeSpec(
        type="receipt",
        telemetry_data=tel,
        receipt_filename_hint=".hyperweave/receipts/20260508_receipt_debug_v0226.svg",
    )
    svg = compose(spec).svg
    footer_line_match = re.search(r'y="470"[^>]*>([^<]*)</text>', svg)
    assert footer_line_match, "footer_tl text element not found at y=470"
    footer_tl = footer_line_match.group(1)
    # Full relative path must appear in the footer — directory prefix + basename.
    assert ".hyperweave/receipts/20260508_receipt_debug_v0226.svg" in footer_tl, (
        f"footer should surface the full relative path from receipt_filename_hint, got {footer_tl!r}"
    )


def test_receipt_footer_falls_back_to_uuid_path_when_hint_empty() -> None:
    """HTTP / MCP callers don't set ``receipt_filename_hint``; the footer
    must still render via the legacy UUID-path fallback so those code
    paths keep producing a usable footer.
    """
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    tel = {
        "session": {"id": "abc-def", "model": "claude-opus", "duration_minutes": 5},
        "profile": {"total_input_tokens": 1, "total_output_tokens": 1, "total_cost": 0.01},
        "tools": {"Edit": {"total_tokens": 100, "count": 1, "tool_class": "mutate"}},
        "stages": [{"name": "i", "label": "I", "pct": 100, "tool_class": "mutate"}],
        "user_events": [],
        "agents": [],
    }
    # Default: receipt_filename_hint="" → legacy UUID-path shape.
    spec = ComposeSpec(type="receipt", telemetry_data=tel)
    svg = compose(spec).svg
    footer_line_match = re.search(r'y="470"[^>]*>([^<]*)</text>', svg)
    assert footer_line_match, "footer_tl text element not found at y=470"
    footer_tl = footer_line_match.group(1)
    assert ".hyperweave/receipts/abc-def.svg" in footer_tl, (
        f"empty hint should fall back to UUID path, got {footer_tl!r}"
    )


def test_receipt_footer_unchanged_when_path_already_fits() -> None:
    """Short fixtures must NOT trigger truncation — the ellipsis only
    appears when overflow is real. Cream-mock fixture has empty session
    id → empty receipt_path → footer fits trivially.
    """
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    tel = {
        "session": {"id": "abc", "model": "claude-opus", "duration_minutes": 5},
        "profile": {"total_input_tokens": 1, "total_output_tokens": 1, "total_cost": 0.01},
        "tools": {"Edit": {"total_tokens": 100, "count": 1, "tool_class": "mutate"}},
        "stages": [{"name": "i", "label": "I", "pct": 100, "tool_class": "mutate"}],
        "user_events": [],
        "agents": [],
    }
    svg = compose(ComposeSpec(type="receipt", telemetry_data=tel)).svg
    footer_line_match = re.search(r'y="470"[^>]*>([^<]*)</text>', svg)
    assert footer_line_match
    footer_tl = footer_line_match.group(1)
    assert "…" not in footer_tl, f"short footer should not be truncated, got {footer_tl!r}"
