"""Emit-time CSS finishing — the artifact ships only the stylesheet it uses.

The measured disease (Stage 4 session A): 76% of the classes a composed
artifact declares match nothing in its own body — the genome/bridge/expression
layers are frame-generic, the artifact is specific. This pass runs once, after
the template render, and edits byte spans inside ``<style>`` bodies only:

- a rule whose every selector provably cannot match the body is dropped — a
  selector cannot match when any class or id token it names is absent from the
  document; selectors carrying functional pseudo-classes (``:not()`` and kin)
  and bare element/``:root``/attribute/``*`` selectors are conservatively
  kept;
- ``@keyframes`` whose name no kept declaration and no inline style references
  are dropped;
- a custom property declared but consumed nowhere is dropped — where
  "consumed" includes ``var()`` uses anywhere in the document, every
  ``--hw-*`` property (the state cascade reads them by name), and every token
  the artifact's own ``hw:chromatic-surface`` contract offers as an override
  point (a declared override point IS consumption; the metadata never drifts
  from the stylesheet);
- multiple ``@media (prefers-color-scheme: dark)`` blocks consolidate into the
  LAST one in emission order — safe under the pinned cascade mechanism (every
  dark rule already follows its base rule, so moving dark rules later never
  changes a winner; see ``tests/compose/test_cascade_order.py``).

Conservative by construction: anything ambiguous stays. The pass iterates to
a fixpoint (a token consumed only by a dropped declaration is itself dead the
moment that declaration goes), so the emit-time gates can hold the shipped
artifact to declared == consumed exactly, and finishing is idempotent by
construction.
"""

from __future__ import annotations

import re

_STYLE_SPAN = re.compile(r"(<style\b[^>]*>)(.*?)(</style>)", re.DOTALL | re.IGNORECASE)
_CLASS_ATTR = re.compile(r'class="([^"]*)"')
_ID_ATTR = re.compile(r'id="([^"]*)"')
_INLINE_ANIM = re.compile(r"animation(?:-name)?\s*:\s*([\w-]+)")
_VAR_USE = re.compile(r"var\(\s*(--[\w-]+)")
_CHROMATIC = re.compile(r"<hw:chromatic-surface\b.*?</hw:chromatic-surface>", re.DOTALL)
_TOKEN = re.compile(r"--[\w-]+")
_DARK_CONDITION = re.compile(r"prefers-color-scheme\s*:\s*dark")


def _skip_string(css: str, i: int) -> int:
    quote = css[i]
    i += 1
    n = len(css)
    while i < n:
        if css[i] == "\\":
            i += 2
            continue
        if css[i] == quote:
            return i + 1
        i += 1
    return n


def _skip_comment(css: str, i: int) -> int:
    end = css.find("*/", i + 2)
    return len(css) if end == -1 else end + 2


def _blocks(css: str) -> list[tuple[str, int, int, int]]:
    """Top-level constructs as ``(kind, start, body_start, end)`` — kind is
    ``at`` (any @-rule with a block), ``atline`` (@import; style), ``comment``
    (a comment between constructs — kept verbatim, they carry assembly
    markers), or ``rule``. String-aware; nested braces balanced."""
    out: list[tuple[str, int, int, int]] = []
    n = len(css)
    i = 0
    start = -1
    while i < n:
        c = css[i]
        if c in {'"', "'"}:
            i = _skip_string(css, i)
            continue
        if css.startswith("/*", i):
            if start == -1:
                end_c = _skip_comment(css, i)
                out.append(("comment", i, i, end_c))
                i = end_c
                continue
            i = _skip_comment(css, i)
            continue
        if start == -1 and not c.isspace():
            start = i
        if c == ";" and start != -1 and css[start] == "@":
            out.append(("atline", start, start, i + 1))
            start = -1
            i += 1
            continue
        if c == "{":
            depth = 1
            j = i + 1
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
            kind = "at" if css[start] == "@" else "rule"
            out.append((kind, start if start != -1 else i, i, j))
            start = -1
            i = j
            continue
        i += 1
    return out


def _selector_can_match(selector: str, classes: set[str], ids: set[str]) -> bool:
    if re.search(r":(?:not|is|where|has)\(", selector):
        return True  # negation can match precisely when its argument is absent
    if any(c not in classes for c in re.findall(r"\.([\w-]+)", selector)):
        return False
    # Element, *, :root, attribute, pseudo compounds are conservatively kept.
    return all(i in ids for i in re.findall(r"#([\w-]+)", selector))


