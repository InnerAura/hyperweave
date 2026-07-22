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


def load_idioms() -> dict[str, Any]:
    """Load the idiom registry (§3 diagrams-v2) from data/registries/idioms.yaml.

    The middle grammar tier: relations (line idioms) binding default dress,
    box/label idioms with scope + rhetoric + collision behavior. Chrome
    vocabulary — implemented once, consumed by every topology."""
    path = _data_path("registries/idioms.yaml")
    if not path.exists():
        return {}
    return _read_yaml(path)  # type: ignore[no-any-return]


def load_glyphs() -> dict[str, dict[str, Any]]:
    """Load the merged glyph registry: brand marks (glyphs.json) over the
    CORE set (glyphs-core.json — generic systems vocabulary a node ``kind``
    resolves; Lucide-derived stroke geometry, see NOTICE). A brand slug
    wins a name collision — brands are the more specific claim."""
    core_path = _data_path("registries/glyphs-core.json")
    core: dict[str, dict[str, Any]] = _read_json(core_path) if core_path.exists() else {}
    path = _data_path("registries/glyphs.json")
    brands: dict[str, dict[str, Any]] = _read_json(path) if path.exists() else {}
    merged = {**core, **brands}
    # Every core mark ALSO registers under ``kind:<slug>`` so a node ``kind``
    # reaches the generic mark even where a brand shadows the bare name
    # (shield/star/braces are brands AND generic words — each channel keeps
    # its own claim).
    for k, v in core.items():
        merged[f"kind:{k}"] = v
    return merged


@lru_cache(maxsize=1)
def load_badge_modes() -> frozenset[str]:
    """Load the stateful-title allowlist from data/config/badge-modes.yaml.

    Titles in the returned frozenset trigger status-indicator rendering
    AND auto-state-inference (engine.py:infer_state). Titles NOT in the
    set default to "stateless" mode at compose time. Lowercased; lookup
    via ``spec.title.lower() in load_badge_modes()``.

    Cached because every badge resolution checks against this set.
    """
    path = _data_path("config/badge-modes.yaml")
    if not path.exists():
        return frozenset()
    raw = _read_yaml(path) or {}
    return frozenset(str(t).lower() for t in raw.get("stateful_types", []))


@lru_cache(maxsize=1)
def load_frame_aliases() -> dict[str, str]:
    """Load the internal→public frame-name map from data/config/frame-aliases.yaml.

    Returns the sparse ``{internal_id: public_name}`` map (only frames whose
    public name differs from their internal id). Callers resolve a name through
    :func:`frame_public_name`, which identity-maps anything absent. Drives the
    string emitted in ``data-hw-frame``, ``<hw:frame>``, and the envelope ``k``;
    the internal id (FrameType value, payload schema id, template key) is
    unchanged. Missing file → empty map (every frame identity-mapped). Cached
    because the resolver fires once per compose() for every frame type.
    """
    path = _data_path("config/frame-aliases.yaml")
    if not path.exists():
        return {}
    raw = _read_yaml(path) or {}
    return {str(k): str(v) for k, v in (raw.get("public_names") or {}).items()}


def frame_public_name(internal: str) -> str:
    """Public name for a frame's internal id (identity when unaliased)."""
    return load_frame_aliases().get(internal, internal)


@lru_cache(maxsize=1)
def load_marquee_classes() -> tuple[dict[str, str], str]:
    """Load the marquee metric→category map from data/config/marquee-classes.yaml.

    Inverts the ``categories: {category: [metric, ...]}`` lists into a flat
    ``{metric_lower: category}`` dict at load. Returns
    ``(metric_to_category, default_category)``. Drives marquee auto-grouping
    ORDER (volume→activity→identity) and hero-eligibility. Missing file → an
    empty map + ``"volume"`` default (all-volume fail-safe). Cached because
    every marquee resolution reads it.
    """
    path = _data_path("config/marquee-classes.yaml")
    if not path.exists():
        return {}, "volume"
    raw = _read_yaml(path) or {}
    default_category = str(raw.get("default_category", "volume"))
    flat: dict[str, str] = {}
    for category, metrics in (raw.get("categories") or {}).items():
        for metric in metrics or []:
            flat[str(metric).strip().lower()] = str(category)
    return flat, default_category


