"""Example-artifact generation — the galleries under `outputs/` and the
committed specimens under `assets/examples/`.

`outputs/` is gitignored, so THIS package is the deliverable: every artifact a
reviewer looks at is a live engine render, and the document around it is
composed from the same declaration that produced the render.

The seam is :mod:`manifest`. A generator DECLARES artifacts into a
:class:`~scripts.examples.manifest.Gallery`; the gallery renders them and the
document emitter iterates the very same records. Before that split, the
renderer and the README each built filenames by string-formatting and the
README probed disk with ``.exists()`` to find out what the renderer had
actually written — two descriptions of one filename, and a missing artifact
showed up as a broken image rather than a failure.

Modules:

* :mod:`manifest`  — ``Artifact`` / ``Gallery``: what exists, and where.
* :mod:`render`    — spec construction + writing bytes to disk.
* :mod:`surfaces`  — renders every artifact through direct · CLI · HTTP · MCP
  and reports divergence (Invariant 9, made continuous).
* :mod:`markdown`  — the small vocabulary the gallery documents are built from.
* :mod:`genomes`   — one data-driven emitter for all four genome galleries.
* :mod:`matrices`  — the matrix fixtures, boundary suite and surface modes.
"""
