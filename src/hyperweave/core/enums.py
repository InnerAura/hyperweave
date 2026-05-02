"""Shared enum values used across HyperWeave.

All enums are StrEnum so that ``"badge" == FrameType.BADGE`` holds True,
preserving backward compatibility with YAML configs, Jinja2 templates,
and existing string comparisons throughout the codebase.
"""

from __future__ import annotations

from enum import StrEnum


class FrameType(StrEnum):
    """Artifact frame type -- each maps to a distinct Jinja2 template."""

    BADGE = "badge"
    STRIP = "strip"
    ICON = "icon"
    DIVIDER = "divider"
    MARQUEE_HORIZONTAL = "marquee-horizontal"
    RECEIPT = "receipt"
    RHYTHM_STRIP = "rhythm-strip"
    MASTER_CARD = "master-card"
    CATALOG = "catalog"
    STATS = "stats"
    CHART = "chart"


class GenomeId(StrEnum):
    """Genome identifier -- maps to a JSON config in data/genomes/."""

    BRUTALIST = "brutalist"
    CHROME = "chrome"
    AUTOMATA = "automata"


class ProfileId(StrEnum):
    """Structural profile -- controls typography, geometry, and glyph rendering."""

    BRUTALIST = "brutalist"
    CHROME = "chrome"


class BorderMotionId(StrEnum):
    """SMIL border overlay motions for badge/strip frames."""

    CHROMATIC_PULSE = "chromatic-pulse"
    CORNER_TRACE = "corner-trace"
    DUAL_ORBIT = "dual-orbit"
    ENTANGLEMENT = "entanglement"
    RIMRUN = "rimrun"


class MotionId(StrEnum):
    """All motion primitives -- union of static + border.

    Use BorderMotionId when the context constrains which system applies.
    Use MotionId at API boundaries (ComposeSpec, CLI, MCP) where the
    caller picks from the full vocabulary.
    """

    STATIC = "static"
    # Border
    CHROMATIC_PULSE = "chromatic-pulse"
    CORNER_TRACE = "corner-trace"
    DUAL_ORBIT = "dual-orbit"
    ENTANGLEMENT = "entanglement"
    RIMRUN = "rimrun"


class DividerVariant(StrEnum):
    """Divider variant slug — both editorial generics and genome-themed.

    Post-v0.2.19 split:
      - Editorial generics (block, current, takeoff, void, zeropoint) are served
        from /a/inneraura/dividers/<slug>; genome-agnostic, hardcoded specimen colors.
      - Genome-themed (dissolve, band, seam) live at /v1/divider/{slug}/{genome}.{motion}
        and are validated against genome.dividers at resolve-time.
    Slug consistency rule: slug carries the design name only, never genome qualifier.
    """

    # Editorial generics (rendered via /a/inneraura/dividers/)
    BLOCK = "block"
    CURRENT = "current"
    TAKEOFF = "takeoff"
    VOID = "void"
    ZEROPOINT = "zeropoint"
    # Genome-themed (rendered via /v1/divider/, declared in genome.dividers)
    DISSOLVE = "dissolve"  # automata
    BAND = "band"  # chrome
    SEAM = "seam"  # brutalist


class GlyphMode(StrEnum):
    """Glyph rendering mode -- controls fill/stroke treatment."""

    AUTO = "auto"
    FILL = "fill"
    WIRE = "wire"
    NONE = "none"


class Regime(StrEnum):
    """Policy regime -- controls CIM enforcement and validation strictness."""

    NORMAL = "normal"
    PERMISSIVE = "permissive"
    UNGOVERNED = "ungoverned"


class ArtifactStatus(StrEnum):
    """Semantic status of an artifact -- drives status indicator color."""

    ACTIVE = "active"
    PASSING = "passing"
    BUILDING = "building"
    WARNING = "warning"
    CRITICAL = "critical"
    FAILING = "failing"
    OFFLINE = "offline"
    LOOP = "loop"


class PlatformId(StrEnum):
    """Target rendering platform -- controls SVG feature compatibility."""

    GITHUB_README = "github-readme"
    WEB_INLINE = "web-inline"
    WEB_IMAGE = "web-image"
    NOTION = "notion"
    APPLE_MAIL = "apple-mail"
    GMAIL = "gmail"


class PolicyLane(StrEnum):
    """Governance policy lane -- controls artifact trust level."""

    UNGOVERNED = "ungoverned"
    SANDBOXED = "sandboxed"
    VERIFIED = "verified"
    AIRLOCK = "airlock"
    MANUAL = "manual"
