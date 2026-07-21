"""--help output contract: bracket annotations survive Rich markup parsing.

Rich treats ``[lowercase...]`` as a style tag and silently swallows unknown
ones — five annotations vanished from ``compose --help`` (two introduced by a
release that never saw them render). Escaped ``\\[`` is the fix; this file is
the first test to ever read the rendered help.
"""

from __future__ import annotations

from typer.testing import CliRunner

from hyperweave.cli import app

runner = CliRunner()

_ANNOTATIONS = (
    "[fetches GitHub data; 'stats' is an alias]",
    "[fetches star history]",
    "[rasterize; needs hyperweave[raster]]",
    "[custom genome]",
    "[render a session receipt]",
    "[Claude Code SessionEnd hook]",
)


def _normalized_help() -> str:
    result = runner.invoke(app, ["compose", "--help"])
    assert result.exit_code == 0, result.output
    # Terminal-width wrapping may split an annotation mid-string; collapse
    # whitespace before the substring check.
    return " ".join(result.output.split())


def test_compose_help_preserves_bracketed_annotations() -> None:
    rendered = _normalized_help()
    for annotation in _ANNOTATIONS:
        assert annotation in rendered, f"annotation eaten by Rich: {annotation!r}"


def test_compose_help_examples_brackets_balance() -> None:
    """Sweep net for future annotations: every ``[`` in the Examples block
    still has its ``]`` — a swallowed style tag drops both."""
    rendered = _normalized_help()
    start = rendered.find("Examples:")
    end = rendered.find("╭", start)
    examples = rendered[start : end if end != -1 else None]
    assert examples.count("[") == examples.count("]"), (
        "unbalanced brackets in Examples — a new annotation likely needs \\[ escaping"
    )
