"""Session telemetry: transcript parsing, stage detection, correction
classification, cost calculation, and data contract assembly.

ARCHITECTURAL INVARIANT: This module NEVER imports from render/ or compose/.
It parses transcripts and produces data contract dicts. Those dicts enter the
compositor through ComposeSpec.telemetry_data like any other input.
"""

from hyperweave.telemetry.context import build_context_summary, window_for_model
from hyperweave.telemetry.contract import build_contract, build_receipt_contract
from hyperweave.telemetry.corrections import classify_user_events
from hyperweave.telemetry.cost import calculate_session_cost, calculate_turn_cost
from hyperweave.telemetry.models import SessionTelemetry, ToolCall
from hyperweave.telemetry.parser import parse_transcript
from hyperweave.telemetry.receipt_payload import build_receipt_payload
from hyperweave.telemetry.stages import detect_stages

__all__ = [
    "SessionTelemetry",
    "ToolCall",
    "build_context_summary",
    "build_contract",
    "build_receipt_contract",
    "build_receipt_payload",
    "calculate_session_cost",
    "calculate_turn_cost",
    "classify_user_events",
    "detect_stages",
    "parse_transcript",
    "window_for_model",
]
