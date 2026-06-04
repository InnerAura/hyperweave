"""Unit tests for the three-mode state architecture in compose/layout.py.

Three modes drive two orthogonal render-time behaviors (indicator
rendering and threshold-CSS auto-inference). The mode-resolution
contract is what every badge resolver depends on — these tests pin it.

Allowlist for tests is constructed locally (not loaded from disk) so
the test contract is independent of the data/badge_modes.yaml content
and so individual cases stay legible.
"""

from __future__ import annotations

from hyperweave.compose.layout import (
    data_hw_statemode_for,
    decide_strip_mode,
    resolve_badge_mode,
)
from hyperweave.core.models import ComposeSpec

ALLOWLIST = frozenset({"build", "coverage", "lint", "ci"})


def _spec(*, title: str, value: str = "", state: str = "active") -> ComposeSpec:
    return ComposeSpec(
        type="badge",
        genome_id="brutalist",
        title=title,
        value=value,
        state=state,
    )


# ─────────────────────────────────────────────────────────────────────
# resolve_badge_mode — three-mode classification
# ─────────────────────────────────────────────────────────────────────


def test_explicit_state_wins_over_allowlist() -> None:
    """A user passing ?state= sets explicit mode, regardless of title."""
    assert resolve_badge_mode(_spec(title="STARS", state="warning"), ALLOWLIST) == "explicit"
    assert resolve_badge_mode(_spec(title="BUILD", state="passing"), ALLOWLIST) == "explicit"


def test_stateful_when_title_in_allowlist() -> None:
    """Allowlisted titles with the default ``active`` state get stateful mode."""
    assert resolve_badge_mode(_spec(title="BUILD"), ALLOWLIST) == "stateful"
    assert resolve_badge_mode(_spec(title="coverage"), ALLOWLIST) == "stateful"  # already lowercase


def test_stateless_when_title_not_in_allowlist() -> None:
    """STARS, FORKS, VERSION etc. default to stateless. No indicator,
    no auto-inference. The orange-diamond-on-6-stars false-alarm fix."""
    assert resolve_badge_mode(_spec(title="STARS", value="42"), ALLOWLIST) == "stateless"
    assert resolve_badge_mode(_spec(title="VERSION", value="0.2.23"), ALLOWLIST) == "stateless"
    assert resolve_badge_mode(_spec(title="LICENSE", value="MIT"), ALLOWLIST) == "stateless"


def test_custom_title_defaults_to_stateless() -> None:
    """Future custom titles like WATCHERS / DOWNLOADS default to stateless,
    so unknown badge types don't accidentally pick up state semantics."""
    assert resolve_badge_mode(_spec(title="WATCHERS", value="99"), ALLOWLIST) == "stateless"
    assert resolve_badge_mode(_spec(title="DOWNLOADS", value="1.2k"), ALLOWLIST) == "stateless"


def test_lowercase_normalization_applied() -> None:
    """spec.title.lower() before allowlist lookup — case-agnostic."""
    assert resolve_badge_mode(_spec(title="BUILD"), ALLOWLIST) == "stateful"
    assert resolve_badge_mode(_spec(title="Build"), ALLOWLIST) == "stateful"
    assert resolve_badge_mode(_spec(title="build"), ALLOWLIST) == "stateful"


def test_separator_normalization_applied() -> None:
    """Hyphens and underscores stripped before allowlist lookup so
    BUILD-STATUS, CI_CD, etc. match canonical joined forms without
    bloating the YAML with every separator variant."""
    al = frozenset({"buildstatus", "cicd", "prchecks"})
    assert resolve_badge_mode(_spec(title="BUILD-STATUS"), al) == "stateful"
    assert resolve_badge_mode(_spec(title="CI_CD"), al) == "stateful"
    assert resolve_badge_mode(_spec(title="ci-cd"), al) == "stateful"
    assert resolve_badge_mode(_spec(title="PR-Checks"), al) == "stateful"
    # Different word entirely — still stateless even after normalization
    assert resolve_badge_mode(_spec(title="foo-bar"), al) == "stateless"


def test_real_world_ci_titles_match_default_allowlist() -> None:
    """Verify the shipped data/badge_modes.yaml covers the common
    real-world badge titles users put in their READMEs. This is the
    regression-prevention test for the v0.2.25 narrowing — pre-fix
    these titles all auto-inferred state for any title; post-fix
    they MUST be allowlisted or we silently drop indicators users
    were relying on."""
    from hyperweave.config.loader import load_badge_modes

    real = load_badge_modes()
    must_match = [
        "BUILD",
        "TESTS",
        "TEST",
        "CI",
        "CICD",
        "CI-CD",
        "CI_CD",
        "PIPELINE",
        "WORKFLOW",
        "CHECKS",
        "LINT",
        "LINTING",
        "COVERAGE",
        "CODECOV",
        "QUALITY",
        "SCORE",
        "DEPLOY",
        "DEPLOYMENT",
        "RELEASE",
        "RELEASES",
        "STATUS",
        "HEALTH",
        "UPTIME",
        "BUILD-STATUS",
        "PR-CHECKS",
        "E2E",
        "INTEGRATION",
    ]
    misses = [t for t in must_match if resolve_badge_mode(_spec(title=t), real) != "stateful"]
    assert misses == [], f"Real-world CI/CD titles fell through to stateless: {misses}"


