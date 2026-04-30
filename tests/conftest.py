"""Shared test fixtures for HyperWeave.

All fixtures are session-scoped where possible to avoid repeated I/O.
No class-based tests -- pytest functions only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hyperweave.config.loader import load_genomes, load_profiles
from hyperweave.core.models import ComposeSpec, SlotContent

if TYPE_CHECKING:
    from hyperweave.core.models import ProfileConfig
    from hyperweave.core.schema import GenomeSpec


# ---------------------------------------------------------------------------
# Genome fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def all_genomes() -> dict[str, GenomeSpec]:
    """Load and return all genome definitions."""
    return load_genomes()


@pytest.fixture(scope="session")
def sample_genome() -> GenomeSpec:
    """Return the brutalist-emerald genome for tests."""
    genomes = load_genomes()
    return genomes["brutalist-emerald"]


@pytest.fixture(scope="session")
def genome_ids(all_genomes: dict[str, GenomeSpec]) -> list[str]:
    """Return all available genome IDs for parametrize helpers."""
    return sorted(all_genomes.keys())


# ---------------------------------------------------------------------------
# Profile fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def all_profiles() -> dict[str, ProfileConfig]:
    """Load and return all profile definitions."""
    return load_profiles()


@pytest.fixture(scope="session")
def sample_profile() -> ProfileConfig:
    """Return the brutalist profile for tests."""
    profiles = load_profiles()
    return profiles["brutalist"]


@pytest.fixture(scope="session")
def profile_ids(all_profiles: dict[str, ProfileConfig]) -> list[str]:
    """Return all available profile IDs for parametrize helpers."""
    return sorted(all_profiles.keys())


# ---------------------------------------------------------------------------
# ComposeSpec fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_compose_spec() -> ComposeSpec:
    """Return a minimal badge ComposeSpec for testing."""
    return ComposeSpec(
        type="badge",
        genome_id="brutalist-emerald",
        profile_id="brutalist",
        title="build",
        value="passing",
        state="passing",
        slots=[
            SlotContent(zone="identity", value="build"),
            SlotContent(zone="value", value="passing"),
        ],
    )


@pytest.fixture()
def strip_compose_spec() -> ComposeSpec:
    """Return a strip ComposeSpec for testing."""
    return ComposeSpec(
        type="strip",
        genome_id="brutalist-emerald",
        profile_id="brutalist",
        title="readme-ai",
        state="active",
        glyph="github",
        slots=[
            SlotContent(zone="identity", value="readme-ai"),
            SlotContent(zone="metric", value="2.9k", data={"label": "STARS"}),
        ],
    )


# ---------------------------------------------------------------------------
# Parametrize helpers
# ---------------------------------------------------------------------------

FRAME_TYPES = [
    "badge",
    "strip",
    "icon",
    "divider",
    "marquee-horizontal",
]

STATES = ["active", "passing", "warning", "critical", "failing", "building", "offline", "neutral"]


def genome_parametrize() -> Any:
    """Return pytest.mark.parametrize for all genomes.

    Usage:
        @genome_parametrize()
        def test_something(genome_id: str): ...
    """
    genomes = load_genomes()
    return pytest.mark.parametrize("genome_id", sorted(genomes.keys()))


def profile_parametrize() -> Any:
    """Return pytest.mark.parametrize for all profiles.

    Usage:
        @profile_parametrize()
        def test_something(profile_id: str): ...
    """
    profiles = load_profiles()
    return pytest.mark.parametrize("profile_id", sorted(profiles.keys()))
