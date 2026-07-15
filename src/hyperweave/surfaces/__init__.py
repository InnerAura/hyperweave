"""The surface layer — one capability registry, three thin adapters.

Architectural Invariant 9 (CLI / HTTP / MCP feature parity) is enforced *by
construction* here: every operation a caller invokes is a :class:`Capability`
registered once, and the CLI, HTTP, and MCP wires become thin adapters that
acquire input, call :func:`dispatch`, and render the result. A capability's
handler is transport-agnostic — it never learns which surface called it (the
:class:`CallContext` carries only a ``surface`` label for telemetry and a
``base_url`` for content-addressed handles, never a branch).

The parity test (``tests/surfaces/test_parity.py``) is the no-drift proof: it
asserts every registered capability is reachable on all three surfaces.
"""

from __future__ import annotations

# Import for side effect: the register() calls in capabilities.py populate the
# roster. Importing the surfaces package (any adapter does) is what guarantees
# dispatch() sees the full set — registration is otherwise import-time-only.
# Placed after the registry import so the module's register() calls resolve; the
# heavy compose/verb imports inside handler bodies stay lazy.
from hyperweave.surfaces import capabilities as _capabilities  # noqa: F401
from hyperweave.surfaces.registry import (
    CallContext,
    Capability,
    all_capabilities,
    dispatch,
    get_capability,
    register,
)

__all__ = [
    "CallContext",
    "Capability",
    "all_capabilities",
    "dispatch",
    "get_capability",
    "register",
]
