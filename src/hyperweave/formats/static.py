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


def strip_animation(svg: str) -> str:
    """Remove SMIL ``<animate*>`` elements, ``@keyframes``, and ``animation:`` decls."""
    svg = _ANIM_PAIR.sub("", svg)
    svg = _ANIM_SELF.sub("", svg)
    svg = _KEYFRAMES.sub("", svg)
    return _ANIM_DECL.sub("", svg)


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


def run_passes(svg: str, passes: list[str]) -> str:
    """Run the named passes over ``svg`` in order (unknown names raise KeyError)."""
    for name in passes:
        svg = _PASSES[name](svg)
    return svg


def pass_names() -> frozenset[str]:
    """The registered pass names (the YAML pipeline validates against this set)."""
    return frozenset(_PASSES)
