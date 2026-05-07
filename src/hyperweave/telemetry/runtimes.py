"""Per-runtime tool registries — spec-driven dispatch.

Replaces the single empirical ``data/telemetry/tool-classes.yaml`` (which
co-mingled every runtime's tools in one namespace) with per-runtime
registries at ``data/telemetry/runtimes/{runtime}.yaml``. Each registry
declares its detection rule (how to recognize a JSONL of this runtime
from its first line), parser module (for dispatcher import), genome /
glyph / provider_label (for resolver lookup), tool table, and pattern
rules (for namespaced families like MCP).

Adding a new runtime is a YAML drop-in: one file in ``runtimes/``, one
parser module, one genome JSON. No dispatcher edits, no resolver
branching — mirrors the paradigm-dispatch pattern (Invariant 12).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from hyperweave.telemetry.models import ToolClass

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger(__name__)

_RUNTIMES_DIR = Path(__file__).resolve().parent.parent / "data" / "telemetry" / "runtimes"


# --------------------------------------------------------------------------- #
# DATACLASSES
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DetectionRule:
    """Rule for sniffing a JSONL transcript's runtime from its first non-empty line.

    ``shape`` is informational; matching uses ``required_keys`` (every key
    must be present at top level) and ``type_values`` (the ``type`` field
    value must be in this set). The two together yield mutual exclusion
    across runtimes — a flat ``{sessionId, type}`` Claude line never
    matches the envelope ``{timestamp, type, payload}`` Codex rule.
    """

    shape: str
    required_keys: tuple[str, ...]
    type_values: tuple[str, ...]

    def matches(self, line: Mapping[str, Any]) -> bool:
        if not all(k in line for k in self.required_keys):
            return False
        type_value = line.get("type", "")
        return type_value in self.type_values


@dataclass(frozen=True)
class ToolPattern:
    """Prefix-based fallback for namespaced tool families (e.g., ``mcp__*``)."""

    prefix: str
    tool_class: ToolClass


@dataclass(frozen=True)
class RuntimeRegistry:
    """Complete registry for one runtime.

    Holds enough metadata to (a) detect when a JSONL belongs to this
    runtime, (b) dispatch to the correct parser, and (c) resolve the
    receipt's identity package (genome, glyph, provider label) without
    any ``if runtime == "..."`` branching.
    """

    runtime: str
    parser_module: str
    genome: str
    glyph: str
    provider_label: str
    detection: DetectionRule
    tools: Mapping[str, ToolClass]
    patterns: tuple[ToolPattern, ...]
    unknown_tool_policy: str  # "warn" | "error"


# --------------------------------------------------------------------------- #
# LOADING
# --------------------------------------------------------------------------- #


def _build_registry(data: Mapping[str, Any]) -> RuntimeRegistry:
    """Construct a RuntimeRegistry from a parsed YAML dict, validating shape."""
    detection_raw = data.get("detection") or {}
    detection = DetectionRule(
        shape=str(detection_raw.get("shape", "")),
        required_keys=tuple(detection_raw.get("required_keys") or ()),
        type_values=tuple(detection_raw.get("type_values") or ()),
    )
    tools_raw = data.get("tools") or {}
    tools = {name: ToolClass(cls) for name, cls in tools_raw.items()}
    patterns_raw = data.get("patterns") or ()
    patterns = tuple(ToolPattern(prefix=str(p["prefix"]), tool_class=ToolClass(p["class"])) for p in patterns_raw)
    return RuntimeRegistry(
        runtime=str(data["runtime"]),
        parser_module=str(data["parser"]),
        genome=str(data["genome"]),
        glyph=str(data["glyph"]),
        provider_label=str(data["provider_label"]),
        detection=detection,
        tools=tools,
        patterns=patterns,
        unknown_tool_policy=str(data.get("unknown_tool_policy", "warn")),
    )


@lru_cache(maxsize=1)
def load_all_runtimes() -> Mapping[str, RuntimeRegistry]:
    """Load every ``runtimes/*.yaml`` once and return a name → registry map.

    Cached: the YAML files don't change at runtime. Tests that need to
    reload (e.g., to inject a synthetic runtime) should call
    ``load_all_runtimes.cache_clear()`` first.
    """
    if not _RUNTIMES_DIR.is_dir():
        msg = f"Runtimes directory not found: {_RUNTIMES_DIR}"
        raise FileNotFoundError(msg)
    registries: dict[str, RuntimeRegistry] = {}
    for path in sorted(_RUNTIMES_DIR.glob("*.yaml")):
        with path.open() as f:
            data = yaml.safe_load(f) or {}
        registry = _build_registry(data)
        if registry.runtime in registries:
            msg = f"Duplicate runtime '{registry.runtime}' in {path}"
            raise ValueError(msg)
        registries[registry.runtime] = registry
    return registries


def get_runtime(name: str) -> RuntimeRegistry:
    """Look up a registry by runtime name. Raises ``KeyError`` if not registered."""
    registries = load_all_runtimes()
    if name not in registries:
        msg = f"Unknown runtime '{name}' (registered: {sorted(registries)})"
        raise KeyError(msg)
    return registries[name]


# --------------------------------------------------------------------------- #
# DETECTION + CLASSIFICATION
# --------------------------------------------------------------------------- #


def detect_runtime(first_line: Mapping[str, Any]) -> RuntimeRegistry:
    """Match a JSONL's first non-empty parsed line against every registry's detection rule.

    Raises ``ValueError`` when no rule matches. Detection rules across
    registered runtimes are mutually exclusive by construction
    (different ``required_keys`` or ``type_values`` sets); the test
    suite asserts this invariant.
    """
    registries = load_all_runtimes()
    matches = [r for r in registries.values() if r.detection.matches(first_line)]
    if not matches:
        msg = (
            "No runtime registry matches the first JSONL line. "
            f"Top-level keys: {sorted(first_line)}; "
            f"type={first_line.get('type', '<missing>')!r}"
        )
        raise ValueError(msg)
    if len(matches) > 1:
        names = sorted(r.runtime for r in matches)
        msg = f"Ambiguous runtime detection — multiple registries matched: {names}"
        raise ValueError(msg)
    return matches[0]


def classify_tool(registry: RuntimeRegistry, name: str) -> ToolClass:
    """Classify a tool name: exact match → pattern prefix match → unknown_tool_policy.

    Policy ``"warn"`` logs a warning and falls back to ``ToolClass.EXPLORE``
    (graceful — receipts still render). Policy ``"error"`` raises
    ``ValueError`` (strict — useful in CI to fail loud on unmapped tools).
    """
    if name in registry.tools:
        return registry.tools[name]
    for pattern in registry.patterns:
        if name.startswith(pattern.prefix):
            return pattern.tool_class
    if registry.unknown_tool_policy == "error":
        msg = f"unknown_tool: '{name}' (runtime={registry.runtime})"
        raise ValueError(msg)
    logger.warning(
        "unknown_tool: %r (runtime=%s) — falling back to ToolClass.EXPLORE; "
        "add to data/telemetry/runtimes/%s.yaml to silence",
        name,
        registry.runtime,
        registry.runtime,
    )
    return ToolClass.EXPLORE
