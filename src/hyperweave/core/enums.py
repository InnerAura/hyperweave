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
    BANNER = "banner"
    ICON = "icon"
    DIVIDER = "divider"
    MARQUEE_HORIZONTAL = "marquee-horizontal"
    MARQUEE_VERTICAL = "marquee-vertical"
    MARQUEE_COUNTER = "marquee-counter"
    RECEIPT = "receipt"
    RHYTHM_STRIP = "rhythm-strip"
    MASTER_CARD = "master-card"
    CATALOG = "catalog"


class GenomeId(StrEnum):
    """Genome identifier -- maps to a JSON config in data/genomes/."""

    BRUTALIST_EMERALD = "brutalist-emerald"
    CHROME_HORIZON = "chrome-horizon"


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


class KineticMotionId(StrEnum):
    """CSS/SMIL kinetic typography motions for banner frames."""

    BARS = "bars"
    BROADCAST = "broadcast"
    CASCADE = "cascade"
    COLLAPSE = "collapse"
    CONVERGE = "converge"
    CRASH = "crash"
    DROP = "drop"
    BREACH = "breach"
    PULSE = "pulse"


class MotionId(StrEnum):
    """All motion primitives -- union of static + border + kinetic.

    Use BorderMotionId or KineticMotionId when the context constrains
    which system applies. Use MotionId at API boundaries (ComposeSpec,
    CLI, MCP) where the caller picks from the full vocabulary.
    """

    STATIC = "static"
    # Border
    CHROMATIC_PULSE = "chromatic-pulse"
    CORNER_TRACE = "corner-trace"
    DUAL_ORBIT = "dual-orbit"
    ENTANGLEMENT = "entanglement"
    RIMRUN = "rimrun"
    # Kinetic
    BARS = "bars"
    BROADCAST = "broadcast"
    CASCADE = "cascade"
    COLLAPSE = "collapse"
    CONVERGE = "converge"
    CRASH = "crash"
    DROP = "drop"
    BREACH = "breach"
    PULSE = "pulse"


class DividerVariant(StrEnum):
    """Specimen-faithful divider variant -- each has a unique visual identity."""

    BLOCK = "block"
    CURRENT = "current"
    TAKEOFF = "takeoff"
    VOID = "void"
    ZEROPOINT = "zeropoint"


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
