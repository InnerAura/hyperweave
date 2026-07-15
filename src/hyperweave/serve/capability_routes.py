"""HTTP route factory — one POST route per registry capability.

Loops the capability registry and registers ``POST {http_path}`` for each
capability that declares one. The endpoint takes the capability's pydantic
``input_model`` as the request body (so OpenAPI documents the exact wire
contract from the model — no ``__signature__`` stamping needed) and dispatches
through the shared core. The parity test is the no-drift proof that every
declared ``http_path`` is actually mounted.

Replaces the five hand-written verb routes (extract/verify/transform/diff/query)
and unifies them with compose/validate under one loop. Compose and validate
each ALSO keep their bespoke GET/behavioral routes elsewhere in ``app.py`` (the
GET frame grammar, the image-response default) — those are surface-specific
divergences that live in the adapter, not the factory. This factory owns only
the uniform ``POST /v1/{capability}`` JSON contract.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from fastapi.responses import JSONResponse

from hyperweave.core.errors import HwError
from hyperweave.surfaces.registry import CallContext, all_capabilities

if TYPE_CHECKING:
    from fastapi import FastAPI

    from hyperweave.surfaces.registry import Capability

# Capabilities whose uniform POST route the factory owns. compose and validate
# keep their bespoke routes in app.py (GET grammar / image default / envelope
# body), so the factory does not double-mount them; it owns the verb five.
_FACTORY_CAPABILITIES = frozenset({"extract", "verify", "transform", "diff", "query"})


def _make_endpoint(cap: Capability) -> Any:
    """Build an async endpoint bound to ``cap`` that dispatches its input model.

    The endpoint's ``body`` parameter is stamped with the capability's concrete
    ``input_model`` as a real annotation (via ``__signature__`` + ``__annotations__``)
    so FastAPI introspects the exact wire contract for OpenAPI and request
    validation. A closure annotation alone does not survive ``from __future__
    import annotations`` (PEP 563 stringifies it to an unresolvable forward ref).
    """
    from hyperweave.surfaces.registry import dispatch

    async def endpoint(body: Any) -> JSONResponse:
        from hyperweave.config.settings import get_settings

        ctx = CallContext(surface="http", base_url=get_settings().public_base_url)
        try:
            result = await dispatch(cap.name, body.model_dump(), ctx)
        except HwError as exc:
            return JSONResponse(exc.envelope(), status_code=exc.http_status)
        return JSONResponse(result)

    endpoint.__name__ = f"{cap.name}_capability"
    endpoint.__doc__ = cap.summary
    # Stamp the concrete model so FastAPI reads it as the JSON body model.
    param = inspect.Parameter("body", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=cap.input_model)
    endpoint.__signature__ = inspect.Signature([param])  # type: ignore[attr-defined]
    endpoint.__annotations__ = {"body": cap.input_model, "return": JSONResponse}
    return endpoint


def register_capability_routes(app: FastAPI) -> None:
    """Mount ``POST {http_path}`` for each factory-owned capability."""
    for cap in all_capabilities():
        if cap.name not in _FACTORY_CAPABILITIES or cap.http_path is None:
            continue
        app.add_api_route(
            cap.http_path,
            _make_endpoint(cap),
            methods=["POST"],
            response_model=None,
            summary=cap.summary,
            name=f"{cap.name}_capability",
        )
