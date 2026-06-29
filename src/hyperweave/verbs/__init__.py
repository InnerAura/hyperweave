"""The verb algebra — read/write operations over the artifact seed.

Write half: ``transform`` (Gate 2). Read half: ``verify`` (Gate 2),
``extract``/``diff``/``query`` (Gate 3). Every verb operates on the embedded
``hw:payload``/``hw:envelope`` through the shared ``core/envelope`` emitter, so
emitted ≡ extracted by construction.
"""

from __future__ import annotations

from hyperweave.verbs.diff import DiffResult, diff
from hyperweave.verbs.extract import ExtractResult, extract
from hyperweave.verbs.query import QueryResult, query
from hyperweave.verbs.transform import TransformResult, transform
from hyperweave.verbs.verify import VerifyResult, verify

__all__ = [
    "DiffResult",
    "ExtractResult",
    "QueryResult",
    "TransformResult",
    "VerifyResult",
    "diff",
    "extract",
    "query",
    "transform",
    "verify",
]
