"""Tests for kit.py -- compose_kit and helper functions.

Uses real compose for integration coverage of the kit pipeline.
"""

from __future__ import annotations

from hyperweave.core.state import infer_state
from hyperweave.kit import _parse_badge_string, compose_kit

# ===========================================================================
# compose_kit
# ===========================================================================


def test_compose_kit_readme_has_divider() -> None:
    results = compose_kit("readme", "brutalist-emerald")
    assert "divider" in results
    assert "<svg" in results["divider"].svg


def test_compose_kit_readme_badges() -> None:
    results = compose_kit("readme", "brutalist-emerald", badges="build:passing,version:v0.1.0")
    assert "badge-build" in results
    assert "badge-version" in results


def test_compose_kit_readme_strip() -> None:
    results = compose_kit("readme", "brutalist-emerald", badges="build:passing")
    assert "strip" in results


def test_compose_kit_readme_social_icons() -> None:
    results = compose_kit("readme", "brutalist-emerald", social="github,discord")
    assert "icon-github" in results
    assert "icon-discord" in results


def test_compose_kit_chrome_genome() -> None:
    results = compose_kit("readme", "chrome-horizon", "CHROME")
    assert "divider" in results


def test_compose_kit_unknown_type_returns_empty() -> None:
    results = compose_kit("nonexistent")
    assert results == {}


def test_compose_kit_artifact_count() -> None:
    """Kit with badges+social should produce divider + badges + strip + icons."""
    results = compose_kit("readme", "brutalist-emerald", "test", "build:passing,cov:95%", "github")
    assert len(results) >= 4  # divider, 2 badges, strip, 1 icon


# ===========================================================================
# infer_state
# ===========================================================================


def testinfer_state_passing() -> None:
    assert infer_state("build", "passing") == "passing"


def testinfer_state_success() -> None:
    assert infer_state("ci", "success") == "passing"


def testinfer_state_failing() -> None:
    assert infer_state("build", "failing") == "failing"


def testinfer_state_error() -> None:
    assert infer_state("lint", "error") == "failing"


def testinfer_state_warning() -> None:
    assert infer_state("lint", "warning") == "warning"


def testinfer_state_building() -> None:
    assert infer_state("build", "running") == "building"


def testinfer_state_percentage_high() -> None:
    assert infer_state("coverage", "95%") == "passing"


def testinfer_state_percentage_mid() -> None:
    assert infer_state("coverage", "75%") == "warning"


def testinfer_state_percentage_low() -> None:
    assert infer_state("coverage", "50%") == "critical"


def testinfer_state_default() -> None:
    assert infer_state("version", "v0.1.0") == "active"


# ===========================================================================
# _parse_badge_string
# ===========================================================================


def test_parse_badge_string() -> None:
    result = _parse_badge_string("build:passing,version:v0.1.0")
    assert result == [("build", "passing"), ("version", "v0.1.0")]


def test_parse_badge_string_with_spaces() -> None:
    result = _parse_badge_string(" build : passing , version : v0.1.0 ")
    assert result == [("build", "passing"), ("version", "v0.1.0")]


def test_parse_badge_string_empty() -> None:
    assert _parse_badge_string("") == []


def test_parse_badge_string_no_colon_skipped() -> None:
    result = _parse_badge_string("build:passing,invalid,version:v1")
    assert result == [("build", "passing"), ("version", "v1")]