@lru_cache(maxsize=1)
def load_font_embedding() -> dict[str, Any]:
    """Load font embedding gate from data/config/font-embedding.yaml.

    Returns a dict with three top-level keys:

    - ``defaults``: per-frame fallback font slug lists (frames absent from
      a genome's block).
    - ``genomes``: per-(genome_id, frame_type) override font slug lists.
    - ``non_embedded_locales``: documentation-only list of locales that
      should bypass font embedding when CJK rendering is added.

    Cached because the font gate fires once per compose() call across
    every HTTP/CLI/MCP entry point.
    """
    path = _data_path("config/font-embedding.yaml")
    if not path.exists():
        return {"defaults": {}, "genomes": {}, "non_embedded_locales": []}
    raw = _read_yaml(path) or {}
    return {
        "defaults": raw.get("defaults") or {},
        "genomes": raw.get("genomes") or {},
        "non_embedded_locales": raw.get("non_embedded_locales") or [],
    }


@lru_cache(maxsize=1)
def load_output_format_pipelines() -> dict[str, list[str]]:
    """Load format→pass-pipeline map from data/config/output-formats.yaml.

    Returns ``{format_id: [pass_name, ...]}`` — the ordered static passes for
    each SVG-shaped format (``svg`` is empty; ``svg-static`` = flatten + strip
    motion). Pass names resolve against ``formats/static.py``. Missing file →
    the built-in defaults (svg empty, svg-static = vars + noanim) so a partial
    install never loses the projection. Cached because the format projection
    reads it on every derive.
    """
    default = {"svg": [], "svg-static": ["vars", "noanim"]}
    path = _data_path("config/output-formats.yaml")
    if not path.exists():
        return default
    raw = _read_yaml(path) or {}
    pipelines = raw.get("pipelines") or {}
    if not pipelines:
        return default
    return {str(fmt): [str(p) for p in (passes or [])] for fmt, passes in pipelines.items()}


@lru_cache(maxsize=1)
def load_surface_modes() -> Any:
    """Load Surface Modes projection constants from data/config/surface-modes.yaml.

    Returns a validated :class:`~hyperweave.compose.surface_modes.SurfaceModesConfig`
    carrying the chroma classifier threshold, the calibrated re-ground lightness
    poles + tier offsets + chroma boost/cap, per-role contrast floors, the AA
    floor, the palette field→role map, and the frame allowlist. Every plate /
    inlay / twin decision reads it, so it is cached like the other config gates.
    The import is local to avoid a config→compose cycle at module load.
    """
    from hyperweave.compose.surface_modes import SurfaceModesConfig

    path = _data_path("config/surface-modes.yaml")
    raw = _read_yaml(path) or {}
    return SurfaceModesConfig(**raw)


@lru_cache(maxsize=1)
def load_envelope_tiers() -> dict[str, str]:
    """Load the per-frame envelope-depth map from data/config/envelope-tiers.yaml.

    Returns ``{frame_type: "minimal" | "full"}``. Frames absent from the file
    fall back to ``minimal`` at resolve time (the conservative default — a
    frame the map forgot still emits a valid, if shallow, envelope). Cached
    because the tier gate fires once per compose() for every frame type.
    """
    path = _data_path("config/envelope-tiers.yaml")
    if not path.exists():
        return {}
    raw = _read_yaml(path) or {}
    return {str(k): str(v) for k, v in (raw.get("tiers") or {}).items()}


@lru_cache(maxsize=1)
def load_matrix_config() -> dict[str, Any]:
    """Load matrix engine config from data/config/matrix-frame.yaml.

    Frame-generic cell knobs: ``caps``, ``polarity_keywords``,
    ``semantic_palette``, ``cell_geometry``, ``mono_triggers``. Chassis
    values live in the paradigm YAML instead. Cached because every matrix
    resolution reads it.
    """
    path = _data_path("config/matrix-frame.yaml")
    if not path.exists():
        return {}
    raw = _read_yaml(path) or {}
    return dict(raw)


