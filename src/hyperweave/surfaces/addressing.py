"""Project a :class:`ComposeSpec` onto each surface's address for it.

One spec describes one artifact. Reaching that artifact over HTTP needs a URL,
over MCP a ``hw_compose`` kwargs dict, over the CLI an argv list — three
renderings of a single intent. Written by hand they drift, and the cost of
writing them caps how much of the corpus can be checked for parity at all:
before this module the proofset's parity matrix hand-wrote all three for every
entry, which is why 204 specs were surface-checked and ~1100 were not.

    >>> spec_to_url(ComposeSpec(type="badge", genome_id="chrome", variant="horizon", title="PYPI", value="v0.3.0"))
    '/v1/badge/PYPI/v0.3.0/chrome.static?variant=horizon'

Route patterns and the segment/query field mapping come from
``data/config/url-grammar.yaml`` (Invariant 5) — never from literals here.

**Not every spec is addressable on every surface**, and that is information
rather than an error to swallow: a spec carrying pre-resolved data tokens
cannot go through the token grammar (which would re-fetch), and a receipt's
transcript payload does not fit in a path. Those raise :class:`Unaddressable`
with a reason string, so a caller sweeping the corpus can print an
addressability audit instead of silently skipping. Same discipline
``surfaces/registry.py:register()`` enforces when a capability has no MCP tool.
"""

from __future__ import annotations

import base64
import json
import re
from enum import Enum
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, urlencode

from hyperweave.config.loader import load_url_grammar

if TYPE_CHECKING:
    from hyperweave.core.models import ComposeSpec

__all__ = [
    "Unaddressable",
    "canonical_spec",
    "normalize_artifact",
    "spec_to_cli_argv",
    "spec_to_mcp_args",
    "spec_to_url",
]


# ── Volatile fragments ───────────────────────────────────────────────────────
# Which parts of a composed artifact legitimately differ between two renders of
# the same spec. This travels with addressing because it is the other half of
# the same contract: an address is correct when what it returns matches a
# direct compose EXCEPT here. Kept in one place — the pack previously lived as
# three verbatim copies (the URL-stability snapshot test, the proofset parity
# harness, the cross-surface sweep), each a chance for one comparison to grow
# stricter than another and fail for a reason that is not a defect.

# Short UUID fragments embedded in element IDs/classes (e.g. hw-ebd30b0c-title).
_HW_UID_RE = re.compile(r"hw-[0-9a-f]{6,}")
# Full UUID v4 inside data-hw-id, data-hw-contract, hw:artifact id (no hw- prefix).
_FULL_UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
# ISO 8601 timestamps in metadata (created / created_at).
_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")
# Package version strings — __version__ comes from git tags, so the same code
# renders "0.2.20" on an untagged tree and "0.4.2" on a tagged one. The regex is
# precise rather than permissive: SVG path data packs numbers as
# `8.205 .113.82-.258.82-.577`, and only true PEP 440 suffixes (aN/bN/rcN,
# .devN/.postN/.preN, -rcN, +local) may extend the match — a bare `.NNN` path
# coordinate must not be consumed as one.
_VERSION_RE = re.compile(
    r"\d+\.\d+\.\d+"
    r"(?:[a-zA-Z]+\d+)?"  # adjacent pre-release: a1, b1, rc1
    r"(?:\.(?:dev|post|pre)\d*)?"  # PEP 440 .devN/.postN/.preN
    r"(?:[-+][0-9a-zA-Z.\-+]+)?"  # legacy -pre or +local (chained)
)
# Font subsetting is content-derived: the glyph set follows every digit and
# letter that appears in rendered text, including the volatile UID and
# timestamp above, so two renders of one artifact carry slightly different
# woff2 bytes. Compare the structural SVG, not the font payload.
_FONT_DATA_RE = re.compile(r"data:font/woff2;base64,[A-Za-z0-9+/=]+")


def normalize_artifact(svg: str) -> str:
    """Scrub volatile fragments so two renders of one spec compare equal.

    What survives is everything a caller could notice: geometry, chromatics,
    text, structure, payload. What goes is identity and provenance that is
    per-render by design.
    """
    svg = _HW_UID_RE.sub("hw-UID", svg)
    svg = _FULL_UUID_RE.sub("UUID", svg)
    svg = _TS_RE.sub("TIMESTAMP", svg)
    svg = _VERSION_RE.sub("VERSION", svg)
    return _FONT_DATA_RE.sub("data:font/woff2;base64,<<FONT>>", svg)


