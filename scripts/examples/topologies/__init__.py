"""Per-family diagram exhibits — one directory per topology.

Each family gets `outputs/diagrams/topologies/<family>/`: a README composed
from its own renders, never hand-written. The flat single-document gallery it
replaces put eleven families in one file, which made "what can this family
express" a scrolling exercise and gave no family room to show its own axes,
capability edges and refusals.

`dag` is the deep template — seven sections, hand-built over a review wave.
Every other family runs the same skeleton (:mod:`exhibit`) over its own
content, and deepens toward that template as its axes get pinned.

Each module single-sources its `FAMILY` slug so the directory, the subcommand
and every message derive from one string and cannot drift apart.
"""
