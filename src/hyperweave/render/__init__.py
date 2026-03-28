"""Jinja2 SVG rendering -- templates, glyph registry, motion system."""

from hyperweave.render.glyphs import (
    GEOMETRIC_GLYPHS,
    can_render_glyph,
    infer_glyph,
    is_geometric,
    load_glyphs,
    render_glyph_context,
    render_glyph_svg,
)
from hyperweave.render.motion import (
    build_motion_context,
    get_motion_css,
    get_motion_info,
    get_motions_dir,
    is_cim_compliant,
    list_motions,
    load_motions,
    validate_motion,
    validate_motion_compat,
)
from hyperweave.render.templates import (
    create_jinja_env,
    get_templates_dir,
    render_artifact,
    render_template,
    set_templates_dir,
)

__all__ = [
    "GEOMETRIC_GLYPHS",
    "build_motion_context",
    "can_render_glyph",
    "create_jinja_env",
    "get_motion_css",
    "get_motion_info",
    "get_motions_dir",
    "get_templates_dir",
    "infer_glyph",
    "is_cim_compliant",
    "is_geometric",
    "list_motions",
    "load_glyphs",
    "load_motions",
    "render_artifact",
    "render_glyph_context",
    "render_glyph_svg",
    "render_template",
    "set_templates_dir",
    "validate_motion",
    "validate_motion_compat",
]
