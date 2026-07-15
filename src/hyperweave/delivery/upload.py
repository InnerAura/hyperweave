"""Upload seam — a Protocol for pushing an artifact to a third-party host.

INTERNAL and unnamed in the CLI. No uploader ships yet; this is the shape
a future one (Slack, an S3 bucket, a paste host) plugs into, plus an env-config
resolver that returns an honest "unavailable" until one is registered. Keeping
the seam here — rather than a ``--via slack`` flag — means the destination
concept never leaks back into a user-facing surface (the rot ``--target`` died
for): a host is a deployment's private wiring, not a compose option.
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from hyperweave.core.errors import HwError, HwErrorCode


@runtime_checkable
class Uploader(Protocol):
    """Pushes artifact bytes to a host and returns a retrievable URL."""

    name: str

    def upload(self, data: bytes, *, media_type: str, filename: str) -> str:
        """Upload ``data`` and return a URL that serves it back."""
        ...


# Registry of built uploaders by name. Ships EMPTY — a deployment registers its
# own via register_uploader(); nothing is bundled.
_UPLOADERS: dict[str, Uploader] = {}


def register_uploader(uploader: Uploader) -> None:
    """Register an uploader implementation under its ``name`` (deployment wiring)."""
    _UPLOADERS[uploader.name] = uploader


def resolve_uploader(name: str = "") -> Uploader:
    """Resolve an uploader by name (or ``HW_UPLOADER``), or raise honestly.

    With no registered uploaders — the shipped state — this always raises
    ``FORMAT_UNAVAILABLE`` naming the seam, so a caller gets a clear "not wired
    up" answer instead of a silent no-op. The env var lets a deployment pick a
    default without a flag.
    """
    chosen = name or os.environ.get("HW_UPLOADER", "")
    if not _UPLOADERS:
        raise HwError(
            HwErrorCode.FORMAT_UNAVAILABLE,
            "no uploader is configured",
            fix="artifacts are served from the compose `url`; register an Uploader to push elsewhere",
        )
    if not chosen:
        if len(_UPLOADERS) == 1:
            return next(iter(_UPLOADERS.values()))
        raise HwError(
            HwErrorCode.FORMAT_UNAVAILABLE,
            "multiple uploaders registered; none selected",
            fix=f"set HW_UPLOADER to one of: {sorted(_UPLOADERS)}",
        )
    try:
        return _UPLOADERS[chosen]
    except KeyError:
        raise HwError(
            HwErrorCode.FORMAT_UNAVAILABLE,
            f"unknown uploader {chosen!r}",
            fix=f"register it, or choose from: {sorted(_UPLOADERS)}",
        ) from None
