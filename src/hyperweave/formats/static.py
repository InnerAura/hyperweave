"""Static-projection passes — byte-span transforms over an assembled SVG.

A composed artifact is ``var(--dna-*)``-based and animated by default (the ``svg``
format). Off-browser rasterizers (resvg, CairoSVG, email clients, PDF converters)
do not resolve CSS custom properties — paints collapse to black/transparent
— and a static image wants no motion. The ``svg-static`` format is these
passes applied in order; ``png``/``webp`` rasterize that static projection.

The passes are deliberately self-contained: ``resolve_vars_to_hex`` reads the
artifact's OWN ``--dna-*: #hex`` declarations (every composed SVG emits them), so
the flatten needs no access to the genome registry.

Every pass edits located byte spans in place and never parses-and-reserializes:
an ElementTree round-trip destroys CDATA sections (``hw:payload`` among them),
drops comments, and rewrites namespace prefixes. Animation stripping locates
each syntactic scope — a SMIL element, a ``<style>`` body, a ``style`` attribute
value — and rewrites only that span with a scope-appropriate scanner; no pattern
ever crosses an attribute or element boundary. Comments and CDATA sections
outside ``<style>`` bodies are never edited.
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


def _var_keepout_spans(svg: str) -> list[tuple[int, int]]:
    """Spans the variable flatten must never edit: comments, CDATA (the
    ``hw:payload`` copy of a spec), and the TEXT NODES of text-bearing
    elements — a label that literally reads ``var(--dna-signal)`` is content,
    not a declaration. Attributes on those elements stay editable (a text
    element's ``fill="var(--dna-…)"`` must still resolve)."""
    spans = _protected_spans(svg)
    for m in re.finditer(r"<(text|tspan|title|desc|metadata|hw:[a-z-]+)\b", svg):
        close = svg.find(f"</{m.group(1)}", m.end())
        if close == -1:
            continue
        i = svg.find(">", m.end())
        while i != -1 and i < close:
            j = svg.find("<", i + 1)
            if j == -1 or j > close:
                j = close
            spans.append((i + 1, j))
            i = svg.find(">", j)
    return spans


def resolve_vars_to_hex(svg: str) -> str:
    """Flatten ``var(--*)`` to literal hex using the artifact's own declarations.

    A used var with no declaration falls back to its inline fallback, then to the
    ink — never to empty (the black/transparent collapse this pass exists to
    prevent). Substitution is span-scoped: CSS and attribute values only, never
    comments, CDATA payloads, or rendered text content.
    """
    decls: dict[str, str] = dict(_DECL_RE.findall(svg))
    decls.update(_active_state_decls(svg))
    ink = decls.get("--dna-ink-primary") or decls.get("--dna-ink") or "#111111"

    # Fixpoint: each pass resolves the outermost var(); nested fallbacks resolve
    # on the next pass. Bounded to avoid pathological input. Keep-out spans are
    # recomputed per pass — substitutions shift offsets.
    for _ in range(8):
        keepout = _var_keepout_spans(svg)

        def _sub(m: re.Match[str], _keepout: list[tuple[int, int]] = keepout) -> str:
            if _inside(m.start(), _keepout):
                return m.group(0)
            name, fallback = m.group(1), m.group(2)
            if name in decls:
                return decls[name]
            return str(fallback).strip() if fallback else ink

        flat = _VAR_RE.sub(_sub, svg)
        if flat == svg:
            break
        svg = flat
    return svg


# ---------------------------------------------------------------------------
# Protected spans — comments and CDATA sections are opaque to every markup
# pass (a hw:payload CDATA can legally contain the literal text of any tag).

_PROTECTED_RE = re.compile(r"<!--.*?-->|<!\[CDATA\[.*?\]\]>", re.DOTALL)


def _protected_spans(svg: str) -> list[tuple[int, int]]:
    return [m.span() for m in _PROTECTED_RE.finditer(svg)]


def _inside(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(s <= pos < e for s, e in spans)


def _delete_matches_outside(svg: str, pattern: re.Pattern[str]) -> tuple[str, int]:
    """Delete every match whose start lies outside a protected span."""
    spans = _protected_spans(svg)
    out: list[str] = []
    last = 0
    count = 0
    for m in pattern.finditer(svg):
        if _inside(m.start(), spans):
            continue
        out.append(svg[last : m.start()])
        last = m.end()
        count += 1
    out.append(svg[last:])
    return "".join(out), count


# ---------------------------------------------------------------------------
# SMIL removal — a scanner, not a paired regex. The paired form
# ``<animateX …>…</animateX>`` and the self-closing form ``<animateX …/>`` can
# coexist in one document; a lazy pair regex bridges from a self-closing
# instance to the NEXT close tag and deletes everything between them.

_SMIL_OPEN = re.compile(r"<animate[A-Za-z]*")


def _tag_end(svg: str, i: int) -> int | None:
    """Index just past the ``>`` closing the tag whose attributes start at ``i``.

    Skips quoted attribute values so a ``>`` inside a value never terminates
    the tag early. Returns None on truncated markup (left untouched).
    """
    n = len(svg)
    while i < n:
        c = svg[i]
        if c in {'"', "'"}:
            k = svg.find(c, i + 1)
            if k == -1:
                return None
            i = k + 1
            continue
        if c == ">":
            return i + 1
        i += 1
    return None


def _smil_spans(svg: str) -> list[tuple[int, int]]:
    """Byte spans of every SMIL ``<animate*>`` element outside protected spans."""
    protected = _protected_spans(svg)
    spans: list[tuple[int, int]] = []
    pos = 0
    for m in _SMIL_OPEN.finditer(svg):
        start = m.start()
        if start < pos or _inside(start, protected):
            continue
        after = svg[m.end() : m.end() + 1]
        if after not in {"", " ", "\t", "\r", "\n", ">", "/"}:
            continue
        end_open = _tag_end(svg, m.end())
        if end_open is None:
            continue
        if svg[end_open - 2 : end_open] == "/>":
            end = end_open
        else:
            name = m.group(0)[1:]
            close = svg.find(f"</{name}>", end_open)
            if close == -1:
                continue  # unmatched open tag — conservatively left alone
            end = close + len(name) + 3
        spans.append((start, end))
        pos = end
    return spans


def _delete_spans(svg: str, spans: list[tuple[int, int]]) -> str:
    if not spans:
        return svg
    out: list[str] = []
    last = 0
    for s, e in spans:
        out.append(svg[last:s])
        last = e
    out.append(svg[last:])
    return "".join(out)


# ---------------------------------------------------------------------------
# CSS scanning — a lexer over one syntactic scope (a <style> body or a style
# attribute value), never a regex over the document.

# All animation-* longhands, multi-dash included (animation-iteration-count,
# animation-timing-function) — the old single-segment pattern shipped those.
_ANIM_PROP = re.compile(r"animation(?:-[a-z]+)*\Z")
_KEYFRAMES_AT = re.compile(r"@(?:-[a-z]+-)?keyframes\b")
_ENTITY = re.compile(r"&(?:#[0-9]+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]*);")


def _skip_string(css: str, i: int) -> int:
    """Index past a CSS string starting at ``i`` (handles backslash escapes)."""
    quote = css[i]
    i += 1
    n = len(css)
    while i < n:
        c = css[i]
        if c == "\\":
            i += 2
            continue
        if c == quote:
            return i + 1
        i += 1
    return n


def _skip_comment(css: str, i: int) -> int:
    end = css.find("*/", i + 2)
    return len(css) if end == -1 else end + 2


def _strip_css_animation(css: str) -> str:
    """Remove ``@keyframes`` blocks and ``animation``/``animation-*`` declarations
    from CSS text, leaving every other byte identical.

    String-, comment-, paren-, and brace-aware; nested at-rules (``@media`` over
    keyframes, keyframes inside ``@supports``) resolve by depth counting.
    """
    drops: list[tuple[int, int]] = []
    n = len(css)
    i = 0
    depth = 0
    decl_start = -1  # start of the current declaration-ish run inside a body
    while i < n:
        c = css[i]
        if c in {'"', "'"}:
            i = _skip_string(css, i)
            continue
        if css.startswith("/*", i):
            i = _skip_comment(css, i)
            continue
        if c == "@":
            m = _KEYFRAMES_AT.match(css, i)
            if m:
                # consume prelude to '{', then the balanced block
                j = m.end()
                while j < n and css[j] != "{":
                    if css[j] in {'"', "'"}:
                        j = _skip_string(css, j)
                    elif css.startswith("/*", j):
                        j = _skip_comment(css, j)
                    else:
                        j += 1
                d = 0
                while j < n:
                    ch = css[j]
                    if ch in {'"', "'"}:
                        j = _skip_string(css, j)
                        continue
                    if css.startswith("/*", j):
                        j = _skip_comment(css, j)
                        continue
                    if ch == "{":
                        d += 1
                    elif ch == "}":
                        d -= 1
                        if d == 0:
                            j += 1
                            break
                    j += 1
                drops.append((i, j))
                i = j
                decl_start = -1
                continue
            i += 1
            continue
        if c == "{":
            depth += 1
            decl_start = i + 1
            i += 1
            continue
        if c == "}":
            depth -= 1
            decl_start = -1
            i += 1
            continue
        if c == ";":
            decl_start = i + 1
            i += 1
            continue
        if depth > 0 and decl_start >= 0 and not c.isspace():
            # at the start of a declaration: read the property name
            j = i
            while j < n and (css[j].isalnum() or css[j] == "-"):
                j += 1
            prop = css[i:j].lower()
            if _ANIM_PROP.match(prop):
                # consume the declaration value: to ';' or '}' at paren depth 0
                k = j
                paren = 0
                while k < n:
                    ch = css[k]
                    if ch in {'"', "'"}:
                        k = _skip_string(css, k)
                        continue
                    if css.startswith("/*", k):
                        k = _skip_comment(css, k)
                        continue
                    if ch == "(":
                        paren += 1
                    elif ch == ")":
                        paren = max(0, paren - 1)
                    elif paren == 0 and ch == ";":
                        k += 1  # the separator goes with the dropped declaration
                        break
                    elif paren == 0 and ch == "}":
                        break
                    k += 1
                drops.append((i, k))
                i = k
                decl_start = i
                continue
            decl_start = -1  # mid-declaration from here to the next ; or }
            i = j if j > i else i + 1
            continue
        i += 1
    return _delete_spans(css, drops)


def _strip_decl_animation(value: str) -> str:
    """Remove ``animation``/``animation-*`` declarations from a ``style``
    attribute value (a declaration list), leaving kept declarations byte-identical.

    Splits at top-level ``;`` only — paren-aware (``url(data:…;…)``), quote-aware,
    and XML-entity-aware (``&#59;`` is content, not a separator).
    """
    n = len(value)
    decls: list[tuple[int, int]] = []  # [start, end) — each including its trailing ';'
    i = 0
    start = 0
    paren = 0
    while i < n:
        c = value[i]
        if c == "&":
            m = _ENTITY.match(value, i)
            i = m.end() if m else i + 1
            continue
        if c in {'"', "'"}:
            k = value.find(c, i + 1)
            i = n if k == -1 else k + 1
            continue
        if c == "(":
            paren += 1
        elif c == ")":
            paren = max(0, paren - 1)
        elif c == ";" and paren == 0:
            decls.append((start, i + 1))
            start = i + 1
        i += 1
    if start < n:
        decls.append((start, n))

    kept: list[str] = []
    for s, e in decls:
        seg = value[s:e]
        prop = seg.split(":", 1)[0].strip().lower()
        if _ANIM_PROP.match(prop):
            continue
        kept.append(seg)
    return "".join(kept)


# ---------------------------------------------------------------------------
# Scope location — <style> bodies (CDATA-wrapped or bare) and style attributes.

_STYLE_ELEMENT = re.compile(r"(<style\b[^>]*>)(.*?)(</style>)", re.DOTALL | re.IGNORECASE)
_CDATA_BODY = re.compile(r"\A(\s*<!\[CDATA\[)(.*)(\]\]>\s*)\Z", re.DOTALL)
_STYLE_ATTR = re.compile(r"""(\bstyle\s*=\s*)("([^"]*)"|'([^']*)')""")


_SCHEME_MEDIA = re.compile(r"@media[^{]*prefers-color-scheme\s*:\s*(dark|light)[^{]*\{")


def bake_face(svg: str, face: str) -> str:
    """Commit ONE face of an adaptive artifact at projection time.

    Every ``prefers-color-scheme`` media wrapper is resolved: the selected
    face's body unwraps IN PLACE (dark rules already follow their base rules
    under the pinned cascade mechanism, so unwrapping keeps them winning by
    order), the other face's block deletes whole. Non-scheme media
    (reduced-motion, forced-colors) are untouched. The committed face stamps
    ``data-hw-face`` on the root — the same honesty mark a compose-time face
    bake carries. Byte-span edits inside ``<style>`` bodies only.
    """

    def _one(css: str) -> str:
        out: list[str] = []
        i, n = 0, len(css)
        while True:
            m = _SCHEME_MEDIA.search(css, i)
            if not m:
                out.append(css[i:])
                break
            depth, j = 1, m.end()
            while j < n and depth:
                ch = css[j]
                if ch in {'"', "'"}:
                    j = _skip_string(css, j)
                    continue
                if css.startswith("/*", j):
                    j = _skip_comment(css, j)
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                j += 1
            out.append(css[i : m.start()])
            if m.group(1) == face:
                out.append(css[m.end() : j - 1])
            i = j
        return "".join(out)

    def _sub(m: re.Match[str]) -> str:
        body = m.group(2)
        cd = _CDATA_BODY.match(body)
        body = cd.group(1) + _one(cd.group(2)) + cd.group(3) if cd else _one(body)
        return f"{m.group(1)}{body}{m.group(3)}"

    baked = _STYLE_ELEMENT.sub(_sub, svg)
    # The root's claims follow the bytes: the artifact no longer adapts, and
    # it carries a committed face — the same attribute shape a compose-time
    # face render wears (the flatten guard reads both).
    baked = re.sub(r'\s*data-hw-adapt="adaptive"', "", baked, count=1)
    # Inspect the ROOT TAG only — a title or label that happens to contain
    # the literal attribute text must not suppress the stamp.
    root_end = baked.find(">", baked.find("<svg"))
    if "data-hw-face=" not in baked[: root_end + 1]:
        baked = baked.replace('data-hw-chromatic="', f'data-hw-face="{face}" data-hw-chromatic="', 1)
    return baked


def _rewrite_style_elements(svg: str) -> str:
    def _sub(m: re.Match[str]) -> str:
        body = m.group(2)
        cd = _CDATA_BODY.match(body)
        body = cd.group(1) + _strip_css_animation(cd.group(2)) + cd.group(3) if cd else _strip_css_animation(body)
        return f"{m.group(1)}{body}{m.group(3)}"

    return _STYLE_ELEMENT.sub(_sub, svg)


def _rewrite_style_attributes(svg: str) -> str:
    """Rewrite each ``style="…"`` attribute value in isolation.

    Skips protected spans and ``<style>`` bodies (where attribute-shaped text
    would be CSS content, not markup)."""
    opaque = _protected_spans(svg)
    opaque += [m.span() for m in _STYLE_ELEMENT.finditer(svg)]

    def _sub(m: re.Match[str]) -> str:
        if _inside(m.start(), opaque):
            return m.group(0)
        quote = m.group(2)[0]
        inner = m.group(3) if m.group(3) is not None else m.group(4)
        return f"{m.group(1)}{quote}{_strip_decl_animation(inner)}{quote}"

    return _STYLE_ATTR.sub(_sub, svg)


# ---------------------------------------------------------------------------
# An element resting at opacity="0" whose body carries an <animate*> child has
# animation as its ONLY lift — stripping the child would leave permanently
# invisible dead DOM (diagram motion particles, divider takeoff boosters).
# The opacity attribute + animate-in-body conjunction IS the two-part gate:
# intentionally-static opacity-0 content has no animate child and never matches.
# The lookbehind keeps fill-opacity="0"/stroke-opacity="0" (paint channels, not
# element visibility) from false-positive whole-element deletion. The (?<!/)
# guard rejects self-closing shapes — with no body and no close tag of their
# own, a lazy match would otherwise bridge to an unrelated close tag.
_ANIMATION_ONLY_ELEMENT = re.compile(
    r'<(circle|ellipse|rect|path)\b[^>]*(?<![\w-])opacity="0"[^>]*(?<!/)>(?:(?!</\1>).)*?<animate(?:(?!</\1>).)*?</\1>\s*',
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
    animated = len(_smil_spans(svg))
    svg, dead = _delete_matches_outside(svg, _ANIMATION_ONLY_ELEMENT)
    svg, dead_groups = _delete_matches_outside(svg, _ANIMATION_ONLY_GROUP)
    dead += dead_groups
    svg = _delete_spans(svg, _smil_spans(svg))
    svg = _rewrite_style_elements(svg)
    svg = _rewrite_style_attributes(svg)
    counts: dict[str, int] = {}
    if animated:
        counts["animated_elements_stripped"] = animated
    if dead:
        counts["motion_only_elements_removed"] = dead
    return svg, counts


_HW_MOTION_TAG = re.compile(r"<hw:motion\b[^>]*>")
_HW_ENVIRONMENT_MOTION = re.compile(r'(<hw:environment\b[^>]*?)\bmotion="[^"]*"')
_HW_SPEC_PERFORMANCE = re.compile(r'(<hw:spec\b[^>]*?)\bperformance="[^"]*"')
_CONSTRAINTS_APPLIED = re.compile(r"(<hw:constraints-applied>)([^<]*)(</hw:constraints-applied>)")
_MOTION_CLAIM_ATTRS = {"vocabulary": "static", "physics": "none", "timing": "none", "stagger-regime": "none"}


def rewrite_motion_claims(svg: str) -> str:
    """Make the projected document's motion claims describe the PROJECTION.

    ``noanim`` strips every animation but used to leave the live source's
    claims behind — a static file declaring ``paint-ok`` /
    ``cim-compliant="false"`` / ``data-hw-motion="animated"`` contradicts its
    own body. Projected metadata describes the rendered projection, not its
    source, so the complete claim set rewrites: the root ``data-hw-motion``,
    ``hw:spec performance``, ``hw:environment motion``, every ``hw:motion``
    doctrine attribute (``rhythm-base`` stays — it names a genome token, not a
    clock), ``cim-compliant``, and the ``cim-compliant`` constraint token.
    """
    svg = re.sub(r'\bdata-hw-motion="[^"]*"', 'data-hw-motion="static"', svg)
    svg = _HW_SPEC_PERFORMANCE.sub(r'\1performance="composite-only"', svg)
    svg = _HW_ENVIRONMENT_MOTION.sub(r'\1motion="static"', svg)
    svg = re.sub(r'\bcim-compliant="[^"]*"', 'cim-compliant="true"', svg)

    def _still_motion_tag(m: re.Match[str]) -> str:
        tag = m.group(0)
        for attr, value in _MOTION_CLAIM_ATTRS.items():
            tag = re.sub(rf'\b{attr}="[^"]*"', f'{attr}="{value}"', tag)
        return tag

    svg = _HW_MOTION_TAG.sub(_still_motion_tag, svg)

    def _with_cim_constraint(m: re.Match[str]) -> str:
        body = m.group(2)
        if "cim-compliant" not in body:
            body = (
                body.replace(", wcag-aa", ", cim-compliant, wcag-aa")
                if ", wcag-aa" in body
                else (f"{body}, cim-compliant")
            )
        return f"{m.group(1)}{body}{m.group(3)}"

    return _CONSTRAINTS_APPLIED.sub(_with_cim_constraint, svg)


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
    "claims": rewrite_motion_claims,
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
