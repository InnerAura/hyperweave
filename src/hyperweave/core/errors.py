"""The error envelope — one shape, three transport renderings.

Every failure across CLI, MCP, and HTTP serializes to the same dict::

    {"error": {"code": "...", "message": "...", "fix": "...", "detail": {...}}}

CLI prints ``message``, then (when ``detail["errors"]`` carries pydantic-shaped
field errors) one indented ``path: msg`` line per violation, then ``fix`` —
see :meth:`HwError.cli_text`. MCP and HTTP return the full envelope dict
unmodified, ``detail`` included. The ``code`` is drawn from a closed registry
so a receiving agent can branch on it without parsing prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping


class HwErrorCode(StrEnum):
    """The closed error-code registry."""

    DAG_RANK_CAP = "DAG_RANK_CAP"
    DAG_NODE_CAP = "DAG_NODE_CAP"
    DAG_CYCLE = "DAG_CYCLE"
    SM_NODE_CAP = "SM_NODE_CAP"
    STACK_NODE_CAP = "STACK_NODE_CAP"
    GLYPH_MISS = "GLYPH_MISS"  # warn-level
    TOPOLOGY_UNKNOWN = "TOPOLOGY_UNKNOWN"
    SPEC_INVALID = "SPEC_INVALID"
    GENOME_UNKNOWN = "GENOME_UNKNOWN"
    VARIANT_UNKNOWN = "VARIANT_UNKNOWN"
    PRESET_UNKNOWN = "PRESET_UNKNOWN"
    ENVELOPE_CORRUPT = "ENVELOPE_CORRUPT"
    TYPE_UNKNOWN = "TYPE_UNKNOWN"
    DATA_RESOLVE_FAIL = "DATA_RESOLVE_FAIL"
    FORMAT_UNAVAILABLE = "FORMAT_UNAVAILABLE"  # raster extra missing / gif unsupported


def format_error_loc(loc: tuple[Any, ...]) -> str:
    """Render a pydantic error ``loc`` tuple as a dotted/indexed path.

    ``("edges", 0, "source")`` → ``"edges[0].source"``. An integer segment is
    a sequence index and binds to the preceding segment with brackets rather
    than a dot, so a repair agent sees a path it can paste into the spec dict
    it just built.
    """
    parts: list[str] = []
    for seg in loc:
        if isinstance(seg, int):
            if parts:
                parts[-1] = f"{parts[-1]}[{seg}]"
            else:
                parts.append(f"[{seg}]")
        else:
            parts.append(str(seg))
    return ".".join(parts)


def format_error_line(err: Mapping[str, Any]) -> str:
    """Render one pydantic error dict (``{type, loc, msg, ...}``) as ``path: msg``.

    ``extra_forbidden`` gets a legible rewrite (``unknown field`` — the signal
    a Mermaid-shaped ``from``/``to`` edge needs) rather than pydantic's generic
    "Extra inputs are not permitted". Custom validator prose loses pydantic's
    "Value error, " prefix, which reads as internal plumbing, not a fix.
    """
    path = format_error_loc(tuple(err.get("loc") or ()))
    if err.get("type") == "extra_forbidden":
        msg = "unknown field"
    else:
        msg = str(err.get("msg", "")).removeprefix("Value error, ")
    return f"{path}: {msg}" if path else msg


# code → HTTP status. Most are client errors (400); a few map more precisely.
_STATUS_BY_CODE: dict[HwErrorCode, int] = {
    HwErrorCode.TYPE_UNKNOWN: 404,
    HwErrorCode.GENOME_UNKNOWN: 404,
    HwErrorCode.VARIANT_UNKNOWN: 404,
    HwErrorCode.PRESET_UNKNOWN: 404,
    HwErrorCode.TOPOLOGY_UNKNOWN: 404,
    HwErrorCode.DATA_RESOLVE_FAIL: 502,
    # 501 Not Implemented — the format is known but this build can't produce it
    # (the [raster] extra is not installed, or gif has no supported path).
    HwErrorCode.FORMAT_UNAVAILABLE: 501,
}


@dataclass
class HwError(Exception):
    """A structured, transport-agnostic error carrying a registry code."""

    code: HwErrorCode
    message: str
    fix: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__init__(self.message)

    @property
    def http_status(self) -> int:
        """Mapped 4xx/5xx status; defaults to 400 (bad request)."""
        return _STATUS_BY_CODE.get(self.code, 400)

    def envelope(self) -> dict[str, Any]:
        """The canonical error-envelope dict (one shape, all transports)."""
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "fix": self.fix,
                "detail": dict(self.detail),
            }
        }

    def cli_text(self) -> str:
        """Plain-text rendering for the CLI surface: message, per-field detail
        lines (when ``detail["errors"]`` carries pydantic-shaped field errors),
        then the optional fix last. A caller with no ``errors`` detail gets the
        exact message-or-message+fix text this method always rendered — that
        contract is load-bearing for callers matching on it verbatim."""
        lines = [self.message]
        errors = self.detail.get("errors") if self.detail else None
        if isinstance(errors, list) and errors:
            cap = 8
            lines.extend(f"  {format_error_line(err)}" for err in errors[:cap] if isinstance(err, dict))
            remainder = len(errors) - cap
            if remainder > 0:
                lines.append(f"  ... and {remainder} more")
        if self.fix:
            lines.append(f"  fix: {self.fix}")
        return "\n".join(lines)
