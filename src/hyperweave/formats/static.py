"""Static-projection passes — pure string transforms over an assembled SVG.

A composed artifact is ``var(--dna-*)``-based and animated by default (the ``svg``
format). Off-browser rasterizers (resvg, CairoSVG, email clients, PDF converters)
do not resolve CSS custom properties — paints collapse to black/transparent
— and a static image wants no motion. The ``svg-static`` format is these
passes applied in order; ``png``/``webp`` rasterize that static projection.

The passes are deliberately self-contained: ``resolve_vars_to_hex`` reads the
artifact's OWN ``--dna-*: #hex`` declarations (every composed SVG emits them), so
the flatten needs no access to the genome registry.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

_DECL_RE = re.compile(r"(--dna-[a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{3,8}|rgba?\([^)]*\))")
# Matches any --* custom property. Fallback group allows one nesting level
# (var(--a, var(--b))); a fixpoint loop resolves deeper nesting.
_VAR_RE = re.compile(r"var\(\s*(--[a-z][a-z0-9-]*)\s*(?:,\s*((?:[^()]|\([^)]*\))*))?\)")
_ANIM_SELF = re.compile(r"<animate[A-Za-z]*\b[^>]*?/>")
_ANIM_PAIR = re.compile(r"<animate([A-Za-z]*)\b[^>]*?>.*?</animate\1>", re.DOTALL)
_KEYFRAMES = re.compile(r"@(-webkit-)?keyframes[^{]*\{(?:[^{}]*\{[^}]*\})*[^}]*\}")
_ANIM_DECL = re.compile(r"animation(?:-[a-z]+)?\s*:[^;}]*;?")


_STATUS_RE = re.compile(r'data-hw-status="([^"]+)"')
_ANYDECL_RE = re.compile(r"(--[a-z][a-z0-9-]*)\s*:\s*([^;}]+)")


def _active_state_decls(svg: str) -> dict[str, str]:
    """The ``--hw-state-*`` cascade values for the artifact's ACTIVE status.

    These vars live in ``[data-hw-status="X"]{…}`` selector blocks, not :root, so
    they must be read from the block matching the artifact's own status. Their
    values may themselves be ``var(--dna-*)`` — the fixpoint loop resolves those.
    """
    m = _STATUS_RE.search(svg)
    if not m:
        return {}
    status = re.escape(m.group(1))
    decls: dict[str, str] = {}
    for body in re.findall(rf'\[data-hw-status\s*=\s*"?{status}"?\][^{{]*\{{([^}}]*)\}}', svg):
        for name, value in _ANYDECL_RE.findall(body):
            if name.startswith("--hw-state"):
                decls[name] = value.strip()
    return decls


def resolve_vars_to_hex(svg: str) -> str:
    """Flatten ``var(--*)`` to literal hex using the artifact's own declarations.

    A used var with no declaration falls back to its inline fallback, then to the
    ink — never to empty (the black/transparent collapse this pass exists to prevent).
    """
    decls: dict[str, str] = dict(_DECL_RE.findall(svg))
    decls.update(_active_state_decls(svg))
    ink = decls.get("--dna-ink-primary") or decls.get("--dna-ink") or "#111111"

    def _sub(m: re.Match[str]) -> str:
        name, fallback = m.group(1), m.group(2)
        if name in decls:
            return decls[name]
        return fallback.strip() if fallback else ink

    # Fixpoint: each pass resolves the outermost var(); nested fallbacks resolve
    # on the next pass. Bounded to avoid pathological input.
    for _ in range(8):
        flat = _VAR_RE.sub(_sub, svg)
        if flat == svg:
            break
        svg = flat
    return svg


# An element resting at opacity="0" whose body carries an <animate*> child has
# animation as its ONLY lift — stripping the child would leave permanently
# invisible dead DOM (diagram motion particles, divider takeoff boosters).
# The opacity attribute + animate-in-body conjunction IS the two-part gate:
# intentionally-static opacity-0 content has no animate child and never matches.
# The lookbehind keeps fill-opacity="0"/stroke-opacity="0" (paint channels, not
# element visibility) from false-positive whole-element deletion.
_ANIMATION_ONLY_ELEMENT = re.compile(
    r'<(circle|ellipse|rect|path)\b[^>]*(?<![\w-])opacity="0"[^>]*>(?:(?!</\1>).)*?<animate(?:(?!</\1>).)*?</\1>\s*',
    re.DOTALL,
)
# The <g opacity="0"> fade-in group is the same dead-DOM class. Scoped to
# groups with NO nested <g> in the body (the guard tokens forbid any inner g
# open/close) — a regex cannot match balanced nesting, so nested groups are
# conservatively left alone rather than mis-truncated.
_ANIMATION_ONLY_GROUP = re.compile(
    r'<g\b[^>]*(?<![\w-])opacity="0"[^>]*>(?:(?!</?g[\s>]).)*?<animate(?:(?!</?g[\s>]).)*?</g>\s*',
    re.DOTALL,
)


def strip_animation(svg: str) -> str:
    """Remove SMIL ``<animate*>`` elements, ``@keyframes``, and ``animation:`` decls.

    Normalizes as it strips: an element whose only opacity source was its
    now-stripped animation is removed outright, never shipped invisible.
    """
    svg, _counts = strip_animation_counted(svg)
    return svg


def strip_animation_counted(svg: str) -> tuple[str, dict[str, int]]:
    """:func:`strip_animation` plus the projection's honesty counts.

    ``animated_elements_stripped`` = SMIL nodes removed (including those inside
    dropped elements); ``motion_only_elements_removed`` = elements deleted
    because animation was their only visibility.
    """
    animated = sum(1 for _ in _ANIM_PAIR.finditer(svg)) + sum(1 for _ in _ANIM_SELF.finditer(svg))
    svg, dead = _ANIMATION_ONLY_ELEMENT.subn("", svg)
    svg, dead_groups = _ANIMATION_ONLY_GROUP.subn("", svg)
    dead += dead_groups
    svg = _ANIM_PAIR.sub("", svg)
    svg = _ANIM_SELF.sub("", svg)
    svg = _KEYFRAMES.sub("", svg)
    svg = _ANIM_DECL.sub("", svg)
    counts: dict[str, int] = {}
    if animated:
        counts["animated_elements_stripped"] = animated
    if dead:
        counts["motion_only_elements_removed"] = dead
    return svg, counts


def clamp_width(svg: str, max_w: int = 800) -> str:
    """Cap the rendered width; viewBox preserves aspect ratio."""
    m = re.search(r'\bwidth="(\d+)"', svg)
    if m and int(m.group(1)) > max_w:
        return svg.replace(f'width="{m.group(1)}"', f'width="{max_w}"', 1)
    return svg


# Pass name → function. The svg-static pipeline (`data/config/output-formats.yaml`)
# names these; the loader resolves the names against this registry. Adding a pass
# is a Python function here + a name in the YAML pipeline — no treatment map.
_PASSES: dict[str, Callable[[str], str]] = {
    "vars": resolve_vars_to_hex,
    "noanim": strip_animation,
    "clamp": clamp_width,
}


def run_passes_counted(svg: str, passes: list[str]) -> tuple[str, dict[str, int]]:
    """:func:`run_passes` plus accumulated projection counts (noanim declares)."""
    counts: dict[str, int] = {}
    for name in passes:
        if name == "noanim":
            svg, pass_counts = strip_animation_counted(svg)
            for key, value in pass_counts.items():
                counts[key] = counts.get(key, 0) + value
        else:
            svg = _PASSES[name](svg)
    return svg, counts


def run_passes(svg: str, passes: list[str]) -> str:
    """Run the named passes over ``svg`` in order (unknown names raise KeyError)."""
    for name in passes:
        svg = _PASSES[name](svg)
    return svg


def pass_names() -> frozenset[str]:
    """The registered pass names (the YAML pipeline validates against this set)."""
    return frozenset(_PASSES)
