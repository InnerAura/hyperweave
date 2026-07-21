"""Capability input models, handlers, and registrations.

Each capability is: a pydantic input model (the wire contract), an async handler
(thin over the verb / surface core — the verbs' ``.to_dict()`` results ARE the
output contract), and a ``register()`` call. Handlers are transport-agnostic;
they read only the model and the :class:`CallContext` (never a surface branch).

Registration order here is the roster order the parity test and
``hw_discover(what="capabilities")`` iterate.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from hyperweave.surfaces.registry import CallContext, Capability, register

# ── Input models ─────────────────────────────────────────────────────────────
# Field docs double as the OpenAPI descriptions (the route factory stamps these
# models onto the endpoint signatures) and the MCP/CLI parameter help.


class ComposeInput(BaseModel):
    """Compose a HyperWeave artifact from a spec envelope."""

    type: str = Field(
        description="Frame type: badge | strip | icon | divider | marquee | receipt | card | chart | matrix | diagram"
    )
    genome: str = Field(default="primer", description="Genome id (primer | brutalist | chrome | automata).")
    variant: str = Field(default="", description="Chromatic variant slug (genome-specific).")
    spec: dict[str, Any] = Field(default_factory=dict, description="Frame IR / content fields.")
    data: str = Field(default="", description="Data-token grammar string (live values resolved inline).")
    format: str = Field(default="svg", description="Output format: svg | svg-static | png | webp.")
    emit: list[str] = Field(
        default_factory=lambda: ["svg"], description="Emit targets: svg | md | payload | compressed."
    )


class ValidateInput(BaseModel):
    """Validate a spec envelope without rendering."""

    type: str = Field(description="Frame type.")
    genome: str = Field(default="primer", description="Genome id.")
    variant: str = Field(default="", description="Chromatic variant slug.")
    spec: dict[str, Any] = Field(default_factory=dict, description="Frame IR / content fields.")


class ExtractInput(BaseModel):
    """Extract the embedded seed at a chosen depth."""

    source: str = Field(description="Artifact SVG string, a /v1/a/{digest} url, or a digest/id.")
    respond: str = Field(
        default="envelope", description="Depth: envelope (compact digest) | payload (lossless) | markdown."
    )


class VerifyInput(BaseModel):
    """Recompute the hash and prove the artifact IS its data."""

    source: str = Field(description="Artifact SVG string, a /v1/a/{digest} url, or a digest/id.")


class TransformInput(BaseModel):
    """Mutate an artifact via an RFC-6902 JSON patch → a new artifact."""

    source: str = Field(description="Artifact SVG string, a /v1/a/{digest} url, or a digest/id.")
    mutations: list[dict[str, Any]] = Field(description="RFC-6902 op list (add/remove/replace/move/copy/test).")
    respond: str = Field(
        default="envelope",
        description="envelope (default — the handle; fetch `url` for pixels) | svg (include the new markup inline).",
    )


class DiffInput(BaseModel):
    """Payload-bound structured delta between two artifacts."""

    a: str = Field(description="First artifact (SVG string / url / digest).")
    b: str = Field(description="Second artifact (SVG string / url / digest).")


class QueryInput(BaseModel):
    """Answer a question about an artifact from its compact envelope."""

    source: str = Field(description="Artifact SVG string, a /v1/a/{digest} url, or a digest/id.")
    question: str = Field(description="Natural-language question resolved against the envelope fields.")


class DiscoverInput(BaseModel):
    """Discover available components / capabilities."""

    what: str = Field(
        default="all",
        description="all | genomes | motions | glyphs | frames | verbs | matrix | diagram | url_grammar "
        "| capabilities | schemas — plus the deep selectors schema:<id> (published JSON Schema, e.g. "
        "schema:diagram/1), example:<frame_type>/<name> (a full bundled spec, compose-ready), and "
        "genome:<id> (role-structured token deep-dive).",
    )


# ── Handlers ─────────────────────────────────────────────────────────────────
# Thin over the verbs / surface core. Compose delegates to the same engine path
# the wires use today; task #7 re-points this ONE handler body through
# compose_surface() (no registration/adapter change).


async def _compose(model: BaseModel, ctx: CallContext) -> dict[str, Any]:
    assert isinstance(model, ComposeInput)
    from hyperweave.compose.surface import SpecEnvelope, compose_surface
    from hyperweave.connectors.data_tokens import (
        format_for_value,
        parse_data_tokens,
        resolve_data_tokens,
    )

    # Live data-token resolution (async, frame-aware) is the transport-adjacent
    # step — the ONE resolution path all three surfaces share. Marquee/stats/matrix
    # consume the resolved list; other frames receive the formatted value string.
    data_tokens_resolved: list[Any] | None = None
    final_spec = dict(model.spec)
    if model.data:
        tokens = parse_data_tokens(model.data)
        resolved, _ttl = await resolve_data_tokens(tokens)
        if model.type in {"marquee", "stats", "matrix"}:
            data_tokens_resolved = list(resolved)
        else:
            formatted = format_for_value(resolved)
            if formatted and "value" not in final_spec:
                final_spec["value"] = formatted

    env = SpecEnvelope(
        type=model.type,
        genome=model.genome,
        variant=model.variant,
        spec=final_spec,
        data=model.data,
        format=model.format,
        emit=tuple(model.emit) or ("svg",),
    )
    # The unified core builds the ComposeSpec, renders, projects to `format`,
    # caches under the digest, and returns the ResponseEnvelope. to_dict() always
    # carries the actionable `envelope` + `url`; the pixels ride `url` for raster.
    response = compose_surface(env, base_url=ctx.base_url, data_tokens=data_tokens_resolved)
    return response.to_dict()


async def _validate(model: BaseModel, _ctx: CallContext) -> dict[str, Any]:
    assert isinstance(model, ValidateInput)
    from hyperweave.compose.surface import SpecEnvelope, validate_surface

    return validate_surface(SpecEnvelope(type=model.type, genome=model.genome, variant=model.variant, spec=model.spec))


async def _extract(model: BaseModel, _ctx: CallContext) -> dict[str, Any]:
    assert isinstance(model, ExtractInput)
    from hyperweave.verbs import extract

    return extract(model.source, respond=model.respond).to_dict()


async def _verify(model: BaseModel, _ctx: CallContext) -> dict[str, Any]:
    assert isinstance(model, VerifyInput)
    from hyperweave.verbs import verify

    return verify(model.source).to_dict()


async def _transform(model: BaseModel, ctx: CallContext) -> dict[str, Any]:
    assert isinstance(model, TransformInput)
    from hyperweave.verbs import transform

    result = transform(model.source, model.mutations, base_url=ctx.base_url)
    out = result.to_dict()
    if model.respond == "svg":
        # The write-verb escape hatch hw_compose already has: inline markup on
        # request. Registry-level, so every surface gains it identically.
        out["svg"] = result.svg
    return out


async def _diff(model: BaseModel, _ctx: CallContext) -> dict[str, Any]:
    assert isinstance(model, DiffInput)
    from hyperweave.verbs import diff

    return diff(model.a, model.b).to_dict()


async def _query(model: BaseModel, _ctx: CallContext) -> dict[str, Any]:
    assert isinstance(model, QueryInput)
    from hyperweave.verbs import query

    return query(model.source, model.question).to_dict()


async def _discover(model: BaseModel, _ctx: CallContext) -> dict[str, Any]:
    assert isinstance(model, DiscoverInput)
    from hyperweave.surfaces.discover import discover

    return discover(model.what)


# ── Registrations (roster order) ─────────────────────────────────────────────

register(
    Capability(
        name="compose",
        summary="Compose a HyperWeave artifact from a spec envelope; returns {envelope, url, ...}.",
        input_model=ComposeInput,
        handler=_compose,
        output_note="{width, height, genome, variant, url, envelope, svg?, md?, payload?, compressed?}",
        http_path="/v1/compose",
        cli_command="compose",
        mcp_tool="hw_compose",
    )
)

register(
    Capability(
        name="validate",
        summary="Validate a spec envelope without rendering; returns a {valid, ...} report.",
        input_model=ValidateInput,
        handler=_validate,
        output_note="{valid: bool, type, genome} or {valid: false, error: {...}}",
        http_path="/v1/validate",
        cli_command="validate",
        mcp_tool="hw_validate",
    )
)

register(
    Capability(
        name="extract",
        summary="Extract the embedded seed at envelope | payload | markdown depth.",
        input_model=ExtractInput,
        handler=_extract,
        output_note="{respond, schema, envelope? | payload? | markdown?}",
        http_path="/v1/extract",
        cli_command="extract",
        mcp_tool="hw_extract",
    )
)

register(
    Capability(
        name="verify",
        summary="Recompute the hash; prove id == sha256(payload).",
        input_model=VerifyInput,
        handler=_verify,
        output_note="{valid: bool, well_formed: bool, id, expected_id, schema}",
        http_path="/v1/verify",
        cli_command="verify",
        mcp_tool="hw_verify",
    )
)

register(
    Capability(
        name="transform",
        summary="Mutate an artifact via an RFC-6902 JSON patch → a new artifact.",
        input_model=TransformInput,
        handler=_transform,
        output_note="{envelope, url, lineage, parent_id, new_id}",
        http_path="/v1/transform",
        cli_command="transform",
        mcp_tool="hw_transform",
    )
)

register(
    Capability(
        name="diff",
        summary="Payload-bound structured delta between two artifacts.",
        input_model=DiffInput,
        handler=_diff,
        output_note="{same, schema, added, removed, changed, title_changed, genome_changed}",
        http_path="/v1/diff",
        cli_command="diff",
        mcp_tool="hw_diff",
    )
)

register(
    Capability(
        name="query",
        summary="Answer a question about an artifact from its compact envelope.",
        input_model=QueryInput,
        handler=_query,
        output_note="{answer, field, mechanism, confidence}",
        http_path="/v1/query",
        cli_command="query",
        mcp_tool="hw_query",
    )
)

register(
    Capability(
        name="discover",
        summary="Discover available genomes, motions, glyphs, frames, verbs, and capabilities.",
        input_model=DiscoverInput,
        handler=_discover,
        output_note="Structured lists keyed by the `what` selector.",
        http_path="/v1/discover",
        cli_command="discover",
        mcp_tool="hw_discover",
        mcp_note=(
            "HTTP face is a bespoke GET (`?what=`), beside the informal "
            "/llms.txt + /llms-full.txt and static /v1/{frames,genomes,motions,glyphs} listings."
        ),
    )
)
