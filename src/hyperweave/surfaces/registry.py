"""The capability registry — the single roster the three surfaces adapt over.

A :class:`Capability` binds a name to a pydantic input model, an async handler,
and the reachability declarations (``http_path`` / ``cli_command`` /
``mcp_tool``) the parity test checks. :func:`dispatch` is the one call path:
validate the payload against the model, run the handler, return a result dict.

Imports here are **pydantic + stdlib only** — never fastapi/fastmcp/typer. The
registry is the transport-agnostic core; the adapters live in
``surfaces/cli.py``, ``serve/capability_routes.py``, and ``mcp/server.py``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from hyperweave.core.errors import HwError, HwErrorCode

# A handler takes the validated input model and the call context, and returns
# the canonical result dict (the same shape on every surface). Handlers are
# uniformly async; a sync core just runs inline.
Handler = Callable[[BaseModel, "CallContext"], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class CallContext:
    """Per-call context threaded to every handler.

    ``surface`` is a label ("cli" | "http" | "mcp") for telemetry only —
    **handlers MUST NOT branch on it**. Per-surface behavioral divergences
    (HTTP's image default, MCP's inline-svg opt-in) live in the adapters, not
    the handlers. ``base_url`` supplies the origin for content-addressed
    ``/v1/a/{digest}`` handles (empty → relative handles).
    """

    surface: str
    base_url: str = ""


@dataclass(frozen=True)
class Capability:
    """One operation, declared once, reachable on all three surfaces.

    ``input_model`` is the pydantic model the payload validates against (its
    field set is the wire contract; the HTTP route factory stamps it onto the
    endpoint signature for OpenAPI). ``output_note`` documents the result-dict
    shape. The reachability fields declare where the capability is wired; the
    parity test asserts each declared site actually exists. A capability with
    ``mcp_tool=None`` must set ``mcp_note`` (why it is not a tool — e.g. served
    as a resource template) so the parity test can account for it.
    """

    name: str
    summary: str
    input_model: type[BaseModel]
    handler: Handler
    output_note: str
    http_path: str | None = None
    cli_command: str | None = None
    mcp_tool: str | None = None
    mcp_note: str = ""


_REGISTRY: dict[str, Capability] = {}


def register(cap: Capability) -> Capability:
    """Register a capability. Re-registration under the same name replaces it
    (idempotent module reload); a capability without an MCP tool must carry an
    ``mcp_note`` so its non-tool reachability is documented."""
    if cap.mcp_tool is None and not cap.mcp_note:
        raise ValueError(f"capability {cap.name!r} has no mcp_tool and no mcp_note — one is required")
    _REGISTRY[cap.name] = cap
    return cap


def get_capability(name: str) -> Capability | None:
    """Look up a capability by name (None if unknown)."""
    return _REGISTRY.get(name)


def all_capabilities() -> list[Capability]:
    """Every registered capability, in registration order."""
    return list(_REGISTRY.values())


async def dispatch(name: str, payload: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    """Validate ``payload`` against the capability's model and run its handler.

    Unknown ``name`` → ``HwError(TYPE_UNKNOWN)``. A payload that fails model
    validation → ``HwError(SPEC_INVALID)`` carrying the pydantic error detail.
    Any ``HwError`` the handler raises propagates unchanged (the adapters render
    it per surface via ``.envelope()`` / ``.cli_text()`` / ``.http_status``).
    """
    cap = _REGISTRY.get(name)
    if cap is None:
        raise HwError(
            HwErrorCode.TYPE_UNKNOWN,
            f"unknown capability {name!r}",
            fix=f"choose from {sorted(_REGISTRY)}",
        )
    try:
        model = cap.input_model.model_validate(payload)
    except PydanticValidationError as exc:
        raise HwError(
            HwErrorCode.SPEC_INVALID,
            f"invalid {name} input: {exc.error_count()} error(s)",
            detail={"errors": exc.errors(include_url=False)},
        ) from exc
    return await cap.handler(model, ctx)