class Unaddressable(Exception):
    """A spec no address on this surface can express — carries why.

    ``surface`` is the label ("http" | "mcp" | "cli"); ``str(exc)`` is a
    reason written for a human reading a coverage report.
    """

    def __init__(self, surface: str, reason: str) -> None:
        super().__init__(reason)
        self.surface = surface
        self.reason = reason


# The path stand-in for a segment whose real value carries a slash; the route
# reads the value from the escape query param instead (``?t=``). Matches the
# convention already in the proofset's hand-written slashed-title entries.
_SLASH_STANDIN = "_"


def _plain(value: Any) -> Any:
    """Enum → its value; everything else unchanged."""
    return value.value if isinstance(value, Enum) else value


def _field(spec: ComposeSpec, dotted: str) -> Any:
    """Read a (possibly dotted) spec field. Missing intermediate → None.

    Dotted paths address the one nested case in the grammar: the strip's
    ``?subtitle=`` lands at ``connector_data.repo_slug``.
    """
    current: Any = spec
    for part in dotted.split("."):
        if current is None:
            return None
        current = current.get(part) if isinstance(current, dict) else getattr(current, part, None)
    return _plain(current)


def _payload_dict(value: Any) -> dict[str, Any]:
    """A matrix/diagram payload as a plain JSON-able dict."""
    if isinstance(value, dict):
        return dict(value)
    dumped = value.model_dump(mode="json", exclude_none=True)
    return dict(dumped)


def _b64url_json(payload: dict[str, Any]) -> str:
    """Compact JSON → unpadded base64url (the ``?spec=`` wire form)."""
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unaddressable_reason(spec: ComposeSpec) -> str:
    """Why no surface-independent address exists for this spec, or ""."""
    if _live_token_kinds(spec):
        kinds = ", ".join(_live_token_kinds(spec))
        return (
            f"carries tokens resolved from a live provider ({kinds}); re-requesting them through "
            "the ?data= / --data grammar would fetch again, comparing a pinned value against a "
            "fresh one rather than comparing the surfaces"
        )
    if spec.genome_override:
        return "carries an inline genome override; only the direct compose() path accepts one"
    return ""


# Token kinds that are LITERAL — their payload is the value, so writing them
# back into the grammar reproduces the same tokens with no network. Everything
# else names a provider and would re-fetch. Distinguishing the two is what lets
# a marquee of `kv:` cells be addressed while a marquee of `gh:` cells is
# honestly refused; treating all tokens alike refused 4 parity specs that round
# trip perfectly.
_LITERAL_TOKEN_KINDS: frozenset[str] = frozenset({"kv", "text"})


def _live_token_kinds(spec: ComposeSpec) -> list[str]:
    """The distinct non-literal token kinds this spec carries, sorted."""
    kinds = {str(getattr(t, "kind", "")) for t in (spec.data_tokens or [])}
    return sorted(k for k in kinds - _LITERAL_TOKEN_KINDS if k)


def _tokens_to_grammar(spec: ComposeSpec) -> str:
    """Serialize literal tokens back into the ``data=`` grammar.

    The inverse of ``connectors.data_tokens._parse_one`` for the literal kinds:
    ``text:PAYLOAD`` and ``kv:KEY=VALUE`` with an optional ``~WINDOW`` suffix.
    Embedded commas escape as ``\\,`` — the payload is the value, so a comma
    inside it must not read as the next token.
    """

    def esc(text: str) -> str:
        return str(text).replace(",", "\\,")

    parts: list[str] = []
    for token in spec.data_tokens or []:
        kind = str(getattr(token, "kind", ""))
        if kind == "text":
            parts.append(f"text:{esc(getattr(token, 'value', ''))}")
            continue
        value = esc(getattr(token, "value", ""))
        window = str(getattr(token, "window", "") or "")
        parts.append(f"kv:{esc(getattr(token, 'label', ''))}={value}{f'~{esc(window)}' if window else ''}")
    return ",".join(parts)


def canonical_spec(spec: ComposeSpec) -> ComposeSpec:
    """``spec`` with the route's own field derivations applied.

    A route that has no segment for a field fills it from one it does have —
    ``/v1/icon/{glyph}/…`` names the artifact after its glyph, so an icon
    fetched by URL carries ``title == glyph`` no matter what the caller left
    empty. Composing a spec directly skips that step, and the two renders then
    differ in ``<title>``. Canonicalize once at declaration time and every
    surface agrees; skip it and :func:`spec_to_url` refuses the address rather
    than hand back one that returns a different artifact.

    A spec with nothing to derive is returned unchanged.
    """
    route = load_url_grammar()["routes"].get(str(_plain(spec.type)))
    derives: dict[str, str] = (route or {}).get("derives") or {}
    filled = {target: getattr(spec, source) for target, source in derives.items() if not getattr(spec, target)}
    return spec.model_copy(update=filled) if filled else spec


