"""Jinja2 rendering -- environment setup, custom filters, render function."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import jinja2

# Template directory resolution

_TEMPLATES_DIR_OVERRIDE: Path | None = None


def get_templates_dir() -> Path:
    """Locate the templates directory."""
    if _TEMPLATES_DIR_OVERRIDE is not None:
        return _TEMPLATES_DIR_OVERRIDE
    return Path(__file__).resolve().parent.parent / "templates"


def set_templates_dir(path: Path) -> None:
    """Override the templates directory (useful for testing)."""
    global _TEMPLATES_DIR_OVERRIDE
    _TEMPLATES_DIR_OVERRIDE = path
    # Invalidate cached env when templates dir changes
    create_jinja_env.cache_clear()


# Jinja2 environment (singleton per templates_dir string)


@functools.lru_cache(maxsize=4)
def create_jinja_env(templates_dir: str | None = None) -> jinja2.Environment:
    """Create the Jinja2 environment with custom filters."""
    if templates_dir is None:
        templates_dir = str(get_templates_dir())

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_dir),
        autoescape=False,  # SVG output, not HTML
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )

    # Register custom filters
    env.filters["css_color"] = _filter_css_color
    env.filters["format_number"] = _filter_format_number
    env.filters["truncate_text"] = _filter_truncate_text
    env.filters["xml_escape"] = _filter_xml_escape

    return env


# Public render API


def render_artifact(template_name: str, context: dict[str, Any]) -> str:
    """Render an artifact SVG from a template and context."""
    env = create_jinja_env()
    template = env.get_template(template_name)
    return template.render(**context)


def render_template(template_name: str, context: dict[str, Any]) -> str:
    """Render a single template without assumptions about inheritance."""
    env = create_jinja_env()
    template = env.get_template(template_name)
    return template.render(**context)


def template_exists(template_name: str) -> bool:
    """Check if a Jinja2 template can be located in the templates dir.

    Used by resolvers that dispatch via slug interpolation
    (e.g., `frames/divider/<genome>-<slug>.svg.j2`) to fall back to a
    multi-branch template when no specific genome-themed template exists.
    """
    env = create_jinja_env()
    try:
        env.get_template(template_name)
    except jinja2.TemplateNotFound:
        return False
    return True


# Custom Jinja2 filters


def _filter_css_color(value: str) -> str:
    if not value:
        return "#000000"
    v = value.strip()
    if v.startswith(("#", "rgb", "hsl", "var(", "url(")):
        return v
    # Bare hex without # prefix
    if len(v) in (3, 6, 8) and all(c in "0123456789abcdefABCDEF" for c in v):
        return f"#{v}"
    return v


def _filter_format_number(value: Any, precision: int = 1) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)

    if n >= 1_000_000:
        return f"{n / 1_000_000:.{precision}f}M"
    if n >= 1_000:
        return f"{n / 1_000:.{precision}f}K"
    if n == int(n):
        return str(int(n))
    return f"{n:.{precision}f}"


def _filter_truncate_text(value: str, max_len: int = 30) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 1] + "\u2026"


def _filter_xml_escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
