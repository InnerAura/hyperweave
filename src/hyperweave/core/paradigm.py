"""Paradigm specifications -- declarative frame-level config overrides.

A paradigm is a cross-cutting aesthetic family (chrome, brutalist, default)
that selects template partials and supplies layout dimensions + typography
sizes to resolvers. Genomes opt into paradigms per frame type via their
``paradigms`` dict:

    {"badge": "chrome", "strip": "chrome", "stats": "brutalist"}

Templates dispatch via slug interpolation:

    {% include "frames/stats/" ~ paradigm ~ "-content.j2" %}

Resolvers consume the typed sub-config (``paradigm_spec.strip.value_font_size``)
instead of comparing paradigm strings (``if paradigm == "chrome"``).

Scoping rule (Architectural Decision):
    ParadigmSpec owns layout + dispatch choices that are identical across
    every genome opting into the paradigm (viewport dims, font sizes,
    divider render mode). GenomeSpec owns chromatic identity and any
    per-genome structural choice (envelope_stops, data_point_shape).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from hyperweave.core.models import FrozenModel


class ParadigmChartConfig(FrozenModel):
    """Chart frame config within a paradigm."""

    viewport_x: int = 80
    viewport_y: int = 150
    viewport_w: int = 760
    viewport_h: int = 245


class ParadigmStatsConfig(FrozenModel):
    """Stats frame config within a paradigm."""

    card_height: int = 260
    embeds_chart: bool = False
    """When True, resolve_stats composes a compact star-history strip
    beneath the metric row (chrome paradigm). When False, stats card is
    self-contained (brutalist paradigm)."""
    embed_viewport_x: int = 240
    embed_viewport_y: int = 170
    embed_viewport_w: int = 220
    embed_viewport_h: int = 70


class ParadigmStripConfig(FrozenModel):
    """Strip frame config within a paradigm."""

    value_font_size: int = 18
    value_font_family: str = "Inter"
    label_font_size: int = 7
    label_font_family: str = "JetBrains Mono"
    divider_render_mode: Literal["gradient", "class"] = "class"
    """``gradient`` routes through chrome-defs ``url(#{uid}-sep)`` stroke;
    ``class`` uses a flat CSS-class-colored divider."""
    status_shape_rendering: Literal["crispEdges", "geometricPrecision"] = "crispEdges"


class ParadigmBadgeConfig(FrozenModel):
    """Badge frame config within a paradigm."""

    label_font_family: str = "Inter"
    value_font_family: str = "Inter"
    label_font_size: int = 11
    value_font_size: int = 11
    value_font_weight: int = 700


class ParadigmBannerConfig(FrozenModel):
    """Banner frame config within a paradigm."""

    hero_font_family: str = "Inter"
    hero_font_weight: int = 800
    hero_skew_deg: float = 0.0
    hero_italic: bool = False


class ParadigmIconConfig(FrozenModel):
    """Icon frame config within a paradigm."""

    supported_shapes: list[str] = Field(default_factory=lambda: ["square", "circle"])
    default_shape: str = "square"


class ParadigmSpec(FrozenModel):
    """A declarative paradigm: frame-level config + required genome fields.

    Loaded from ``data/paradigms/*.yaml`` by
    :func:`hyperweave.config.loader.load_paradigms`. Consumed by frame
    resolvers via ``paradigm_spec.{frame}.{key}`` attribute access.
    """

    id: str
    """Paradigm slug (matches YAML filename stem)."""
    name: str
    """Human-readable name."""
    description: str = ""

    badge: ParadigmBadgeConfig = Field(default_factory=ParadigmBadgeConfig)
    strip: ParadigmStripConfig = Field(default_factory=ParadigmStripConfig)
    banner: ParadigmBannerConfig = Field(default_factory=ParadigmBannerConfig)
    chart: ParadigmChartConfig = Field(default_factory=ParadigmChartConfig)
    stats: ParadigmStatsConfig = Field(default_factory=ParadigmStatsConfig)
    icon: ParadigmIconConfig = Field(default_factory=ParadigmIconConfig)

    requires_genome_fields: list[str] = Field(default_factory=list)
    """Genome field names that must be non-empty when a genome opts into
    this paradigm for any frame type. Enforced at load time by
    :func:`hyperweave.compose.validate_paradigms.validate_genome_against_paradigms`.
    """
