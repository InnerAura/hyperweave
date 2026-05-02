#!/usr/bin/env python3
"""Stress test: exercise HyperWeave through CLI, HTTP API, and MCP server.

Generates artifacts across all frame types, genomes, substrates, and states
through all three interfaces. Outputs to outputs/stress-test/.

Usage:
    PYTHONPATH=src python3 scripts/stress_test.py
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from pathlib import Path

OUT = Path("outputs/stress-test")

# ── Test matrix ──

GENOMES = [
    "brutalist",
    "chrome",
]
SUBSTRATES = ["flat", "tectonic", "specular", "temporal", "parchment"]
STATES = ["active", "warning", "critical", "building", "offline"]
GLYPH_MODES = ["auto", "fill", "wire"]

BADGE_SPECS: list[dict[str, str]] = [
    {"title": "build", "desc": "passing", "glyph": "github", "state": "active"},
    {"title": "coverage", "desc": "94%", "glyph": "", "state": "active"},
    {"title": "version", "desc": "v0.1.0", "glyph": "", "state": "active"},
    {"title": "python", "desc": ">=3.12", "glyph": "python", "state": "active"},
    {"title": "docker", "desc": "1.2M pulls", "glyph": "docker", "state": "active"},
    {"title": "npm", "desc": "v2.3.1", "glyph": "npm", "state": "active"},
    {"title": "build", "desc": "failing", "glyph": "github", "state": "critical"},
    {"title": "build", "desc": "unstable", "glyph": "github", "state": "warning"},
]

STRIP_SPECS: list[dict[str, str]] = [
    {"title": "readme-ai", "metrics": "VERSION:v0.6.9,STARS:12.4k,FORKS:1.2k,COVERAGE:94%"},
    {"title": "hyperweave", "metrics": "VERSION:v0.1.0,STATUS:active"},
]

DIVIDER_VARIANTS: list[str] = [
    "block",
    "current",
    "takeoff",
    "void",
    "zeropoint",
]

ICON_GLYPHS = ["github", "python", "docker", "react", "rust", "kubernetes"]


class StressCounter:
    """Tracks pass/fail counts per interface."""

    def __init__(self) -> None:
        self.passed: dict[str, int] = {"cli": 0, "api": 0, "mcp": 0, "direct": 0}
        self.failed: dict[str, int] = {"cli": 0, "api": 0, "mcp": 0, "direct": 0}
        self.errors: list[str] = []
        self.start = time.monotonic()

    def record(self, interface: str, ok: bool, label: str = "") -> None:
        if ok:
            self.passed[interface] += 1
        else:
            self.failed[interface] += 1
            if label:
                self.errors.append(f"[{interface}] {label}")

    def summary(self) -> str:
        elapsed = time.monotonic() - self.start
        total = sum(self.passed.values()) + sum(self.failed.values())
        lines = [
            f"\n{'=' * 60}",
            f"STRESS TEST SUMMARY — {total} artifacts in {elapsed:.1f}s",
            f"{'=' * 60}",
        ]
        for iface in ["direct", "cli", "api", "mcp"]:
            p, f = self.passed[iface], self.failed[iface]
            status = "PASS" if f == 0 else "FAIL"
            lines.append(f"  {iface:<8} {p:>4} passed  {f:>4} failed  [{status}]")
        if self.errors:
            lines.append(f"\nErrors ({len(self.errors)}):")
            for e in self.errors[:20]:
                lines.append(f"  - {e}")
            if len(self.errors) > 20:
                lines.append(f"  ... and {len(self.errors) - 20} more")
        lines.append(f"{'=' * 60}")
        return "\n".join(lines)


counter = StressCounter()


# ═══════════════════════════════════════════════════════════
# Interface 1: Direct Python (compose engine)
# ═══════════════════════════════════════════════════════════


def direct_compose(
    frame: str,
    genome: str,
    title: str = "",
    desc: str = "",
    state: str = "active",
    glyph: str = "",
    substrate: str = "flat",
    glyph_mode: str = "auto",
    terminal: str = "diamond",
    rule_style: str = "straight",
    variant: str = "default",
) -> str | None:
    """Compose directly through Python engine."""
    try:
        from hyperweave.compose.engine import compose
        from hyperweave.core.models import ComposeSpec

        spec = ComposeSpec(
            type=frame,
            genome_id=genome,
            title=title,
            description=desc,
            state=state,
            glyph=glyph,
            substrate=substrate,
            glyph_mode=glyph_mode,
            terminal=terminal,
            rule_style=rule_style,
            variant=variant,
            metadata_tier=3,
        )
        result = compose(spec)
        return result.svg
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════
# Interface 2: CLI (subprocess)
# ═══════════════════════════════════════════════════════════


def cli_compose(
    frame: str,
    genome: str,
    title: str = "",
    value: str = "",
    state: str = "active",
    glyph: str = "",
    substrate: str = "flat",
    terminal: str = "diamond",
    rule_style: str = "straight",
) -> str | None:
    """Compose via CLI subprocess."""
    cmd = [
        sys.executable,
        "-m",
        "hyperweave",
        "compose",
        frame,
        title,
        value,
        "--genome",
        genome,
        "--state",
        state,
        "--substrate",
        substrate,
    ]
    if glyph:
        cmd.extend(["--glyph", glyph])
    if frame == "divider":
        cmd.extend(["--terminal", terminal, "--rule", rule_style])

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env={**__import__("os").environ, "PYTHONPATH": "src"},
        )
        if proc.returncode != 0:
            return None
        return proc.stdout if proc.stdout.strip().startswith("<svg") else None
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════
# Interface 3: HTTP API (in-process TestClient)
# ═══════════════════════════════════════════════════════════


def api_compose(
    frame: str,
    genome: str,
    title: str = "",
    desc: str = "",
    state: str = "active",
    glyph: str = "",
    substrate: str = "flat",
    terminal: str = "diamond",
    rule_style: str = "straight",
    variant: str = "default",
) -> str | None:
    """Compose via HTTP API POST endpoint (in-process TestClient)."""
    try:
        from starlette.testclient import TestClient

        from hyperweave.serve.app import app

        client = TestClient(app)
        resp = client.post(
            "/v1/compose",
            json={
                "type": frame,
                "genome": genome,
                "title": title,
                "description": desc,
                "state": state,
                "glyph": glyph,
                "substrate": substrate,
                "terminal": terminal,
                "rule_style": rule_style,
                "variant": variant,
            },
        )
        if resp.status_code == 200 and resp.text.strip().startswith("<svg"):
            return resp.text
        return None
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════
# Interface 4: MCP Server (in-process tool call)
# ═══════════════════════════════════════════════════════════


async def mcp_compose(
    frame: str,
    genome: str,
    title: str = "",
    value: str = "",
    state: str = "active",
    glyph: str = "",
    substrate: str = "flat",
    terminal: str = "diamond",
    rule_style: str = "straight",
) -> str | None:
    """Compose via MCP server tool (direct async call)."""
    try:
        from hyperweave.mcp.server import hw_compose

        svg = await hw_compose(
            type=frame,
            label=title,
            value=value,
            genome=genome,
            state=state,
            glyph=glyph,
            substrate=substrate,
            terminal=terminal,
            rule_style=rule_style,
        )
        if svg and svg.strip().startswith("<svg"):
            return svg
        return None
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════
# Test Suites
# ═══════════════════════════════════════════════════════════


def _save(svg: str | None, path: Path, interface: str, label: str) -> None:
    """Save SVG and record result."""
    if svg:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(svg)
        counter.record(interface, True)
    else:
        counter.record(interface, False, label)


def run_direct_tests() -> None:
    """Full matrix through direct Python compose."""
    print("  [direct] Running full matrix...")
    for genome in GENOMES:
        gdir = OUT / "direct" / genome

        # Badges
        for spec in BADGE_SPECS:
            svg = direct_compose("badge", genome, **spec)
            name = f"badge_{spec['title']}_{spec['state']}"
            _save(svg, gdir / f"{name}.svg", "direct", name)

        # Strips
        for spec in STRIP_SPECS:
            svg = direct_compose("strip", genome, spec["title"], spec["metrics"])
            _save(svg, gdir / f"strip_{spec['title']}.svg", "direct", f"strip_{spec['title']}")

        # Icons
        for glyph in ICON_GLYPHS:
            svg = direct_compose("icon", genome, glyph, "", "active", glyph)
            _save(svg, gdir / f"icon_{glyph}.svg", "direct", f"icon_{glyph}")

        # Dividers (specimen variants only)
        for var in DIVIDER_VARIANTS:
            svg = direct_compose("divider", genome, "", "", variant=var)
            _save(svg, gdir / f"divider_{var}.svg", "direct", f"divider_{var}")

        # Marquee (horizontal-only since v0.2.14)
        svg = direct_compose("marquee-horizontal", genome, "HYPERWEAVE LIVING ARTIFACTS AI-NATIVE")
        _save(svg, gdir / "marquee-horizontal.svg", "direct", "marquee-horizontal")

        # Substrate matrix
        for sub in SUBSTRATES:
            svg = direct_compose("badge", genome, "build", "passing", "active", "github", sub)
            _save(svg, gdir / f"substrate_badge_{sub}.svg", "direct", f"substrate_{sub}")

        # Glyph modes
        for mode in GLYPH_MODES:
            svg = direct_compose("badge", genome, "build", "passing", "active", "github", glyph_mode=mode)
            _save(svg, gdir / f"glyph_mode_{mode}.svg", "direct", f"glyph_mode_{mode}")

        # State machine
        for state in STATES:
            svg = direct_compose("badge", genome, "build", state, state, "github")
            _save(svg, gdir / f"state_{state}.svg", "direct", f"state_{state}")


def run_cli_tests() -> None:
    """CLI interface tests (subset for speed)."""
    print("  [cli] Running CLI tests...")
    for genome in GENOMES:
        gdir = OUT / "cli" / genome

        # Badges
        for spec in BADGE_SPECS[:3]:
            svg = cli_compose("badge", genome, spec["title"], spec["desc"], spec["state"], spec.get("glyph", ""))
            name = f"badge_{spec['title']}_{spec['state']}"
            _save(svg, gdir / f"{name}.svg", "cli", name)

        # Strip
        svg = cli_compose("strip", genome, "readme-ai", "VERSION:v0.6.9,STARS:12.4k")
        _save(svg, gdir / "strip.svg", "cli", "strip")

        # Icon
        svg = cli_compose("icon", genome, "github", "", "active", "github")
        _save(svg, gdir / "icon.svg", "cli", "icon")

        # Divider
        svg = cli_compose("divider", genome, "", "", terminal="aurora", rule_style="wave")
        _save(svg, gdir / "divider.svg", "cli", "divider")


def run_api_tests() -> None:
    """HTTP API tests (in-process TestClient)."""
    print("  [api] Running API tests...")
    for genome in GENOMES:
        gdir = OUT / "api" / genome

        # POST compose — all frame types
        for spec in BADGE_SPECS[:4]:
            svg = api_compose("badge", genome, spec["title"], spec["desc"], spec["state"], spec.get("glyph", ""))
            name = f"badge_{spec['title']}_{spec['state']}"
            _save(svg, gdir / f"{name}.svg", "api", name)

        svg = api_compose("strip", genome, "readme-ai", "VERSION:v0.6.9,STARS:12.4k")
        _save(svg, gdir / "strip.svg", "api", "strip")

        svg = api_compose("icon", genome, "python", "", "active", "python")
        _save(svg, gdir / "icon.svg", "api", "icon")

        svg = api_compose("divider", genome, "", "")
        _save(svg, gdir / "divider.svg", "api", "divider")

    # URL grammar routes (GET)
    try:
        from starlette.testclient import TestClient

        from hyperweave.serve.app import app

        client = TestClient(app)

        url_tests = [
            ("/v1/compose/badge/build/passing/brutalist", "url_badge"),
            ("/v1/compose/badge/build/passing/chrome.breathe", "url_badge_motion"),
            ("/v1/compose/strip/readme-ai/STARS:12.4k/brutalist", "url_strip"),
            ("/v1/compose/icon/github/brutalist", "url_icon"),
            ("/v1/compose/divider/chrome?terminal=aurora&rule=wave", "url_divider"),
            ("/v1/compose/marquee/HYPERWEAVE/brutalist", "url_marquee"),
        ]

        for url, label in url_tests:
            resp = client.get(url)
            svg = resp.text if resp.status_code == 200 and resp.text.strip().startswith("<svg") else None
            _save(svg, OUT / "api" / "url-grammar" / f"{label}.svg", "api", f"GET {label}")

        # Discovery endpoints
        for endpoint in ["/v1/genomes", "/v1/motions", "/v1/substrates"]:
            resp = client.get(endpoint)
            ok = resp.status_code == 200
            counter.record("api", ok, f"GET {endpoint}")

    except Exception as exc:
        counter.record("api", False, f"URL grammar setup: {exc}")


async def run_mcp_tests() -> None:
    """MCP server tool tests (direct async call)."""
    print("  [mcp] Running MCP tests...")
    for genome in GENOMES:
        gdir = OUT / "mcp" / genome

        # Badges
        for spec in BADGE_SPECS[:3]:
            svg = await mcp_compose("badge", genome, spec["title"], spec["desc"], spec["state"], spec.get("glyph", ""))
            name = f"badge_{spec['title']}_{spec['state']}"
            _save(svg, gdir / f"{name}.svg", "mcp", name)

        # Strip (via hw_strip)
        try:
            from hyperweave.mcp.server import hw_strip

            svg = await hw_strip(title="readme-ai", metrics="VERSION:v0.6.9,STARS:12.4k", genome=genome)
            ok = svg and svg.strip().startswith("<svg")
            if ok:
                (gdir / "strip.svg").parent.mkdir(parents=True, exist_ok=True)
                (gdir / "strip.svg").write_text(svg)
            counter.record("mcp", bool(ok), "hw_strip")
        except Exception:
            counter.record("mcp", False, "hw_strip")

        # Marquee (via hw_marquee)
        try:
            from hyperweave.mcp.server import hw_marquee

            svg = await hw_marquee(type="horizontal", content="HYPERWEAVE LIVING ARTIFACTS", genome=genome)
            ok = svg and svg.strip().startswith("<svg")
            if ok:
                (gdir / "marquee.svg").parent.mkdir(parents=True, exist_ok=True)
                (gdir / "marquee.svg").write_text(svg)
            counter.record("mcp", bool(ok), "hw_marquee")
        except Exception:
            counter.record("mcp", False, "hw_marquee")

        # Genomes list
        try:
            from hyperweave.mcp.server import hw_genomes

            genomes_list = await hw_genomes()
            counter.record("mcp", len(genomes_list) > 0, "hw_genomes")
        except Exception:
            counter.record("mcp", False, "hw_genomes")


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════


def main() -> None:
    import shutil

    # Gut outputs/stress-test/
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    print("HyperWeave Stress Test")
    print("=" * 60)

    # 1. Direct compose (full matrix)
    run_direct_tests()

    # 2. CLI subprocess
    run_cli_tests()

    # 3. HTTP API (in-process)
    run_api_tests()

    # 4. MCP server (async)
    asyncio.run(run_mcp_tests())

    # Summary
    print(counter.summary())

    # Write report
    report = counter.summary()
    (OUT / "REPORT.txt").write_text(report)

    # Exit code
    total_failed = sum(counter.failed.values())
    sys.exit(1 if total_failed > 0 else 0)


if __name__ == "__main__":
    main()
