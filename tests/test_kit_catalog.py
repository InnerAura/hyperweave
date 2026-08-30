"""Kit authority guards — the predicates are packaged truth, the catalog is
generated, and neither may drift from the live engine.

The always-on half guards the packaged authority
(``data/registries/kit-predicates.yaml``): it loads, and every enum token its
rules reference exists in the live vocabulary — the walk that caught ``beam``
and ``pill`` escaping discovery guards the activation rules the same way.

The catalog half runs wherever the generated skill catalog exists (the owner's
checkout now; the committed tree at the release's readiness commit) and skips
elsewhere — same pattern as the plugin-manifest guard. A hand-authored catalog
guessed five activation rules and got four wrong and shipped a stale
``source_version``; these guards make both failure classes impossible to
re-ship silently.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from hyperweave.config.loader import load_diagram_presets, load_kit_predicates
from hyperweave.core.diagram import EdgeKind, NodeStyle, Topology

_ROOT = Path(__file__).resolve().parents[1]
_SKILL_DIR = Path(os.environ.get("HW_SKILL_DIR", _ROOT / "skills" / "hyperweave"))
_CATALOG = _SKILL_DIR / "references" / "kit-catalog.json"


class TestPackagedAuthority:
    def test_predicates_load_from_the_package(self) -> None:
        parts = load_kit_predicates()
        assert len(parts) >= 40, "the activation authority ships in package data"

    def test_rule_vocabulary_matches_the_live_enums(self) -> None:
        # Every node_style / topology / edge-kind token a rule references must
        # be a live enum member — an activation rule naming a retired or
        # invented member activates nothing, silently.
        styles = {s.value for s in NodeStyle if s.value}
        topologies = {t.value for t in Topology}
        kinds = {k.value for k in EdgeKind if k.value}

        def _tokens(expected: Any) -> list[Any]:
            if isinstance(expected, dict):
                return list(expected.get("any_of", []))
            if isinstance(expected, list):
                return list(expected)
            return [expected]

        for part_id, rule in load_kit_predicates().items():
            for clause, body in rule.items():
                if clause == "census" or not isinstance(body, dict):
                    continue
                for field_name, expected in body.items():
                    values = [v for v in _tokens(expected) if isinstance(v, str)]
                    if field_name == "node_style":
                        assert set(values) <= styles, f"{part_id}: unknown node_style in {values}"
                    elif field_name == "topology":
                        assert set(values) <= topologies, f"{part_id}: unknown topology in {values}"
                    elif field_name == "kind" and clause in ("any_edge", "no_edge"):
                        assert set(values) <= kinds, f"{part_id}: unknown edge kind in {values}"


catalog_present = pytest.mark.skipif(
    not _CATALOG.is_file(), reason="generated kit catalog not present in this checkout (untracked until release)"
)


@catalog_present
class TestGeneratedCatalog:
    def _load(self) -> dict[str, Any]:
        return json.loads(_CATALOG.read_text())

    def test_catalog_is_generated_never_hand_authored(self) -> None:
        catalog = self._load()
        assert catalog["schema"] == "hyperweave-kit-catalog/2"
        assert "GENERATED" in catalog["authority"] and "do not hand-edit" in catalog["authority"]

    def test_source_version_matches_the_package(self) -> None:
        from hyperweave import __version__

        declared = self._load()["source_version"]
        release = __version__.split("+")[0].split(".dev")[0]
        if release == __version__:
            assert declared == release, f"catalog stamped {declared} against released {release}"
        else:
            assert declared.count(".") == 2  # dev window: last release; closes at the readiness commit

    def test_counts_match_the_parts(self) -> None:
        catalog = self._load()
        parts = catalog["parts"]
        assert catalog["counts"]["parts"] == len(parts)
        assert catalog["counts"]["authorable"] == sum(1 for e in parts if e["ownership"] == "authorable")

    def test_every_proof_names_a_bundled_preset(self) -> None:
        presets = set(load_diagram_presets())
        for entry in self._load()["parts"]:
            proof = entry.get("proof") or {}
            for key in ("declared", "evaluated"):
                name = proof.get(key)
                assert name is None or name == "" or name in presets, (
                    f"{entry['id']}: {key} proof {name!r} is not bundled"
                )

    def test_authority_parts_all_appear_in_the_catalog(self) -> None:
        ids = {e["id"] for e in self._load()["parts"]}
        missing = set(load_kit_predicates()) - ids
        assert not missing, f"authority parts absent from the catalog: {sorted(missing)}"

    def test_skill_references_resolve(self) -> None:
        # No shipped reference may point at a file that no longer exists.
        import re

        skill = (_SKILL_DIR / "SKILL.md").read_text()
        for link in re.findall(r"\]\(((?:references|assets)/[^)]+)\)", skill):
            assert (_SKILL_DIR / link).is_file(), f"SKILL.md links a missing file: {link}"
