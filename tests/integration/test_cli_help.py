"""--help output contract: bracket annotations survive Rich markup parsing.

Rich treats ``[lowercase...]`` as a style tag and silently swallows unknown
ones — five annotations vanished from ``compose --help`` (two introduced by a
release that never saw them render). Escaped ``\\[`` is the fix; this file is
the first test to ever read the rendered help.
"""

from __future__ import annotations

import re

from typer.testing import CliRunner

from hyperweave.cli import app

runner = CliRunner()

# CI runners force color, so the captured help carries ANSI styling that can
# split an annotation mid-string (styling is not content — Rich's SWALLOWING
# removes content, which the assertions still catch after stripping).
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

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
    # Strip ANSI styling, then collapse whitespace — terminal width and color
    # mode both vary per environment; the annotation TEXT must survive both.
    return " ".join(_ANSI.sub("", result.output).split())


def test_compose_help_preserves_bracketed_annotations() -> None:
    rendered = _normalized_help()
    for annotation in _ANNOTATIONS:
        assert annotation in rendered, f"annotation eaten by Rich: {annotation!r}"
