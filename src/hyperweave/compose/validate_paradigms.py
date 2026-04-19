"""Genome/paradigm cross-validation at the compose/load boundary.

This module enforces that any genome opting into a paradigm declares
every genome field that paradigm requires. It deliberately lives
outside :mod:`hyperweave.core.schema` so ``GenomeSpec`` remains
self-contained — the cross-cutting check needs ParadigmSpec data loaded
from config, which would create a circular dependency if embedded as a
Pydantic ``@model_validator`` on ``GenomeSpec``.

Invoked once at load time by :class:`hyperweave.config.loader.ConfigLoader`
after both ``load_genomes()`` and ``load_paradigms()`` have populated
their caches. Raises ``ValueError`` with a structured message listing
every ``(paradigm_slug, required_field)`` violation across the genome
so a single run surfaces the complete remediation list.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hyperweave.core.paradigm import ParadigmSpec
    from hyperweave.core.schema import GenomeSpec


def validate_genome_against_paradigms(
    genome: GenomeSpec,
    paradigms: dict[str, ParadigmSpec],
) -> None:
    """Assert that ``genome`` declares every field required by its paradigms.

    Walks the set of paradigm slugs referenced by ``genome.paradigms``;
    for each slug, looks up ``ParadigmSpec.requires_genome_fields`` and
    checks that ``getattr(genome, field)`` is non-empty (truthy). Empty
    strings and empty lists are treated as missing — they are the shape
    the old ``| default(...)`` fallbacks were activating on.

    Unknown paradigm slugs are silently skipped; they dispatch to the
    ``default`` paradigm at render time, which has no requirements.

    :raises ValueError: if any paradigm declares a requirement the genome
        does not fulfill. Message enumerates every violation in one pass.
    """
    declared_slugs = set((genome.paradigms or {}).values())

    missing: dict[str, list[str]] = {}
    for slug in declared_slugs:
        paradigm = paradigms.get(slug)
        if paradigm is None:
            continue
        for field in paradigm.requires_genome_fields:
            value = getattr(genome, field, None)
            if not value:
                missing.setdefault(slug, []).append(field)

    if missing:
        lines = [f"  paradigm '{slug}' requires: {', '.join(fields)}" for slug, fields in sorted(missing.items())]
        raise ValueError(f"Genome '{genome.id}' opts into paradigms with missing required fields:\n" + "\n".join(lines))
