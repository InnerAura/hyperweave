"""Registry — cached accessors for all config data.

Replaces the ConfigLoader singleton with individual ``@lru_cache`` functions.
Each resource type has its own cache and can be cleared independently via
``reset_registry()`` (used by tests).
"""

from __future__ import annotations

import functools
from typing import Any

from hyperweave.config.loader import (
    load_font_metrics,
    load_genomes,
    load_glyphs,
    load_motions,
    load_policies,
    load_profiles,
    load_terminal_rules,
    load_terminals,
)
from hyperweave.core.models import ProfileConfig  # noqa: TC001 (runtime return type)
from hyperweave.core.schema import GenomeSpec  # noqa: TC001 (runtime return type)


@functools.lru_cache(maxsize=1)
def get_genome_specs() -> dict[str, GenomeSpec]:
    """All validated genome specs, keyed by ID."""
    return load_genomes()


@functools.lru_cache(maxsize=1)
def get_genomes() -> dict[str, dict[str, Any]]:
    """All genomes as dicts (for template/dict access). Validated through GenomeSpec."""
    return {gid: spec.model_dump() for gid, spec in get_genome_specs().items()}


@functools.lru_cache(maxsize=1)
def get_profile_configs() -> dict[str, ProfileConfig]:
    """All validated profile configs, keyed by ID."""
    return load_profiles()


@functools.lru_cache(maxsize=1)
def get_profiles() -> dict[str, dict[str, Any]]:
    """All profiles as dicts (for template/dict access). Validated through ProfileConfig."""
    return {pid: p.model_dump() for pid, p in get_profile_configs().items()}


@functools.lru_cache(maxsize=1)
def get_glyphs() -> dict[str, dict[str, Any]]:
    """Glyph registry from data/glyphs.json."""
    return load_glyphs()


@functools.lru_cache(maxsize=1)
def get_motions() -> dict[str, dict[str, Any]]:
    """Motion definitions from data/motions/."""
    return load_motions()


@functools.lru_cache(maxsize=1)
def get_terminals() -> dict[str, dict[str, Any]]:
    """Terminal geometry definitions."""
    return load_terminals()


@functools.lru_cache(maxsize=1)
def get_rules() -> dict[str, dict[str, Any]]:
    """Terminal rule style definitions."""
    return load_terminal_rules()


@functools.lru_cache(maxsize=1)
def get_policies() -> dict[str, dict[str, Any]]:
    """Policy lane definitions."""
    return load_policies()


@functools.lru_cache(maxsize=1)
def get_font_metrics() -> dict[str, dict[str, Any]]:
    """Font metric lookup tables."""
    return load_font_metrics()


def reset_registry() -> None:
    """Clear all registry caches. For testing."""
    get_genome_specs.cache_clear()
    get_genomes.cache_clear()
    get_profile_configs.cache_clear()
    get_profiles.cache_clear()
    get_glyphs.cache_clear()
    get_motions.cache_clear()
    get_terminals.cache_clear()
    get_rules.cache_clear()
    get_policies.cache_clear()
    get_font_metrics.cache_clear()
