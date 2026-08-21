"""The chromatic surface an artifact exposes — what a theme may repaint.

An agent handed a composed SVG has no way to know which paint answers to a
``--dna-*`` override. The only way to find out was to override everything and
watch what refused to move. This module builds the declaration that removes
that step: three zones, each naming what it is and whether it is writable.

The chassis list is a MEASUREMENT of the artifact's own stylesheet, taken at
the point every CSS layer is final, so it cannot go stale. The other two zones
name a locus and a reason rather than dumping hexes — ``sinks`` turns eight
commands of archaeology into one grep, and stays true as templates change.

Vocabulary and reasons live in ``data/config/chromatic-surface.yaml``
(Invariant 5); the emission is a Jinja template (Invariant 6).
"""

from __future__ import annotations

import re
from typing import Any

# The artifact's own `--dna-*: value` declarations. Deliberately the same shape
# formats/static.py:_DECL_RE reads for the flatten pass — one artifact, one
# answer to "which tokens does this file declare?".
_DECL_RE = re.compile(r"(--dna-[a-z0-9-]+)\s*:")

# A glyph paint value that came from the registry rather than the genome: a
# literal hex. `var(--dna-*)` fills are chassis paint and flip with the theme.
_LITERAL_PAINT = re.compile(r"^#[0-9A-Fa-f]{3,8}$")


def _frame_declared_tokens(ctx: dict[str, Any], rules: list[Any]) -> set[str]:
    """Tokens the FRAME's own defs template declares, per the config rules.

    The genome CSS layer is a string in the context and reads directly; a
    frame's defs stylesheet is rendered later by Jinja, so the tokens it will
    declare are named in ``chromatic-surface.yaml`` instead. Each rule fires
    only when its ``when`` field is truthy, matching the template's own
    condition — the far-face derivations are empty on a plate render.
    """
    frame = str(getattr(ctx.get("frame_type"), "value", ctx.get("frame_type", "")))
    paradigm = str(ctx.get("paradigm", ""))
    tokens: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        # frame/paradigm select the defs template; a rule may omit either to
        # match every render. Config data, never a branch on a paradigm literal.
        if "frame" in rule and str(rule["frame"]) != frame:
            continue
        if "paradigm" in rule and str(rule["paradigm"]) != paradigm:
            continue
        gate = str(rule.get("when") or "")
        if gate and not ctx.get(gate):
            continue
        tokens.update(str(name) for name in (rule.get("tokens") or []))
        name = str(rule.get("token") or "")
        if not name:
            continue
        source = str(rule.get("count_from") or "")
        if source:
            tokens.update(name.replace("{i}", str(i)) for i in range(len(ctx.get(source) or [])))
        else:
            tokens.add(name)
    return tokens


def _declared_tokens(*css_sources: str) -> set[str]:
    """Every ``--dna-*`` custom property declared in the given CSS text."""
    found: set[str] = set()
    for source in css_sources:
        found.update(_DECL_RE.findall(source or ""))
    return found


def _absorb_glyph_record(record: Any, brands: set[str]) -> None:
    """Record one glyph mark when its paint did not come from the genome.

    Three registry-painted shapes, all of which survive a genome swap: a
    gradient reference (multicolour master), a literal group fill, and
    per-path fills on a colour master.
    """
    glyph_id = str(getattr(record, "glyph_id", "") or getattr(record, "glyph", "") or "")
    gradient = str(getattr(record, "glyph_gradient", "") or getattr(record, "gradient", "") or "")
    fill = str(getattr(record, "glyph_fill", "") or getattr(record, "fill", "") or "")
    paths = getattr(record, "glyph_paths", None) or getattr(record, "paths", None) or ()
    path_literal = any(_LITERAL_PAINT.match(str(getattr(p, "fill", "") or "")) for p in paths)
    if not (gradient or path_literal or _LITERAL_PAINT.match(fill)):
        return
    name = glyph_id or gradient
    if name:
        brands.add(name)


def _collect_brand_glyphs(value: Any, brands: set[str], depth: int = 0) -> None:
    """Walk the context for glyph marks painted from the registry.

    Recursive by the same reasoning as ``context.py:_collect_text``: a new
    frame that wraps its glyph records in another list/dict layer is found
    without an edit here. Depth-bounded against a cyclic context.
    """
    if depth > 12 or value is None or isinstance(value, str | int | float | bool):
        return
    if isinstance(value, list | tuple):
        for item in value:
            _collect_brand_glyphs(item, brands, depth + 1)
        return
    if isinstance(value, dict):
        # A `*_glyph_gradients` entry IS a registry gradient: `id` is the glyph.
        if "stops" in value and "id" in value:
            brands.add(str(value["id"]))
            return
        for item in value.values():
            _collect_brand_glyphs(item, brands, depth + 1)
        return
    if hasattr(value, "__dataclass_fields__"):
        _absorb_glyph_record(value, brands)
        for field_name in value.__dataclass_fields__:
            _collect_brand_glyphs(getattr(value, field_name, None), brands, depth + 1)


def chromatic_zones(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """The artifact's mutability contract as L8 zone records.

    Called once per compose, after every CSS layer and frame record is final.
    Returns the rows ``components/chromatic-surface.svg.j2`` stamps; an empty
    brand zone is dropped rather than emitted as a lie about having none.
    """
    from hyperweave.config.loader import load_chromatic_surface

    cfg = load_chromatic_surface()
    capabilities = cfg["capabilities"]
    reasons = cfg["reasons"]

    tokens = _declared_tokens(str(ctx.get("css", "")), str(ctx.get("inline_style_overrides", "")))
    tokens |= _frame_declared_tokens(ctx, cfg["frame_tokens"])
    ordered = sorted(tokens)
    zones: list[dict[str, Any]] = [
        {
            "id": "chassis",
            "capability": str(capabilities.get("chassis", "chromatic-override")),
            "count": len(ordered),
            "tokens": " ".join(ordered),
        },
        {
            "id": "material",
            "capability": str(capabilities.get("material", "fixed")),
            "sinks": " ".join(cfg["sinks"]),
            "reason": str(reasons.get("material", "")),
        },
    ]

    brands: set[str] = set()
    _collect_brand_glyphs(ctx.get("frame_context") or {}, brands)
    for key, value in ctx.items():
        if key.endswith("_glyph_gradients") or key.startswith(("matrix_", "diagram_", "receipt_")):
            _collect_brand_glyphs(value, brands)
    single = str(ctx.get("glyph_id", "") or "")
    if single and ctx.get("has_glyph"):
        brands.add(single)
    if brands:
        zones.append(
            {
                "id": "brand",
                "capability": str(capabilities.get("brand", "fixed")),
                "count": len(brands),
                "glyphs": " ".join(sorted(brands)),
                "reason": str(reasons.get("brand", "")),
            }
        )
    return zones
