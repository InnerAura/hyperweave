"""ComposeSpec.variant field — Path B grammar (v0.2.19).

Scope: ComposeSpec accepts any string at construction time (no Pydantic
field_validator). Validation moves to resolve-time and is driven by the
genome's `variants` whitelist (declared in genome JSON). This locks both
contracts: the lenient model boundary AND the strict resolve-time check.
"""

from __future__ import annotations

import pytest

from hyperweave.compose.resolver import resolve
from hyperweave.core.models import ComposeSpec


def test_variant_defaults_to_empty() -> None:
    """Empty default = 'frame-type default, resolved by paradigm/genome'."""
    spec = ComposeSpec(type="badge")
    assert spec.variant == ""


@pytest.mark.parametrize("value", ["", "blue", "purple", "bifamily"])
def test_variant_accepts_automata_allowed_values(value: str) -> None:
    """Automata genome's variants list = ['blue', 'purple', 'bifamily']."""
    spec = ComposeSpec(type="badge", genome_id="automata", variant=value)
    resolved = resolve(spec)
    # Empty resolves via paradigm default; non-empty passes whitelist
    assert resolved.frame_context.get("variant", "") in {value, "blue", "bifamily"}


@pytest.mark.parametrize("value", ["teal", "amethyst", "BLUE", "Purple", "green"])
def test_variant_rejects_unknown_values_at_resolve_time(value: str) -> None:
    """Path B: validation is resolve-time against genome.variants, not Pydantic."""
    spec = ComposeSpec(type="badge", genome_id="automata", variant=value)
    # Construction succeeds (lenient field). Resolve-time raises.
    with pytest.raises(ValueError) as exc_info:
        resolve(spec)
    assert "variant" in str(exc_info.value)


def test_variant_accepts_anything_when_genome_has_no_variants_axis() -> None:
    """Genomes with empty `variants` list accept variant='' only (no axis)."""
    # brutalist has variants=[]; passing variant="" is fine
    spec = ComposeSpec(type="badge", genome_id="brutalist", variant="")
    resolve(spec)  # no error
