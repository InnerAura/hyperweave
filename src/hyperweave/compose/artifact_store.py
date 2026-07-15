"""Content-addressed artifact store.

The envelope id (``sha256`` of the payload) doubles as the artifact's ADDRESS.
``compose`` stores the rendered SVG under its digest; the read-only
``GET /v1/a/{digest}`` route serves it back. Three wins at once: a compact handle
(the agent embeds ``/v1/a/{digest}``, not 30 KB of SVG), free dedup (identical
content → same digest → one cached render), and a render-cache speed win.

Two tiers:

- **In-memory LRU** — always on. Stable handles for the life of the process;
  covers the multi-turn edit loop. Eviction/restart drops entries.
- **Disk tier (durable)** — opt-in via ``HW_ARTIFACT_CACHE_DIR`` (or
  ``configure_disk_cache``). Makes ``/v1/a/{digest}`` resolve cross-session: a
  README badge that must resolve forever, and a composed document that outlives
  the session, persist. Required-for-flagship — the document agent breaks
  statelessness on day one.

A cold handle with neither tier 404s; the caller falls back to the
self-describing ``?spec=`` URL.
"""

from __future__ import annotations

import contextlib
import os
from collections import OrderedDict
from pathlib import Path

_MAX_ENTRIES = 512
_cache: OrderedDict[str, str] = OrderedDict()
_disk_dir: Path | None = None

# Derived-projection tier: png/webp/static.svg bytes keyed by (source digest,
# format-ext). Smaller cap than the SVG tier — raster bytes are heavier and the
# common README path re-fetches the SVG, not the raster. Keys are
# ``{hex}.{key-ext}`` so they sit beside ``{hex}.svg`` on disk.
_MAX_DERIVED = 128
_derived: OrderedDict[str, bytes] = OrderedDict()


def _normalize(digest: str) -> str:
    """Accept either the bare hex or the ``sha256:`` envelope-id form."""
    return digest.split(":", 1)[1] if digest.startswith("sha256:") else digest


def configure_disk_cache(path: str | os.PathLike[str] | None) -> None:
    """Enable (or disable) the durable disk tier. Empty/None → memory-only."""
    global _disk_dir
    if not path:
        _disk_dir = None
        return
    _disk_dir = Path(path)
    _disk_dir.mkdir(parents=True, exist_ok=True)


def _disk_path(key: str) -> Path | None:
    return _disk_dir / f"{key}.svg" if _disk_dir is not None else None


def store_artifact(digest: str, svg: str) -> str:
    """Cache ``svg`` under its content digest (LRU + durable disk tier when on)."""
    key = _normalize(digest)
    if key in _cache:
        _cache.move_to_end(key)
    _cache[key] = svg
    while len(_cache) > _MAX_ENTRIES:
        _cache.popitem(last=False)
    path = _disk_path(key)
    if path is not None:
        # disk durability is best-effort; the LRU still serves this process
        with contextlib.suppress(OSError):
            path.write_text(svg, encoding="utf-8")
    return key


def get_artifact(digest: str) -> str | None:
    """Return the SVG for ``digest`` — LRU first, then the durable disk tier."""
    key = _normalize(digest)
    svg = _cache.get(key)
    if svg is not None:
        _cache.move_to_end(key)
        return svg
    path = _disk_path(key)
    if path is not None and path.exists():
        try:
            svg = path.read_text(encoding="utf-8")
        except OSError:
            return None
        _cache[key] = svg  # warm the LRU
        return svg
    return None


def store_derived(digest: str, key: str, data: bytes) -> str:
    """Cache a derived projection (png/webp/static.svg) for a source digest.

    ``key`` is the derived-store key — the format extension, optionally with a
    width suffix (``png``, ``webp``, ``static.svg``, ``png@w=400``). Stored in an
    own byte LRU (cap 128) and, when the disk tier is on, as ``{hex}.{key}``
    beside the source ``{hex}.svg``. Returns the composite cache key.
    """
    ckey = f"{_normalize(digest)}.{key}"
    if ckey in _derived:
        _derived.move_to_end(ckey)
    _derived[ckey] = data
    while len(_derived) > _MAX_DERIVED:
        _derived.popitem(last=False)
    if _disk_dir is not None:
        with contextlib.suppress(OSError):
            (_disk_dir / _disk_derived_name(_normalize(digest), key)).write_bytes(data)
    return ckey


def get_derived(digest: str, key: str) -> bytes | None:
    """Return a cached derived projection — LRU first, then the durable disk tier."""
    ckey = f"{_normalize(digest)}.{key}"
    data = _derived.get(ckey)
    if data is not None:
        _derived.move_to_end(ckey)
        return data
    if _disk_dir is not None:
        path = _disk_dir / _disk_derived_name(_normalize(digest), key)
        if path.exists():
            try:
                data = path.read_bytes()
            except OSError:
                return None
            _derived[ckey] = data  # warm the LRU
            return data
    return None


def _disk_derived_name(hexd: str, key: str) -> str:
    """Disk filename for a derived projection. A ``@w=`` cap becomes ``.w{N}``
    so the on-disk name stays a plain filename (no ``@``/``=`` reserved chars)."""
    if "@w=" in key:
        base, width = key.split("@w=", 1)
        return f"{hexd}.w{width}.{base}"
    return f"{hexd}.{key}"


def reset_cache() -> None:
    """Drop both in-memory tiers (tests + the loader reset path). Disk is untouched."""
    _cache.clear()
    _derived.clear()


# Durability is opt-in via the environment so `pip install hyperweave` writes no
# files by default; a deployment sets HW_ARTIFACT_CACHE_DIR to persist handles.
configure_disk_cache(os.environ.get("HW_ARTIFACT_CACHE_DIR") or None)
