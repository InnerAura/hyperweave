"""Compiler diagnostics — the advisory record (§6, diagrams-v2).

A diagnostic teaches: {rule, measured, band, suggestion}. It NEVER blocks a
compose — refusals live at the input seam and carry their rule name in the
error instead. All three surfaces render the same record: the CLI prints
``diagnostic: rule — measured (band) → suggestion`` to stderr; HTTP JSON and
MCP carry the dict form.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One advisory finding from the diagram compiler."""

    rule: str
    measured: str
    band: str
    suggestion: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)

    def cli_text(self) -> str:
        return f"diagnostic: {self.rule} — {self.measured} (band: {self.band}) → {self.suggestion}"
