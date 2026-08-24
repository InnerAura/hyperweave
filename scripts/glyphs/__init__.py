"""The glyph and font asset pipeline.

Everything that produces or checks the material the frames draw with:
`data/glyphs.json` (brand marks and geometric shapes), the subsetted woff2
payloads under `data/fonts/`, and the per-face advance-width tables the layout
engine measures against.

Separate from `scripts.examples` because the direction is opposite. These
scripts write INTO `src/hyperweave/data/` — they produce committed inputs the
engine reads. The example generators read that data and write artifacts out.
"""