def spec_to_url(spec: ComposeSpec, *, base_url: str = "") -> str:
    """The GET image URL that renders ``spec``.

    Raises :class:`Unaddressable` when the frame has no image route, when a
    required path segment is empty (an empty segment does not route), when a
    declared derivation does not hold (run :func:`canonical_spec` first), or
    when the spec carries payload only the direct path accepts.
    """
    grammar = load_url_grammar()
    frame = str(_plain(spec.type))
    route = grammar["routes"].get(frame)
    if route is None:
        reason = grammar["unrouted"].get(frame) or f"no GET image route declared for frame {frame!r}"
        raise Unaddressable("http", reason)
    if reason := _unaddressable_reason(spec):
        raise Unaddressable("http", reason)
    for target, source in (route.get("derives") or {}).items():
        if getattr(spec, target) != getattr(spec, source):
            raise Unaddressable(
                "http",
                f"the {frame} route derives {target} from {source}, so this URL would return "
                f"{target}={getattr(spec, source)!r} rather than {getattr(spec, target)!r} "
                f"— pass the spec through canonical_spec() first",
            )
    if spec.chrome != "caption":
        raise Unaddressable("http", f"chrome={spec.chrome!r} has no query parameter on the image routes")

    segments: dict[str, Any] = route.get("segments") or {}
    query_decl: dict[str, Any] = route.get("query") or {}
    escaped: dict[str, str] = {}

    path = str(route["pattern"])
    for name, decl in segments.items():
        if "const" in decl:
            # A constant segment can depend on a query param being fillable:
            # `/v1/matrix/custom/...` is only a valid address when ?spec= carries
            # the table. A spec that points at a server-side adapter instead
            # (connector_data={"matrix_adapter": ...}) has its content on the
            # server under a PRESET SLUG, and the slug is not something the spec
            # records — so no URL is derivable, and emitting `custom` with no
            # ?spec= would hand back an address the route answers 400 to.
            needs = str(decl.get("requires_query") or "")
            if needs:
                paired = str((query_decl.get(needs) or {}).get("field") or "")
                if paired and _field(spec, paired) is None:
                    raise Unaddressable(
                        "http",
                        f"the {frame} route needs either a preset slug or an inline ?{needs}=, and "
                        f"this spec carries neither — its content comes from a server-side adapter "
                        f"({', '.join(sorted(spec.connector_data or {})) or 'none named'}), whose "
                        "preset slug a spec does not record",
                    )
            value = str(decl["const"])
        else:
            raw = _field(spec, str(decl["field"]))
            value = "" if raw is None else str(raw)
            if not value:
                raise Unaddressable("http", f"path segment {{{name}}} needs spec.{decl['field']}, which is empty")
            if "/" in value:
                escaped[str(decl["escape_query"])] = value
                value = _SLASH_STANDIN
        path = path.replace(f"{{{name}}}", quote(value, safe=""))
    path = path.replace("{genome}", quote(spec.genome_id, safe="")).replace(
        "{motion}", quote(str(_plain(spec.motion)), safe="")
    )

    # A param that exists only to carry a slashed segment (``?t=``) rides
    # along ONLY when the escape actually fired; emitting it otherwise would
    # duplicate the title into every URL.
    escape_params = {str(d["escape_query"]) for d in segments.values() if "escape_query" in d}

    params: list[tuple[str, str]] = []
    for param, decl in query_decl.items():
        if param in escape_params:
            if param in escaped:
                params.append((param, escaped[param]))
            continue
        field = decl.get("field")
        if not field:  # doc-only parameter (no spec field behind it)
            continue
        raw = _field(spec, str(field))
        if raw is None or raw == "" or raw == decl.get("default"):
            continue
        if decl.get("encode") == "base64url-json":
            payload = json.dumps(_payload_dict(raw), separators=(",", ":")).encode()
            cap = int(decl.get("max_decoded_bytes") or 0)
            if cap and len(payload) > cap:
                # The route rejects an oversize inline payload with a 400. Refuse
                # here instead of handing back a URL that fails on use: a big
                # table reaches HTTP through a server-known preset slug, which
                # the spec does not record, so no URL can be derived for it.
                raise Unaddressable(
                    "http",
                    f"the {field} payload is {len(payload)} bytes, past the {cap}-byte inline "
                    f"?{param}= cap; a table this size is served by a preset slug, which a spec "
                    "does not carry",
                )
            params.append((param, _b64url_json(_payload_dict(raw))))
        else:
            params.append((param, str(raw)))

    # Literal tokens ride the data grammar. The YAML marks `data` doc-only
    # because whether it can be filled depends on the token KINDS, not on a
    # field being non-empty — that judgement lives here.
    if spec.data_tokens and "data" in query_decl:
        params.append(("data", _tokens_to_grammar(spec)))

    # Sorted so the same spec always yields the same URL — a stable address is
    # what makes the artifact cacheable and the coverage report diffable.
    query = urlencode(sorted(params))
    return f"{base_url}{path}" + (f"?{query}" if query else "")


