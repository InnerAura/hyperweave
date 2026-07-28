"""The unified compose surface — one spec shape in, one response shape out.

Architectural Invariant 9: CLI, MCP, and HTTP all accept the same
:class:`SpecEnvelope` and return the same :class:`ResponseEnvelope`, so the three
wires are thin adapters over this single core. ``compose_surface`` is that core —
the compose capability handler (``surfaces/capabilities.py``) resolves live
``data`` tokens (async, frame-aware) and then calls it.

It builds a ``ComposeSpec``, renders once, projects to the requested ``format``,
caches the SVG under its content digest, and returns ``{envelope, url, ...}`` per
the requested ``emit`` targets — never forcing the inline SVG on a caller that
only wants the actionable envelope.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field, ValidationError

from hyperweave.compose.artifact_store import store_artifact
from hyperweave.compose.engine import compose
from hyperweave.core.base import FrozenModel
from hyperweave.core.defaults import default_genome
from hyperweave.core.diagram import DiagramSpec
from hyperweave.core.enums import FrameType
from hyperweave.core.envelope import extract_envelope, extract_payload
from hyperweave.core.errors import HwError, HwErrorCode, format_error_line
from hyperweave.core.matrix import MatrixSpec
from hyperweave.core.models import ComposeSpec
from hyperweave.formats import FormatId, Projection, parse_format, project

# Frame content that maps to a dedicated ComposeSpec field rather than a kwarg.
_IR_FIELD: dict[str, str] = {"matrix": "matrix", "diagram": "diagram"}


def split_dotted_genome(genome: str, variant: str) -> tuple[str, str]:
    """Split a dotted ``genome.variant`` into ``(genome, variant)``.

    A separate ``variant`` alongside a dotted genome is a caller error when
    they disagree (a silent pick would hide the conflict); agreeing values
    pass. Input without a dot passes through untouched, so the call is
    idempotent — the CLI pre-splits for flag-precedence bookkeeping and
    :func:`resolve_presentation` splits again for the other surfaces.
    """
    if "." not in genome:
        return genome, variant
    base, _, dotted_variant = genome.partition(".")
    if variant and dotted_variant and variant != dotted_variant:
        raise HwError(
            HwErrorCode.SPEC_INVALID,
            f"genome {genome!r} sets variant {dotted_variant!r}, but variant {variant!r} was also given",
            fix="pass the dotted genome OR a separate variant — or make them agree",
        )
    return base, (variant or dotted_variant)


def resolve_presentation(
    frame_type: str, genome: str, variant: str, *, genome_override: dict[str, Any] | None = None
) -> tuple[str, str]:
    """The ONE presentation-resolution step both verbs on all three surfaces run.

    Raw caller input to canonical ``(genome_id, variant)``, or a structured
    refusal — validate and compose cannot disagree on anything resolved here:

    1. empty genome → :func:`default_genome` (primer, every frame);
    2. dotted ``genome.variant`` splits (conflicting separate variant refused);
    3. unknown genome → ``GENOME_UNKNOWN`` naming the registry;
    4. frame support: the genome must declare ``paradigms.<frame>`` — except a
       receipt on a non-receipt-capable genome, which canonicalizes to primer
       (the resolver's designed fallback), never refuses;
    5. a non-empty variant outside the genome's whitelist → ``VARIANT_UNKNOWN``.

    ``variant`` may return ``""`` — the flagship/paradigm default resolves at
    render time (``resolver.resolve_variant``'s Path-B chain, unchanged). A
    ``genome_override`` dict (``--genome-file`` / ``genome_override``) IS the
    genome: registry existence is skipped, frame support and the variant
    whitelist read the override itself.
    """
    from hyperweave.config.loader import get_loader

    genome = genome or default_genome(frame_type)
    genome, variant = split_dotted_genome(genome, variant)
    frame = "stats" if frame_type == "card" else frame_type

    if genome_override is not None:
        g: dict[str, Any] = genome_override
    else:
        genomes = get_loader().genomes
        maybe = genomes.get(genome)
        if maybe is None:
            raise HwError(
                HwErrorCode.GENOME_UNKNOWN,
                f"unknown genome {genome!r}",
                fix=f"known genomes: {', '.join(sorted(genomes))}",
            )
        g = maybe

    if frame == "receipt":
        from hyperweave.compose.resolver import genome_supports_receipts

        if not genome_supports_receipts(genome, genome_override):
            genome, g = default_genome(frame), get_loader().genomes[default_genome(frame)]
    elif frame in _FRAME_TYPES and frame not in (g.get("paradigms") or {}):
        # Unknown frame TYPES fall through untouched — ComposeSpec's own
        # validation names them TYPE_UNKNOWN; a frame-support message for a
        # frame that doesn't exist would be a misdiagnosis.
        if genome_override is not None:
            raise HwError(
                HwErrorCode.SPEC_INVALID,
                f"{frame} frame is not supported by genome {genome!r} (no paradigms.{frame} entry)",
            )
        supporting = sorted(gid for gid, gg in get_loader().genomes.items() if frame in (gg.get("paradigms") or {}))
        raise HwError(
            HwErrorCode.SPEC_INVALID,
            f"{frame} frame is not supported by genome {genome!r}",
            fix=f"use a genome that supports {frame}: {', '.join(supporting)}" if supporting else "",
        )

    allowed = list(g.get("variants") or [])
    if allowed and variant and variant not in allowed:
        raise HwError(
            HwErrorCode.VARIANT_UNKNOWN,
            f"unknown variant {variant!r} for genome {genome!r}",
            fix=f"known variants: {', '.join(allowed)}",
        )
    return genome, variant


# ComposeSpec top-level field names that a caller may pack into `spec` ALONGSIDE
# an IR frame's schema (e.g. matrix + connector_data, diagram + chrome/
# performance). Derived from the model so any hw_compose param that is a real
# ComposeSpec field forwards through the envelope without a hand-maintained list.
# `type`/`genome_id`/`variant`/`data_tokens` are supplied by the envelope mapping
# directly; the IR field names are excluded so the nested schema still lands in
# `matrix`/`diagram`.
_COMPOSE_FIELDS: frozenset[str] = frozenset(ComposeSpec.model_fields) - {
    "matrix",
    "diagram",
    "type",
    "genome_id",
    "variant",
    "data_tokens",
}

# Fields a matrix/diagram IR schema declares under names that collide with a
# ComposeSpec field (title on both; glyph_tint on diagram). These stay in the IR
# content — never lifted to a top-level ComposeSpec kwarg — so a matrix's `title`
# heads the table rather than becoming a badge label. Per-frame liftable sets
# subtract these from `_COMPOSE_FIELDS`.
_LIFTABLE_BY_IR: dict[str, frozenset[str]] = {
    "matrix": _COMPOSE_FIELDS - frozenset(MatrixSpec.model_fields),
    "diagram": _COMPOSE_FIELDS - frozenset(DiagramSpec.model_fields),
}

# emit targets understood by the surface (png bytes ride the `format` axis, not emit).
# `faces` is twin-only — it bakes the light + dark faces as two plate artifacts and
# returns their content-addressed URLs (the <picture> pair). See `_emit_faces`.
_VALID_EMIT = {"svg", "md", "payload", "compressed", "faces"}

# Known frame types incl. the `card` alias (accepted, canonicalized to stats).
_FRAME_TYPES = {f.value for f in FrameType} | {"card"}


class SpecEnvelope(FrozenModel):
    """The canonical compose input, identical across every transport."""

    type: str
    genome: str = ""
    """Empty resolves through :func:`resolve_presentation` (primer, any frame)."""
    variant: str = ""
    spec: dict[str, Any] = Field(default_factory=dict)
    data: str = ""
    format: str = "svg"
    emit: tuple[str, ...] = ("svg",)


class ResponseEnvelope(FrozenModel):
    """The canonical compose output. Default emit (svg) returns just the bytes;
    multi-target emit returns the full dict so an agent reads the envelope and
    embeds the url without the pixels ever entering its context.

    ``envelope`` is the always-present actionable read (the hwz/1 seed); ``svg``
    carries the projected SVG text for SVG formats (empty for raster — the caller
    fetches those bytes from ``url``). ``compressed`` is the emit-gated copy of
    the envelope for callers that explicitly requested it."""

    envelope: dict[str, Any] = Field(default_factory=dict)
    svg: str = ""
    md: str = ""
    payload: dict[str, Any] | None = None
    compressed: dict[str, Any] | None = None
    width: int = 0
    height: int = 0
    genome: str = ""
    variant: str = ""
    url: str = ""
    faces: dict[str, str] | None = None
    """Twin only: ``{"light": url, "dark": url}`` — the two baked faces' content-
    addressed handles (each a plain plate). Present when ``faces`` is emitted on an
    adaptive twin; feeds ``delivery.embed.embed_snippets`` as ``[dark, light]``."""
    warnings: tuple[str, ...] = ()
    """Non-fatal normalization notes (cyclic-dag promotion, motion ladder)."""
    diagnostics: tuple[dict[str, str], ...] = ()
    """sec 6 compiler diagnostics: advisory {rule, measured, band, suggestion}
    records — identical on CLI stderr, HTTP JSON, and MCP."""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "width": self.width,
            "height": self.height,
            "genome": self.genome,
            "variant": self.variant,
            "url": self.url,
            "envelope": self.envelope,
        }
        if self.svg:
            out["svg"] = self.svg
        if self.md:
            out["md"] = self.md
        if self.payload is not None:
            out["payload"] = self.payload
        if self.compressed is not None:
            out["compressed"] = self.compressed
        if self.faces is not None:
            out["faces"] = self.faces
        if self.warnings:
            out["warnings"] = list(self.warnings)
        if self.diagnostics:
            out["diagnostics"] = list(self.diagnostics)
        return out


def build_artifact_url(digest: str, base_url: str = "", fmt: str = "svg") -> str:
    """Content-addressed handle for a digest, optionally in a derived format.

    ``fmt="svg"`` yields the bare ``/v1/a/{hex}`` handle (the live artifact);
    any other format appends the projection suffix (``.static.svg`` / ``.png`` /
    ``.webp`` / ``.gif``) so the derived-projection route serves it.
    """
    hexd = digest.split(":", 1)[1] if digest.startswith("sha256:") else digest
    from hyperweave.formats import format_ext

    base = f"{base_url.rstrip('/')}/v1/a/{hexd}" if base_url else f"/v1/a/{hexd}"
    if fmt == FormatId.SVG.value:
        return base
    return f"{base}.{format_ext(parse_format(fmt))}"


def _to_compose_spec(env: SpecEnvelope, *, data_tokens: list[Any] | None = None) -> ComposeSpec:
    """Map a SpecEnvelope to a ComposeSpec, raising HwError on a bad spec.

    ``data_tokens`` (already resolved by the handler) is injected onto the
    ComposeSpec so the marquee/stats/matrix resolvers consume the live list;
    other frames receive the formatted value via ``env.spec['value']`` already.
    """
    content = dict(env.spec or {})
    # Back-compat: `chrome` was the pre-gut diagram presentation axis
    # (card/bare/caption), publicly settable via CLI --chrome / HTTP / MCP.
    # It is now internal-only (ComposeSpec.chrome, sec 12.1 embeds); a stray
    # key from an old stored payload or client must not 500 — drop it
    # silently rather than let it fall through to a nested IR dict (where
    # `extra="forbid"` would reject it) or resurrect external control of a
    # retired axis.
    content.pop("chrome", None)
    override = content.get("genome_override")
    genome_id, variant = resolve_presentation(
        env.type,
        env.genome,
        env.variant,
        genome_override=override if isinstance(override, dict) else None,
    )
    kwargs: dict[str, Any] = {"type": env.type, "genome_id": genome_id}
    if variant:
        kwargs["variant"] = variant
    ir_field = _IR_FIELD.get(env.type)
    if ir_field:
        # An IR frame's `spec` carries the nested schema PLUS any ComposeSpec-level
        # fields the caller packed alongside it (connector_data,
        # performance, surface axes, …). Lift the ComposeSpec fields out to
        # top-level kwargs; IR-owned names (title, diagram glyph_tint) stay put so
        # the remainder is the IR schema for `matrix`/`diagram`.
        for name in _LIFTABLE_BY_IR[env.type] & content.keys():
            kwargs[name] = content.pop(name)
        # Only pass the IR field when the caller actually supplied a schema. An
        # empty remainder means the input rides another path — the matrix
        # connector-registry adapter (connector_data), diagram preset, or data
        # tokens — which coerce_*_input engages when `matrix`/`diagram` is None.
        if content:
            kwargs[ir_field] = content
    else:
        kwargs.update(content)
    if data_tokens is not None:
        kwargs["data_tokens"] = data_tokens
    return build_compose_spec(kwargs, env.type)


def build_compose_spec(kwargs: dict[str, Any], frame_type: str) -> ComposeSpec:
    """Construct a ComposeSpec, mapping validation failures to clean HwError.

    The one exception-mapping seam every surface shares: the registry/HTTP/MCP
    path arrives via ``_to_compose_spec``; the CLI builds its kwargs from flags
    and calls this directly — so a malformed spec prints the same rule text
    everywhere instead of a raw traceback on one surface.
    """
    try:
        return ComposeSpec(**kwargs)
    except ValidationError as exc:
        code = HwErrorCode.TYPE_UNKNOWN if frame_type not in _FRAME_TYPES else HwErrorCode.SPEC_INVALID
        errors = exc.errors(include_url=False)
        # ComposeSpec nests an IR frame's schema under its own field name
        # (`diagram`/`matrix`), so pydantic prepends that name to every
        # nested loc — noise relative to the dict the caller actually
        # supplied as `spec`. Strip it so a field path reads `edges[0].source`
        # rather than `diagram.edges[0].source`.
        ir_field = _IR_FIELD.get(frame_type)
        if ir_field:
            errors = [
                {**err, "loc": tuple(err.get("loc") or ())[1:]}
                if tuple(err.get("loc") or ())[:1] == (ir_field,)
                else err
                for err in errors
            ]
        # Surface the first violation's own field path + text — cli_text()
        # used to print only message + fix, so a count-only message buried
        # the actual rule and gave a repairing agent nowhere to look.
        first = format_error_line(errors[0]) if errors else ""
        more = f" (+{len(errors) - 1} more)" if len(errors) > 1 else ""
        summary = f"{first}{more}" if first else f"{exc.error_count()} error(s)"
        raise HwError(
            code,
            f"invalid {frame_type} spec: {summary}",
            detail={"errors": errors},
        ) from exc
    except (TypeError, ValueError) as exc:
        raise HwError(HwErrorCode.SPEC_INVALID, str(exc)) from exc


def _emit_faces(
    spec: ComposeSpec,
    *,
    base_url: str,
    data_tokens: list[Any] | None,
) -> dict[str, str]:
    """Bake a twin's light + dark faces as two plate artifacts, return their URLs.

    Each face is a PLAIN PLATE render of the same spec with ``palette=fixed`` and
    ``surface_face`` pinned — the resolver's face-bake (WC-2a) resolves ABSOLUTE
    semantics: the requested face is left as the genome's own (native) palette
    when it matches the genome's substrate, and gets ``flip_palette`` merged in
    when it doesn't (e.g. ``face="dark"`` on a dark-native genome like noir is
    pass-through; ``face="light"`` on it merges the computed flip). Either way
    the untouched plate pipeline renders the result. Faces carry ``face`` in
    their payload, so the two get DISTINCT content addresses from each other
    and from the adaptive twin. Returned as ``{"light": url, "dark": url}``;
    the caller orders them ``[dark, light]`` for ``embed_snippets``.
    """
    faces: dict[str, str] = {}
    for face in ("light", "dark"):
        face_spec = spec.model_copy(update={"palette": "fixed", "surface_face": face})
        face_result = compose(face_spec)
        face_env = extract_envelope(face_result.svg)
        face_digest = str(face_env.get("id", "")) if face_env else ""
        if face_digest:
            store_artifact(face_digest, face_result.svg)
            faces[face] = build_artifact_url(face_digest, base_url, fmt="svg")
    return faces


def compose_surface(
    env: SpecEnvelope,
    *,
    base_url: str = "",
    data_tokens: list[Any] | None = None,
) -> ResponseEnvelope:
    """Render a SpecEnvelope, project to ``format``, cache, return a ResponseEnvelope.

    Live ``data`` tokens are resolved by the compose capability handler and passed
    in via ``data_tokens`` (marquee/stats/matrix) or already folded into
    ``env.spec['value']`` (other frames). The rendered SVG is cached under its
    content digest before projection; ``url`` points at the format the caller
    requested. ``svg`` in the response always carries the projected bytes decoded
    as text for SVG formats (raster bytes never travel in the text envelope —
    the caller fetches them from ``url``).
    """
    emit = set(env.emit) or {"svg"}
    unknown = emit - _VALID_EMIT
    if unknown:
        raise HwError(
            HwErrorCode.SPEC_INVALID,
            f"unknown emit target(s): {sorted(unknown)}",
            fix=f"choose from {sorted(_VALID_EMIT)}",
        )

    fmt = parse_format(env.format)
    spec = _to_compose_spec(env, data_tokens=data_tokens)
    result = compose(spec)

    # Cache the live SVG under its content digest; the digest addresses every
    # derived projection too (derive-on-demand at the /v1/a/{digest}.{ext} route).
    payload_pair = extract_payload(result.svg)
    envelope = extract_envelope(result.svg)
    digest = str(envelope.get("id", "")) if envelope else ""
    url = ""
    if digest:
        store_artifact(digest, result.svg)
        url = build_artifact_url(digest, base_url, fmt=env.format)

    # Project to the requested format. The adaptive x flatten guard lives inside
    # project() (WC's guard, relocated): svg-static/png/webp of an adaptive
    # artifact is rejected; a face render is exempt. For raster formats the bytes
    # do not enter the text envelope — the caller fetches them from `url`.
    is_face = spec.surface_face != ""
    projection = project(result.svg, fmt, is_face=is_face)
    svg_text = projection.data.decode("utf-8") if fmt in {FormatId.SVG, FormatId.SVG_STATIC} else ""

    payload_obj: dict[str, Any] | None = None
    if "payload" in emit and payload_pair is not None:
        try:
            payload_obj = json.loads(payload_pair[1])
        except json.JSONDecodeError:
            payload_obj = None

    # `faces` is twin-only: an adaptive palette with no explicit face baked. A
    # plate/inlay or a single-face render has no <picture> pair to produce, so the
    # request is a caller error caught here (loud, not a silent empty faces dict).
    faces: dict[str, str] | None = None
    if "faces" in emit:
        is_twin = spec.palette == "adaptive" and spec.ground != "bare" and not spec.surface_face
        if not is_twin:
            raise HwError(
                HwErrorCode.SPEC_INVALID,
                "faces emit is only valid for a twin (surface=twin: opaque + adaptive)",
                fix="compose with surface=twin, or drop the faces emit target",
            )
        faces = _emit_faces(spec, base_url=base_url, data_tokens=data_tokens)

    return ResponseEnvelope(
        envelope=envelope or {},
        svg=svg_text if "svg" in emit else "",
        md=result.markdown if "md" in emit else "",
        payload=payload_obj,
        compressed=envelope if "compressed" in emit else None,
        width=result.width,
        height=result.height,
        genome=spec.genome_id,
        variant=spec.variant,
        url=url,
        faces=faces,
        warnings=tuple(result.warnings),
        diagnostics=tuple(result.diagnostics) + _projection_diagnostics(projection),
    )


def _projection_diagnostics(projection: Projection) -> tuple[dict[str, str], ...]:
    """Projection drop-counts as a diagnostics record — the same honesty the
    CLI prints on stderr, threaded to MCP/HTTP envelope consumers."""
    if not projection.diagnostics:
        return ()
    measured = " · ".join(f"{key.replace('_', ' ')}: {value}" for key, value in projection.diagnostics.items())
    return (
        {
            "rule": "static-projection",
            "measured": measured,
            "band": "a flattening format declares what it drops",
            "suggestion": "render format=svg for the live artifact",
        },
    )


def validate_surface(env: SpecEnvelope) -> dict[str, Any]:
    """Validate a SpecEnvelope without rendering. Returns a report dict.

    Validate shares compose's gate: it builds the ComposeSpec AND runs the
    IR frame's structural coercion (the cheap, render-free half). Without
    the second step an envelope whose diagram/matrix fields landed at the
    top level (leaving ``spec`` empty) validated True yet failed to compose
    — a false green a cold agent will trust. Running the same coercion the
    resolver runs makes validate and compose incapable of disagreeing on
    structure."""
    try:
        cspec = _to_compose_spec(env)
        _validate_ir_structure(cspec)
    except HwError as exc:
        return {"valid": False, **exc.envelope()}
    return {"valid": True, "type": env.type, "genome": cspec.genome_id}


def _validate_ir_structure(cspec: ComposeSpec) -> None:
    """Run the real compose pipeline (bytes discarded) so validate refuses
    exactly what compose refuses — the invariant is "a file that validates
    always composes". Structural refusals live at every depth of the solve
    (input coercion, topology node bands, hub sector slots, dag rank caps,
    annotation anchors), so a curated pre-check list can never stay
    complete; the pipeline itself is the only honest oracle. Refusals are
    ValueError-family (DiagramInputError / MatrixInputError / pydantic
    ValidationError) and map to SPEC_INVALID carrying the solver's own
    message. Non-IR frames have no separate structural pass."""
    if cspec.type not in _IR_FIELD:
        return
    try:
        compose(cspec)
    except HwError:
        raise
    except (ValueError, TypeError) as exc:
        raise HwError(HwErrorCode.SPEC_INVALID, str(exc)) from exc
