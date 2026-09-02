"""Shared relational geometry: text fit, bounds, path flattening, containers.

Every solver calls this layer; none reimplements it. The modules hold
relations, not family constants — a card, a lane band, a matrix column, and
a masthead pill all size their text through :mod:`.text`, clip their wires
through :mod:`.bounds` and :mod:`.paths`, and size their enclosure through
:mod:`.containers`.
"""
