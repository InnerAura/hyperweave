"""Delivery mechanics — how composed bytes reach a destination.

The only user-facing delivery model the CLI names is *bytes to stdout or a file*
(``-o``). Everything else here is either an auto-detected convenience or an
internal seam for the document layer:

- :mod:`kitty` — blit a PNG into a graphics-capable terminal via the kitty
  graphics protocol. Auto-detected (no flag): raw image bytes to an interactive
  TTY are never the wanted behavior, and piped output always stays raw, so the
  detection harms nothing (the ``ls``/``git``/``bat`` convention).
- :mod:`embed` — build markdown/html ``<picture>`` snippets from hosted URLs.
  INTERNAL: the document layer's seam; not exposed on any CLI/HTTP/MCP surface.
- :mod:`upload` — an :class:`~hyperweave.delivery.upload.Uploader` Protocol +
  env-config resolver. No implementation ships; the seam is unnamed in the CLI.
"""

from __future__ import annotations