@lru_cache(maxsize=1)
def load_diagram_config() -> dict[str, Any]:
    """Load diagram engine config from data/config/diagram-frame.yaml.

    Frame-generic flow knobs: ``caps``, ``orientation_legality``,
    ``routing_overridable``, connector/track/particle/beam/flow constants,
    ``annotate`` (the chrome pass's slide/push/callout constants),
    ``choreography``, ``fallback_ladder``, ``mono_triggers``. Chassis values
    and the kinetic-channel defaults live in the paradigm YAML instead.
    Cached because every diagram resolution reads it.
    """
    path = _data_path("config/diagram-frame.yaml")
    if not path.exists():
        return {}
    raw = _read_yaml(path) or {}
    return dict(raw)


@lru_cache(maxsize=1)
def load_diagram_presets() -> dict[str, dict[str, Any]]:
    """Load server-known diagram presets from data/presets/diagram.yaml.

    Each entry is a complete DiagramSpec dict (specimen recreations and the
    canon applied set) keyed by preset slug. Presets are content, so they
    live in data/ — a YAML edit updates the artifact, zero Python edits.
    """
    path = _data_path("presets/diagram.yaml")
    if not path.exists():
        return {}
    raw = _read_yaml(path) or {}
    return {str(k): dict(v) for k, v in (raw.get("presets") or {}).items()}


def load_matrix_presets() -> dict[str, dict[str, Any]]:
    """Load server-known matrix presets from data/presets/matrix.yaml.

    Same shape as :func:`load_diagram_presets`: a ``presets`` map keyed by
    slug. Matrix presets are connector_data payloads (e.g. ``connectors`` names
    an adapter built by ``build_connector_registry_matrix``), so the
    declaration is data and the builder stays code.
    """
    path = _data_path("presets/matrix.yaml")
    if not path.exists():
        return {}
    raw = _read_yaml(path) or {}
    return {str(k): dict(v) for k, v in (raw.get("presets") or {}).items()}


@lru_cache(maxsize=1)
def load_connector_registry() -> tuple[dict[str, Any], ...]:
    """Load the connector registry from data/registries/connectors.yaml.

    Source for the generated connector matrix (the ``connector-registry``
    matrix adapter). Returns the ordered connector entries; an immutable
    tuple because the result is cached and shared.
    """
    path = _data_path("registries/connectors.yaml")
    if not path.exists():
        return ()
    raw = _read_yaml(path) or {}
    return tuple(dict(entry) for entry in raw.get("connectors") or [])


def _available_font_slugs() -> frozenset[str]:
    """Return the set of font slugs present in data/fonts/ as .b64 + .meta.json pairs."""
    fonts_dir = _data_path("fonts")
    if not fonts_dir.exists():
        return frozenset()
    slugs: set[str] = set()
    for b64 in fonts_dir.glob("*.b64"):
        meta = b64.with_suffix(".meta.json")
        if meta.exists():
            slugs.add(b64.stem)
    return frozenset(slugs)


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
        # validate_genome_variants additionally checks v0.3.0 variant grammar
        # self-consistency: variant_overrides keys ⊆ variants[], variant_tones
        # structural shape, variant_pairs primary/secondary in tones, etc.
        from hyperweave.compose.validate_paradigms import (
            validate_font_embedding,
            validate_genome_against_paradigms,
            validate_genome_chromatic_coverage,
            validate_genome_roles,
            validate_genome_surface_contract,
            validate_genome_variants,
        )

        # Surface Modes supply contract: a genome opting into a surface-capable
        # frame (matrix/diagram per surface-modes.yaml) must carry the role
        # fields the adaptive projection needs on every variant — the gate that
        # lets a future genome (vellum) inherit inlay/twin with zero code.
        surface_frames = frozenset(load_surface_modes().frames)

        for genome_spec in self.genome_specs.values():
            validate_genome_against_paradigms(genome_spec, self.paradigms)
            validate_genome_variants(genome_spec)
            validate_genome_surface_contract(genome_spec, surface_frames)
            validate_genome_roles(genome_spec)
            validate_genome_chromatic_coverage(genome_spec)

        # Cross-validate the font embedding gate against the loaded genomes
        # and the on-disk font files. Catches typos, missing .b64 files,
        # and rows that reference fonts no genome declares (silent drops
        # at intersection time would otherwise mask the misconfig).
        validate_font_embedding(self.genome_specs, load_font_embedding(), _available_font_slugs())

        self.glyphs = load_glyphs()
        self.motions = load_motions()
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