def test_active_sentinel_falls_through() -> None:
    """ComposeSpec defaults state to 'active' (truthy sentinel). The mode
    resolver must NOT treat that as explicit — it means 'user did not
    opine'. This is the subtle semantic the impl-note guards."""
    spec = _spec(title="STARS")  # state defaults to "active"
    assert spec.state == "active"
    assert resolve_badge_mode(spec, ALLOWLIST) == "stateless"


def test_empty_title_yields_stateless() -> None:
    """No title — no allowlist match possible — stateless."""
    assert resolve_badge_mode(_spec(title=""), ALLOWLIST) == "stateless"


# ─────────────────────────────────────────────────────────────────────
# decide_strip_mode — strip rollup
# ─────────────────────────────────────────────────────────────────────


def test_strip_explicit_state_wins() -> None:
    spec = _spec(title="strip", state="warning")
    assert decide_strip_mode(["STARS", "FORKS"], spec, ALLOWLIST) == "explicit"


def test_strip_stateful_when_any_metric_allowlisted() -> None:
    """Mixed metrics: BUILD | STARS | VERSION → stateful (rolled-up
    indicator renders). Per design-decision D6 in the v0.2.25 plan,
    the strip's right-edge indicator is the strip's overall health
    pixel; if any metric carries semantic state, the indicator fires."""
    spec = _spec(title="repo")
    assert decide_strip_mode(["BUILD", "STARS", "VERSION"], spec, ALLOWLIST) == "stateful"


def test_strip_stateless_when_all_metrics_neutral() -> None:
    """STARS | FORKS | VERSION → all stateless → no indicator."""
    spec = _spec(title="repo")
    assert decide_strip_mode(["STARS", "FORKS", "VERSION"], spec, ALLOWLIST) == "stateless"


def test_strip_explicit_overrides_metric_rollup() -> None:
    """User-set state wins even when no metrics are allowlisted."""
    spec = _spec(title="repo", state="critical")
    assert decide_strip_mode(["STARS", "FORKS"], spec, ALLOWLIST) == "explicit"


def test_strip_handles_empty_metric_list() -> None:
    spec = _spec(title="repo")
    assert decide_strip_mode([], spec, ALLOWLIST) == "stateless"


def test_strip_handles_none_titles() -> None:
    """Defensive: a metric with no title doesn't crash the rollup."""
    spec = _spec(title="repo")
    assert decide_strip_mode([None, "BUILD"], spec, ALLOWLIST) == "stateful"


# ─────────────────────────────────────────────────────────────────────
# data_hw_statemode_for — attribute-value mapping
# ─────────────────────────────────────────────────────────────────────


def test_attribute_mapping() -> None:
    assert data_hw_statemode_for("stateful") == "auto"
    assert data_hw_statemode_for("explicit") == "explicit"
    assert data_hw_statemode_for("stateless") == "off"


def test_only_auto_triggers_threshold_css() -> None:
    """Documents the contract: ``data-hw-statemode='auto'`` is the only
    value that matches the qualified threshold-CSS selectors in
    data/css/expression.css. The OTHER two values (explicit, off) flow
    through but don't trigger leading-digit auto-tinting — explicit
    state comes from spec.state via the data-hw-status cascade,
    stateless gets no tinting at all."""
    assert data_hw_statemode_for("stateful") == "auto"
    assert data_hw_statemode_for("explicit") != "auto"
    assert data_hw_statemode_for("stateless") != "auto"


# ─────────────────────────────────────────────────────────────────────
# DOM assertion: stateless badge has zero status-zone elements
# ─────────────────────────────────────────────────────────────────────


def test_stateless_svg_has_no_status_zone_element() -> None:
    """End-to-end DOM assertion using the actual compose() pipeline.

    Catches regressions that would re-introduce the unconditional
    indicator emission in chrome/brutalist content templates.
    """
    import xml.etree.ElementTree as ET

    from hyperweave.compose.engine import compose

    spec = _spec(title="STARS", value="42")  # stateless — not in allowlist
    result = compose(spec)
    root = ET.fromstring(result.svg)
    ns = "{http://www.w3.org/2000/svg}"
    status_zones = root.findall(f".//{ns}g[@data-hw-zone='status']")
    assert status_zones == [], (
        f"Stateless STARS badge has {len(status_zones)} status-zone "
        f"<g> elements; expected 0. The threshold-CSS gating fix relies "
        f"on these not rendering at all on stateless badges."
    )


def test_stateful_svg_has_one_status_zone_element() -> None:
    import xml.etree.ElementTree as ET

    from hyperweave.compose.engine import compose

    spec = _spec(title="BUILD", value="passing")  # stateful — in allowlist
    result = compose(spec)
    root = ET.fromstring(result.svg)
    ns = "{http://www.w3.org/2000/svg}"
    status_zones = root.findall(f".//{ns}g[@data-hw-zone='status']")
    assert len(status_zones) == 1, (
        f"Stateful BUILD badge has {len(status_zones)} status-zone <g> elements; expected exactly 1."
    )


def test_explicit_state_svg_has_one_status_zone_element() -> None:
    import xml.etree.ElementTree as ET

    from hyperweave.compose.engine import compose

    spec = _spec(title="STARS", value="42", state="warning")
    result = compose(spec)
    root = ET.fromstring(result.svg)
    ns = "{http://www.w3.org/2000/svg}"
    status_zones = root.findall(f".//{ns}g[@data-hw-zone='status']")
    assert len(status_zones) == 1, (
        f"Explicit ?state=warning STARS badge has {len(status_zones)} "
        f"status-zone <g> elements; expected exactly 1 (user-set state "
        f"survives the stateless-by-title default)."
    )
