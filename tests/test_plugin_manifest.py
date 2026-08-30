"""Plugin manifest guard — every declared skill path resolves and the declared
version matches the released package.

The `.claude-plugin/` directory is deliberately untracked until the skill
release's readiness commit (Gate 7 closes there), so this guard skips where the
directory is absent (fresh clones, worktrees) and validates wherever it exists
(the owner's main checkout, the eventual committed tree). A manifest publishing
paths that do not exist is the recorded defect this pins against.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_PLUGIN_DIR = _ROOT / ".claude-plugin"

pytestmark = pytest.mark.skipif(
    not _PLUGIN_DIR.is_dir(), reason="plugin manifests not present in this checkout (untracked until release)"
)


def test_every_declared_skill_path_resolves() -> None:
    marketplace = json.loads((_PLUGIN_DIR / "marketplace.json").read_text())
    for plugin in marketplace.get("plugins", []):
        for skill_path in plugin.get("skills", []):
            target = _ROOT / skill_path
            assert target.is_dir(), f"marketplace.json publishes a path that does not exist: {skill_path}"
            assert (target / "SKILL.md").is_file(), f"declared skill has no SKILL.md: {skill_path}"


def test_plugin_version_matches_the_released_package() -> None:
    from hyperweave import __version__

    declared = json.loads((_PLUGIN_DIR / "plugin.json").read_text()).get("version", "")
    assert declared, "plugin.json declares no version"
    release = __version__.split("+")[0].split(".dev")[0]
    if release == __version__:
        assert declared == release, f"plugin.json declares {declared} against released package {release}"
    else:
        # A dev build sits between releases; the manifest holds the last
        # release. The equality closes at the Stage 8 readiness commit.
        assert declared.count(".") == 2 and all(p.isdigit() for p in declared.split("."))