# ComposeSpec field -> hw_compose parameter, where the two names differ. Every
# other shared field passes through under its own name.
_MCP_RENAMES: dict[str, str] = {
    "genome_id": "genome",
    "marquee_direction": "direction",
    "marquee_speeds": "speeds",
    "surface_face": "face",
}

# Fields that are not part of the compositional INTENT: derived at validation
# (``profile_id`` resolves from the genome), structural containers the surfaces
# fill themselves (``slots``), or provenance/metadata knobs no surface exposes.
# Skipped on every projection — including them would put a value the caller
# never asked for into the address.
_NOT_INTENT: frozenset[str] = frozenset(
    {
        "chrome",
        "frame_id",
        "profile_id",
        "slots",
        "custom_glyph_svg",
        "intent",
        "approach",
        "tradeoffs",
        "numeric_value",
        "threshold_id",
        "generation",
        "metadata_tier",
        "series",
        "platform",
        "receipt_display_name",
    }
)


def spec_to_mcp_args(spec: ComposeSpec) -> dict[str, Any]:
    """``hw_compose`` kwargs equivalent to ``spec``.

    Only fields that differ from their default are emitted, so the args read
    as the request actually made rather than a full-field dump. Callers add
    ``respond`` themselves — that is a response-shape choice, not part of the
    compositional intent.
    """
    from hyperweave.core.models import ComposeSpec as _Spec

    if reason := _unaddressable_reason(spec):
        raise Unaddressable("mcp", reason)
    if spec.chrome != "caption":
        raise Unaddressable("mcp", f"chrome={spec.chrome!r} is not a hw_compose parameter")

    args: dict[str, Any] = {}
    for name, model_field in _Spec.model_fields.items():
        # data_tokens goes out as the `data` grammar string below — hw_compose
        # has no data_tokens parameter, and passing one is a hard validation
        # error rather than a silent drop.
        if name in _NOT_INTENT or name == "data_tokens":
            continue
        value = _plain(getattr(spec, name))
        if value is None or value == "" or value == _plain(model_field.default):
            continue
        if name in ("matrix", "diagram"):
            value = _payload_dict(getattr(spec, name))
        args[_MCP_RENAMES.get(name, name)] = value
    if spec.data_tokens:
        args["data"] = _tokens_to_grammar(spec)
    # `type` is required by the tool even when it equals the model default.
    args["type"] = str(_plain(spec.type))
    return args


# ComposeSpec field -> `hyperweave compose` flag. Fields absent from this map
# are either positional (title/value), unsupported (see _CLI_ABSENT), or at
# their default and therefore omitted.
_CLI_FLAGS: dict[str, str] = {
    "genome_id": "--genome",
    "state": "--state",
    "motion": "--motion",
    "glyph": "--glyph",
    "glyph_mode": "--glyph-mode",
    "regime": "--regime",
    "size": "--size",
    "shape": "--shape",
    "variant": "--variant",
    "pair": "--pair",
    "state_glyph_shape": "--state-glyph-shape",
    "divider_variant": "--divider-variant",
    "marquee_direction": "--direction",
    "glyph_tint": "--glyph-tint",
    "performance": "--performance",
    "font_mode": "--font-mode",
    "ground": "--ground",
    "palette": "--palette",
    "surface_face": "--face",
}

