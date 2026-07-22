"""Genome role grouping — the recolor-by-intent data contract.

Roles are pure data (accent / surface / ink / status → token lists); the
loader validates them at startup so a phantom token or a roleless genome
fails every test run, not a user's recolor."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from hyperweave.cli import app
from hyperweave.config.loader import get_loader

runner = CliRunner()

_ROLE_KEYS = ("accent", "surface", "ink", "status")


def test_every_built_in_genome_declares_roles() -> None:
    for gid, genome in get_loader().genomes.items():
        roles = genome.get("roles") or {}
        assert roles, f"genome {gid!r} ships no roles grouping"
        assert set(roles) == set(_ROLE_KEYS), f"genome {gid!r} roles keys drift: {sorted(roles)}"


def test_role_tokens_resolve_to_real_genome_fields() -> None:
    """A role naming a phantom token would make recolor-by-intent a silent
    no-op — every listed token must be a truthy field on its genome."""
    for gid, genome in get_loader().genomes.items():
        for role, tokens in (genome.get("roles") or {}).items():
            for token in tokens:
                assert genome.get(token), f"{gid}: role {role!r} names phantom token {token!r}"


def test_every_chromatic_token_is_role_assigned() -> None:
    """Coverage is the other direction: no chromatic token floats outside the
    role grouping (an unassigned token is invisible to intent-driven tools)."""
    import re

    hexish = re.compile(r"^#|^rgba?\(|^linear-gradient|^radial-gradient")
    for gid, genome in get_loader().genomes.items():
        assigned = {t for tokens in (genome.get("roles") or {}).values() for t in tokens}
        chromatic = {k for k, v in genome.items() if isinstance(v, str) and hexish.match(v) and k != "roles"}
        floating = chromatic - assigned
        assert not floating, f"{gid}: chromatic tokens outside any role: {sorted(floating)}"


def test_genome_explain_prints_the_role_breakdown() -> None:
    result = runner.invoke(app, ["genomes", "primer", "--explain"])
    assert result.exit_code == 0, result.output
    for role in _ROLE_KEYS:
        assert f"{role}:" in result.stdout
    assert "accent_signal" in result.stdout


def test_genome_explain_without_id_names_the_fix() -> None:
    result = runner.invoke(app, ["genomes", "--explain"])
    assert result.exit_code == 2
    assert "genomes <id> --explain" in result.stderr


def test_discover_genome_selector_returns_role_structured_tokens() -> None:
    from hyperweave.surfaces.discover import discover

    deep = discover("genome:primer")["genome"]
    assert deep["id"] == "primer"
    assert deep["roles"]["accent"]["accent"].startswith("#")
    assert "diagram" in deep["paradigms"]
    assert deep["variants"]


def test_discover_genome_selector_rejects_unknown_id() -> None:
    from hyperweave.core.errors import HwError
    from hyperweave.surfaces.discover import discover

    with pytest.raises(HwError) as exc_info:
        discover("genome:vellum-nope")
    assert "primer" in (exc_info.value.fix or "")


def test_unclaimed_chromatic_token_fails_at_config_load() -> None:
    """The reverse direction is loader-enforced, not test-only: a chromatic
    token no role claims fails loud the moment config loads."""
    from hyperweave.compose.validate_paradigms import validate_genome_chromatic_coverage

    spec = get_loader().genome_specs["primer"]
    validate_genome_chromatic_coverage(spec)  # intact genome passes

    thinned = {role: [t for t in tokens if t != "accent"] for role, tokens in spec.roles.items()}
    broken = spec.model_copy(update={"roles": thinned})
    with pytest.raises(ValueError, match="'accent' is claimed by no role"):
        validate_genome_chromatic_coverage(broken)


def test_explain_and_discover_genome_share_one_extraction() -> None:
    """The CLI breakdown and the discover deep-dive render the same values —
    pinned so a future edit to one face cannot silently drift the other."""
    from hyperweave.surfaces.discover import discover, genome_deep_dive

    deep = discover("genome:primer")["genome"]
    assert deep == genome_deep_dive("primer")
    out = runner.invoke(app, ["genomes", "primer", "--explain"]).stdout
    assert deep["roles"]["accent"]["accent"] in out
