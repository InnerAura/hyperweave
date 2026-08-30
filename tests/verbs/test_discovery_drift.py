"""The enum-drift gate and the agent capsule.

The gate is the load-bearing half of the contract: every vocabulary string a
discovery surface prints derives from — or is tested against — the live enums
and legality config, so a discovery answer can never omit a member (beam,
pill were the two live escapes) or invent one. The capsule is the compact
derived contract an agent reads instead of the full schema dump; its digest
lets a caller cache it and skip the rediscovery ritual.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from hyperweave.core.diagram import EdgeKind, EdgeMotion, NodeRole, NodeStyle, Topology
from hyperweave.core.errors import HwError, HwErrorCode
from hyperweave.surfaces.discover import agent_capsule, discover

runner = CliRunner()


def _head_members(prose: str) -> set[str]:
    """The `a | b | c` head of a vocabulary string, before its ` — ` prose."""
    return {p.strip() for p in prose.split(" — ", 1)[0].split("|")}


class TestEnumDriftGate:
    """A discovery string that omits or invents an enum member fails here —
    the walk `20-` specifies, closed over NodeStyle, EdgeMotion, EdgeKind,
    and the legality tables."""

    def test_edge_motion_prose_matches_the_enum_exactly(self) -> None:
        prose = discover("diagram")["diagram"]["edge_motion"]
        assert _head_members(prose) == {m.value for m in EdgeMotion if m.value}

    def test_node_styles_prose_matches_the_enum_exactly(self) -> None:
        prose = discover("diagram")["diagram"]["node_styles"]
        assert _head_members(prose) == {s.value for s in NodeStyle if s.value}

    def test_edge_kinds_appear_in_the_diagram_section(self) -> None:
        section = json.dumps(discover("diagram")["diagram"])
        for kind in (k.value for k in EdgeKind if k.value):
            assert kind in section

    def test_capsule_vocabulary_is_the_enums_verbatim(self) -> None:
        vocab = agent_capsule()["vocabulary"]
        assert vocab["edge_motion"] == [m.value for m in EdgeMotion if m.value]
        assert vocab["node_styles"] == [s.value for s in NodeStyle if s.value]
        assert vocab["edge_kinds"] == [k.value for k in EdgeKind if k.value]
        assert vocab["roles"] == [r.value for r in NodeRole if r.value]

    def test_every_topology_has_a_family_entry_with_legality(self) -> None:
        families = agent_capsule()["families"]
        assert set(families) == {t.value for t in Topology}
        for fam in families.values():
            assert fam["orientations"], "every family declares its legal orientations"


class TestAgentCapsule:
    def test_single_digit_kilobytes_with_stable_digest(self) -> None:
        full = agent_capsule()
        assert len(json.dumps(full)) < 9_000
        assert full["schema"] == "capsule/1"
        assert full["digest"].startswith("sha256:")
        assert agent_capsule()["digest"] == full["digest"]

    def test_topology_scope_shrinks_and_changes_the_digest(self) -> None:
        full, loop = agent_capsule(), agent_capsule("loop")
        assert set(loop["families"]) == {"loop"}
        assert len(json.dumps(loop)) < len(json.dumps(full))
        assert loop["digest"] != full["digest"]
        assert loop["families"]["loop"]["presets"], "the family lists its bundled presets"

    def test_unknown_topology_refuses_with_the_menu(self) -> None:
        with pytest.raises(HwError) as exc:
            agent_capsule("blob")
        assert exc.value.code is HwErrorCode.TOPOLOGY_UNKNOWN
        assert "loop" in exc.value.fix

    def test_capsule_caps_match_the_engine_config(self) -> None:
        from hyperweave.config.loader import load_diagram_config

        caps = (load_diagram_config().get("caps") or {}).get("layouts") or {}
        seq = agent_capsule("sequence")["families"]["sequence"]["caps"]
        assert seq["sequence"] == caps["sequence"]


class TestCapsuleThroughRealCli:
    def test_agent_flag_prints_the_capsule(self) -> None:
        from hyperweave.cli import app

        result = runner.invoke(app, ["discover", "--agent", "--topology", "loop"])
        assert result.exit_code == 0
        doc = json.loads(result.stdout)
        assert doc["capsule"]["scope"] == "loop"
        assert doc["capsule"]["digest"].startswith("sha256:")

    def test_needs_appends_extra_sections(self) -> None:
        from hyperweave.cli import app

        result = runner.invoke(app, ["discover", "--agent", "--needs", "motions"])
        assert result.exit_code == 0
        doc = json.loads(result.stdout)
        assert "capsule" in doc and "motions" in doc

    def test_topology_without_agent_refuses(self) -> None:
        from hyperweave.cli import app

        result = runner.invoke(app, ["discover", "--topology", "loop"])
        assert result.exit_code == 2
        assert "--agent" in result.output
