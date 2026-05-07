"""Configuration loader -- reads all data files at startup."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from hyperweave.core.models import ProfileConfig
from hyperweave.core.paradigm import ParadigmSpec
from hyperweave.core.schema import GenomeSpec

# Default data directory (relative to package)
_PACKAGE_DIR = Path(__file__).resolve().parent.parent
_DATA_DIR = _PACKAGE_DIR / "data"


def _data_path(subpath: str) -> Path:
    return _DATA_DIR / subpath


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_genomes() -> dict[str, GenomeSpec]:
    """Load all genome JSON files from data/genomes/."""
    genomes_dir = _data_path("genomes")
    result: dict[str, GenomeSpec] = {}

    if not genomes_dir.exists():
        return result

    for path in sorted(genomes_dir.glob("*.json")):
        raw = _read_json(path)
        genome = GenomeSpec(**raw)
        result[genome.id] = genome

    return result


def load_profiles() -> dict[str, ProfileConfig]:
    """Load all profile YAML files from data/profiles/."""
    profiles_dir = _data_path("profiles")
    result: dict[str, ProfileConfig] = {}

    if not profiles_dir.exists():
        return result

    for path in sorted(profiles_dir.glob("*.yaml")):
        raw = _read_yaml(path)
        profile = ProfileConfig(**raw)
        result[profile.id] = profile

    return result


def load_paradigms() -> dict[str, ParadigmSpec]:
    """Load all paradigm YAML files from data/paradigms/.

    Paradigms declare frame-level layout/typography config and the set of
    genome fields that must be non-empty for any genome that opts into
    them (see ``ParadigmSpec.requires_genome_fields``). Missing paradigm
    slugs resolve to ``default`` at dispatch time.
    """
    paradigms_dir = _data_path("paradigms")
    result: dict[str, ParadigmSpec] = {}

    if not paradigms_dir.exists():
        return result

    for path in sorted(paradigms_dir.glob("*.yaml")):
        raw = _read_yaml(path)
        paradigm = ParadigmSpec(**raw)
        result[paradigm.id] = paradigm

    return result


def load_glyphs() -> dict[str, dict[str, Any]]:
    """Load the glyph registry from data/glyphs.json."""
    path = _data_path("glyphs.json")
    if not path.exists():
        return {}
    return _read_json(path)  # type: ignore[no-any-return]


@lru_cache(maxsize=1)
def load_badge_modes() -> frozenset[str]:
    """Load the stateful-title allowlist from data/badge_modes.yaml.

    Titles in the returned frozenset trigger status-indicator rendering
    AND auto-state-inference (engine.py:infer_state). Titles NOT in the
    set default to "stateless" mode at compose time. Lowercased; lookup
    via ``spec.title.lower() in load_badge_modes()``.

    Cached because every badge resolution checks against this set.
    """
    path = _data_path("badge_modes.yaml")
    if not path.exists():
        return frozenset()
    raw = _read_yaml(path) or {}
    return frozenset(str(t).lower() for t in raw.get("stateful_types", []))


def load_motions() -> dict[str, dict[str, Any]]:
    """Load motion definitions from data/motions/ (root + border/ + kinetic/ subdirs)."""
    motions_dir = _data_path("motions")
    result: dict[str, dict[str, Any]] = {}

    if not motions_dir.exists():
        return result

    # Root-level (static.yaml)
    for path in sorted(motions_dir.glob("*.yaml")):
        raw = _read_yaml(path)
        if raw and "id" in raw:
            result[raw["id"]] = raw

    # Subdirectories (border/, kinetic/)
    for subdir in ("border", "kinetic"):
        sub = motions_dir / subdir
        if sub.is_dir():
            for path in sorted(sub.glob("*.yaml")):
                raw = _read_yaml(path)
                if raw and "id" in raw:
                    result[raw["id"]] = raw

    return result


def load_terminals() -> dict[str, dict[str, Any]]:
    """Load terminal geometry definitions from data/terminals/."""
    terminals_dir = _data_path("terminals")
    result: dict[str, dict[str, Any]] = {}

    if not terminals_dir.exists():
        return result

    for path in sorted(terminals_dir.glob("*.json")):
        raw = _read_json(path)
        if raw and "id" in raw:
            result[raw["id"]] = raw

    return result


def load_terminal_rules() -> dict[str, dict[str, Any]]:
    """Load terminal rule style definitions from data/terminals/rules/."""
    rules_dir = _data_path("terminals/rules")
    result: dict[str, dict[str, Any]] = {}

    if not rules_dir.exists():
        return result

    for path in sorted(rules_dir.glob("*.json")):
        raw = _read_json(path)
        if raw and "id" in raw:
            result[raw["id"]] = raw

    return result


def load_policies() -> dict[str, dict[str, Any]]:
    """Load policy lane definitions from data/policies/."""
    policies_dir = _data_path("policies")
    result: dict[str, dict[str, Any]] = {}

    if not policies_dir.exists():
        return result

    for path in sorted(policies_dir.glob("*.json")):
        raw = _read_json(path)
        if raw and "id" in raw:
            result[raw["id"]] = raw

    return result


def load_font_metrics() -> dict[str, dict[str, Any]]:
    """Load font metric lookup tables from data/font-metrics/."""
    metrics_dir = _data_path("font-metrics")
    result: dict[str, dict[str, Any]] = {}

    if not metrics_dir.exists():
        return result

    for path in sorted(metrics_dir.glob("*.json")):
        raw = _read_json(path)
        if raw and "font_family" in raw:
            result[raw["font_family"].lower()] = raw

    return result


# Singleton ConfigLoader (used by compose pipeline)


class ConfigLoader:
    """Singleton that loads and caches all config at startup.

    Genomes are validated through GenomeSpec on load.  The validated models
    live in ``genome_specs``; the dict representation (for template access
    and backward compatibility) lives in ``genomes``.  Both are keyed by
    genome ID and stay in sync.
    """

    def __init__(self) -> None:
        self.genomes: dict[str, dict[str, Any]] = {}
        self.genome_specs: dict[str, GenomeSpec] = {}
        self.profiles: dict[str, dict[str, Any]] = {}
        self.profile_configs: dict[str, ProfileConfig] = {}
        self.paradigms: dict[str, ParadigmSpec] = {}
        self.glyphs: dict[str, dict[str, Any]] = {}
        self.motions: dict[str, dict[str, Any]] = {}
        self.terminals: dict[str, dict[str, Any]] = {}
        self.rules: dict[str, dict[str, Any]] = {}
        self.policies: dict[str, dict[str, Any]] = {}
        self.font_metrics: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def load(self) -> None:
        """Load all config files."""
        if self._loaded:
            return

        # Load genomes through GenomeSpec validation
        validated = load_genomes()
        for gid, spec in validated.items():
            self.genome_specs[gid] = spec
            self.genomes[gid] = spec.model_dump()

        # Load profiles through ProfileConfig validation
        validated_profiles = load_profiles()
        for pid, profile in validated_profiles.items():
            self.profile_configs[pid] = profile
            self.profiles[pid] = profile.model_dump()

        self.paradigms = load_paradigms()

        # Cross-validate: every genome must declare the genome fields
        # required by the paradigms it opts into. Raises at load time so
        # chrome-defs templates can drop their specimen-color fallbacks.
        from hyperweave.compose.validate_paradigms import validate_genome_against_paradigms

        for genome_spec in self.genome_specs.values():
            validate_genome_against_paradigms(genome_spec, self.paradigms)

        self.glyphs = load_glyphs()
        self.motions = load_motions()
        self.terminals = load_terminals()
        self.rules = load_terminal_rules()
        self.policies = load_policies()
        self.font_metrics = load_font_metrics()
        self._loaded = True


_loader: ConfigLoader | None = None


def get_loader() -> ConfigLoader:
    """Return the singleton ConfigLoader, creating and loading if needed.

    Delegates to the registry module for validated, cached data.
    All callers continue to work through this function while the
    registry provides the actual cached storage.
    """
    global _loader
    if _loader is None:
        _loader = ConfigLoader()
        _loader.load()
    return _loader


def reset_loader() -> None:
    """Reset the singleton loader and the registry caches. For testing."""
    global _loader
    _loader = None
    try:
        from hyperweave.config.registry import reset_registry

        reset_registry()
    except ImportError:
        pass
