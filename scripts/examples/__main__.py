"""`python -m scripts.examples` — build the whole visual acceptance surface.

One entry point for every gallery under `outputs/`. The modules beside this one
each own a gallery: what it declares, and the document it composes from those
records.
"""

from __future__ import annotations

from scripts.examples.proofset import main

if __name__ == "__main__":
    main()
