"""Per-genome reasoning YAML files (data only — loader lives in compose/reasoning.py).

Each file (e.g. brutalist.yaml, chrome.yaml, automata.yaml) declares
``hw:reasoning`` block content per frame_type x substrate_kind. The loader
reads them at compose time and wires the intent/approach/tradeoffs strings
into template context — fields the metadata.svg.j2 template emits inside the
``<hw:reasoning>`` block when metadata_tier >= 3.
"""
