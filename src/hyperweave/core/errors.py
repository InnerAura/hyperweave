"""The error envelope — one shape, three transport renderings.

Every failure across CLI, MCP, and HTTP serializes to the same dict::

    {"error": {"code": "...", "message": "...", "fix": "...", "detail": {...}}}

CLI prints ``message`` + ``fix`` as plain text (full JSON under ``--debug``);
MCP returns the dict as a tool result; HTTP returns the dict with a mapped 4xx
status. The ``code`` is drawn from a closed registry so a receiving agent can
branch on it without parsing prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class HwErrorCode(StrEnum):
    """The closed error-code registry (alpha.5)."""

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


# code → HTTP status. Most are client errors (400); a few map more precisely.
_STATUS_BY_CODE: dict[HwErrorCode, int] = {
    HwErrorCode.TYPE_UNKNOWN: 404,
    HwErrorCode.GENOME_UNKNOWN: 404,
    HwErrorCode.VARIANT_UNKNOWN: 404,
    HwErrorCode.PRESET_UNKNOWN: 404,
    HwErrorCode.TOPOLOGY_UNKNOWN: 404,
    HwErrorCode.DATA_RESOLVE_FAIL: 502,
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
        """Plain-text rendering for the CLI surface (message + optional fix)."""
        return f"{self.message}\n  fix: {self.fix}" if self.fix else self.message
