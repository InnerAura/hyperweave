"""The container-inclusion law: an enclosure is sized by everything it holds."""

from __future__ import annotations


def container_width(
    *, members_w: float, furniture_ink: float, pads: float, air: float = 0.0, floor: float = 0.0
) -> float:
    """``max(floor, members_w, furniture_ink + pads + air)``.

    ``members_w`` is the widest member the container encloses; ``furniture_ink``
    is the measured ink of the header, count badge, legend, or label it
    carries; ``pads`` is the sum of both interior pads; ``air`` is the clear
    gap the furniture pieces need between each other.
    """
    return max(floor, members_w, furniture_ink + pads + air)