# Fields the compose command cannot express. Named with the reason the audit
# should print — a gap stated is a gap that can be closed. (`connector_data`
# used to sit here: the sweep counted 300+ strips the CLI could not address,
# which is what prompted adding `--subtitle`.)
_CLI_ABSENT: dict[str, str] = {
    "telemetry_data": "receipts take a transcript path positionally, not an inline payload",
    "marquee_speeds": "no --speeds flag on `compose`",
}

# Spec fields the CLI reaches through a flag that does not carry the whole
# field. `connector_data` is an adapter payload — a fetched stats blob, a
# bundled matrix spec — of which exactly one key, the strip's subtitle, has a
# flag. Anything else in there is genuinely unaddressable and says so.
_CLI_PARTIAL: dict[str, tuple[str, str, str]] = {
    # field: (only-supported key, flag, reason when other keys are present)
    "connector_data": (
        "repo_slug",
        "--subtitle",
        "carries fetched connector payload beyond the strip subtitle; `compose` has no flag for it",
    ),
}

# `compose FRAME [TITLE] [VALUE]` — which spec fields those two positionals
# carry, per frame. Declared rather than assumed: the icon command takes the
# artifact's TITLE positionally and its glyph through --glyph (the glyph-named
# path segment is an HTTP-route convention, not a CLI one), and the card/stats
# command reads its username from the title slot.
_CLI_POSITIONAL: dict[str, tuple[str, ...]] = {
    "badge": ("title", "value"),
    "strip": ("title", "value"),
    "marquee": ("title",),
    "icon": ("title",),
    "divider": (),
    "matrix": (),
    "diagram": (),
    "stats": ("stats_username",),
    # `compose receipt <transcript.jsonl>` — the positional is a FILE PATH, not
    # a spec field, so nothing maps here. Listed anyway: without an entry the
    # projection stops at "positional order is not declared", a generic message
    # that hides the real and more useful one (`telemetry_data` in _CLI_ABSENT:
    # receipts take a path, not an inline payload).
    "receipt": (),
}


def spec_to_cli_argv(spec: ComposeSpec) -> list[str]:
    """``hyperweave compose`` argv (without the program name) for ``spec``.

    Matrix/diagram payloads ride ``--spec`` as inline JSON, which is what the
    command documents for a spec that is not a bundled preset.
    """
    from hyperweave.core.models import ComposeSpec as _Spec

    if reason := _unaddressable_reason(spec):
        raise Unaddressable("cli", reason)
    if spec.chrome != "caption":
        raise Unaddressable("cli", f"chrome={spec.chrome!r} is not a `compose` flag")

    frame = str(_plain(spec.type))
    positional = _CLI_POSITIONAL.get(frame)
    if positional is None:
        raise Unaddressable("cli", f"positional argument order for frame {frame!r} is not declared")

    positionals: list[str] = []
    for name in positional:
        value = str(_plain(getattr(spec, name)) or "")
        if not value:
            break  # trailing optionals; a hole would shift later positions
        positionals.append(value)

    options: list[str] = []
    consumed = set(positional)
    for name, model_field in _Spec.model_fields.items():
        value = _plain(getattr(spec, name))
        if value is None or value == "" or value == _plain(model_field.default):
            continue
        if name in consumed or name == "type" or name in _NOT_INTENT:
            continue
        if name == "data_tokens":
            options += ["--data", _tokens_to_grammar(spec)]
            continue
        if name in _CLI_ABSENT:
            raise Unaddressable("cli", _CLI_ABSENT[name])
        if name in _CLI_PARTIAL:
            key, flag, reason = _CLI_PARTIAL[name]
            payload = getattr(spec, name) or {}
            if set(payload) - {key}:
                raise Unaddressable("cli", reason)
            options += [flag, str(payload[key])]
            continue
        if name in ("matrix", "diagram"):
            options += ["--spec", json.dumps(_payload_dict(getattr(spec, name)), separators=(",", ":"))]
            continue
        field_flag = _CLI_FLAGS.get(name)
        if field_flag is None:
            raise Unaddressable("cli", f"no `compose` flag carries spec.{name}")
        options += [field_flag, str(value)]

    # A positional whose VALUE starts with a dash would be read as an option —
    # and `--` alone is the POSIX end-of-options marker, so a badge whose value
    # is the "--" placeholder for an unresolved metric silently swallowed every
    # flag after it and exited 2. Options first, then the separator, then the
    # positionals, but only when one of them needs the protection: the common
    # argv stays the readable thing a person would actually type.
    if any(p.startswith("-") for p in positionals):
        return [frame, *options, "--", *positionals]
    return [frame, *positionals, *options]