def _filter_css(css: str, classes: set[str], ids: set[str], keep_anim: set[str], consumed: set[str]) -> str:
    kept: list[str] = []
    keyframes: list[tuple[str, str]] = []  # (name, text) — resolved second pass
    for kind, start, body_start, end in _blocks(css):
        text = css[start:end]
        head = css[start:body_start]
        if kind in {"atline", "comment"}:
            kept.append(text)
            continue
        if kind == "at":
            if head.lstrip().startswith(("@keyframes", "@-webkit-keyframes")):
                name = head.split()[-1].strip()
                keyframes.append((name, text))
                kept.append(f"\x00KF:{name}\x00")
                continue
            if head.lstrip().startswith("@media"):
                inner_text = css[body_start + 1 : end - 1]
                inner = _filter_css(inner_text, classes, ids, keep_anim, consumed)
                if inner == inner_text:
                    kept.append(text)
                elif inner.strip():
                    kept.append(head + "{" + inner + "}")
                continue
            kept.append(text)  # @font-face and anything else: verbatim
            continue
        selectors = head.split(",")
        alive = [s for s in selectors if _selector_can_match(s, classes, ids)]
        if not alive:
            continue
        body = css[body_start + 1 : end - 1]
        pruned = re.sub(
            r"(--[\w-]+)\s*:\s*[^;{}]+;?",
            lambda m: "" if (m.group(1) not in consumed and not m.group(1).startswith("--hw-")) else m.group(0),
            body,
        )
        if not pruned.strip():
            continue
        if len(alive) == len(selectors) and pruned == body:
            kept.append(text)  # untouched rules keep their exact bytes
            continue
        head = ",".join(alive)
        if not head.endswith((" ", "\n")):
            head += " "
        kept.append(head + "{" + pruned + "}")

    text = "\n".join(kept)
    referenced = set(keep_anim) | set(_INLINE_ANIM.findall(text))
    for name, kf_text in keyframes:
        text = text.replace(f"\x00KF:{name}\x00", kf_text if name in referenced else "")
    return text


def _consolidate_dark(css: str) -> str:
    """Merge every dark media block's body into the LAST one, in order."""
    spans = [
        (start, body_start, end)
        for kind, start, body_start, end in _blocks(css)
        if kind == "at"
        and css[start:body_start].lstrip().startswith("@media")
        and _DARK_CONDITION.search(css[start:body_start])
    ]
    if len(spans) < 2:
        return css
    bodies = [css[b + 1 : e - 1] for _s, b, e in spans]
    merged = "\n".join(bodies)
    out: list[str] = []
    last = 0
    for idx, (s, b, e) in enumerate(spans):
        out.append(css[last:s])
        if idx == len(spans) - 1:
            out.append(css[s : b + 1] + merged + css[e - 1 : e])
        last = e
    out.append(css[last:])
    return "".join(out)


def finish_css(svg: str) -> str:
    """Shake unused rules, GC unreferenced keyframes and tokens, consolidate
    dark media blocks. Byte-span edits inside ``<style>`` bodies only."""
    for _ in range(6):
        finished = _finish_once(svg)
        if finished == svg:
            return finished
        svg = finished
    return svg


def _finish_once(svg: str) -> str:
    style_spans = [m.span(2) for m in _STYLE_SPAN.finditer(svg)]
    if not style_spans:
        return svg
    body = svg
    for s, e in reversed(style_spans):
        body = body[:s] + body[e:]

    classes: set[str] = set()
    for value in _CLASS_ATTR.findall(body):
        classes.update(value.split())
    ids = set(_ID_ATTR.findall(body))
    inline_anim = set(_INLINE_ANIM.findall(body))
    consumed = set(_VAR_USE.findall(svg))
    for block in _CHROMATIC.findall(svg):
        consumed.update(_TOKEN.findall(block))

    def _sub(m: re.Match[str]) -> str:
        finished = _filter_css(m.group(2), classes, ids, inline_anim, consumed)
        finished = _consolidate_dark(finished)
        return f"{m.group(1)}{finished}{m.group(3)}"

    return _STYLE_SPAN.sub(_sub, svg)
