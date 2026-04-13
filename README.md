<div id="top">

<p align="center">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/f36c8969d15d76da4400ebcfaa04ec1e2eacb170/assets/hyperweave-banner.svg" alt="HyperWeave" width="800"/>
</p>

<p align="center">
  <strong>Headless visual output layer for AI agents.</strong><br/>
  One API call &rarr; self-contained SVG. No JavaScript. No dependencies. No runtime.<br/>
  Works everywhere an <code>&lt;img&gt;</code> tag works.
</p>

<!--
<p align="center">
  <img src="https://hyperweave.app/v1/live/github/InnerAura/hyperweave/stars/chrome-horizon.static" alt="stars"/>
  <img src="https://hyperweave.app/v1/live/github/InnerAura/hyperweave/forks/chrome-horizon.static" alt="forks"/>
  <img src="https://hyperweave.app/v1/live/pypi/hyperweave/version/chrome-horizon.static" alt="version"/>
  <img src="https://hyperweave.app/v1/live/github/InnerAura/hyperweave/license/chrome-horizon.static" alt="license"/>
  <img src="https://hyperweave.app/v1/live/pypi/hyperweave/python_requires/chrome-horizon.static" alt="python"/>
</p>
-->
<p align="center">
  <img src="https://hyperweave.app/v1/strip/hyperweave/chrome-horizon.static?live=github:InnerAura/hyperweave:build,pypi:hyperweave:version,github:InnerAura/hyperweave:license&glyph=github" alt="strip"/>
</p>

<!--
Safe, Auditable, Drop-Anywhere Visuals for your Agents.

---

"Hyperweave is the visual protocol for autonomous agents. We give AI agents the ability to generate high-fidelity, brand-aligned UI artifacts—roadmaps, telemetry, and status cards—so humans can monitor and trust agentic workflows."

---

HyperWeave is the visual artifact layer for modern software.
Generate branded, self-contained SVG outputs for profiles, repositories, docs, dashboards, and agent workflows.

“runtime-free visual compiler for structured machine outputs”

take structured state, compress it into an emotionally legible surface, and make it portable

"In a post-Mythos world, letting autonomous agents generate executable UI code (React/JS) is a catastrophic security risk. HyperWeave is the secure, stateless, verifiable visual protocol for the Agentic Web."

The Voiceover: "Agents don't need to generate heavy React apps that require hosting and runtimes. HyperWeave generates secure, zero-dependency SVG artifacts that travel to wherever your users actually work."
-->

---

## The Problem

When an AI agent needs visual output, it generates React code or HTML that breaks across platforms, carries no brand identity, and is illegible to the next agent in the chain. There's no portable, reliable visual primitive for agents.

HyperWeave is that primitive. Semantic SVGs with embedded CSS state machines, accessibility markup, and machine-readable metadata. The artifact stays live, stays on-brand, and stays legible &mdash; whether it's rendered in a GitHub README, Slack, Notion, documentation site, email, VS Code, or terminal. Every surface that renders an `<img>` tag is a HyperWeave surface.

---

## Genomes &mdash; Aesthetic DNA

A genome is a portable, machine-readable aesthetic specification. It encodes the complete visual identity &mdash; chromatic system, surface material, motion vocabulary, geometric form language &mdash; as a set of CSS custom properties that any agent can consume and apply consistently across every artifact type.

<!--
Why genome and not theme? Because brand isn't a design problem, it's an infrastructure problem. When an agent says "build me a status page," it has zero memory of visual identity. A genome solves that: define once, express everywhere, from a 90px badge to a full-width banner. The same genome produces different artifacts that feel like they came from the same hand.
-->

<table>
<tr>
<td></td>
<td align="center"><strong>brutalist-emerald</strong></td>
<td align="center"><strong>chrome-horizon</strong></td>
</tr>
<tr>
<td align="center"><strong>Signals</strong></td>
<td>
  <img src="https://hyperweave.app/v1/badge/BUILD/passing/brutalist-emerald.static?state=passing" alt="passing"/>
  <img src="https://hyperweave.app/v1/badge/BUILD/warning/brutalist-emerald.static?state=warning" alt="warning"/>
  <img src="https://hyperweave.app/v1/badge/BUILD/critical/brutalist-emerald.static?state=critical" alt="critical"/>
</td>
<td>
  <img src="https://hyperweave.app/v1/badge/BUILD/passing/chrome-horizon.static?state=passing" alt="passing"/>
  <img src="https://hyperweave.app/v1/badge/BUILD/warning/chrome-horizon.static?state=warning" alt="warning"/>
  <img src="https://hyperweave.app/v1/badge/BUILD/critical/chrome-horizon.static?state=critical" alt="critical"/>
</td>
</tr>
<tr>
<td align="center"><strong>Dashboard</strong></td>
<td><img src="https://hyperweave.app/v1/strip/readme-ai/brutalist-emerald.static?value=STARS:2.9k,FORKS:278"/></td>
<td><img src="https://hyperweave.app/v1/strip/readme-ai/chrome-horizon.static?value=STARS:2.9k,FORKS:278"/></td>
</tr>
<tr>
<td rowspan="2" align="center"><strong>Profile&nbsp;cards</strong></td>
<td><img src="assets/examples/brutalist-emerald/profile-cards/stats.svg" alt="stats" width="100%"/></td>
<td><img src="assets/examples/chrome-horizon/profile-cards/stats.svg" alt="stats" width="100%"/></td>
</tr>
<tr>
<td><img src="assets/examples/brutalist-emerald/profile-cards/chart_stars_full.svg" alt="star chart" width="100%"/></td>
<td><img src="assets/examples/chrome-horizon/profile-cards/chart_stars_full.svg" alt="star chart" width="100%"/></td>
</tr>
<tr>
<td rowspan="3" align="center"><strong>Marquee</strong></td>
<td><img src="https://hyperweave.app/v1/marquee/HYPERWEAVE%20%C2%B7%20LIVING%20ARTIFACTS%20%C2%B7%20INNERAURA%20LABS/brutalist-emerald.static?rows=1"/></td>
<td><img src="https://hyperweave.app/v1/marquee/HYPERWEAVE%20%C2%B7%20LIVING%20ARTIFACTS%20%C2%B7%20INNERAURA%20LABS/chrome-horizon.static?rows=1"/></td>
</tr>
<tr>
<!-- <td><img src="https://hyperweave.app/v1/marquee/HYPERWEAVE%7CLIVING%20ARTIFACTS%7CAI-NATIVE%20SVG%7CCOMPOSITOR%20API/brutalist-emerald.static?rows=3"/></td>
<td><img src="https://hyperweave.app/v1/marquee/HYPERWEAVE%7CLIVING%20ARTIFACTS%7CAI-NATIVE%20SVG%7CCOMPOSITOR%20API/chrome-horizon.static?rows=3"/></td> -->
</tr>
<tr>
<td><img src="https://hyperweave.app/v1/marquee/HYPERWEAVE%20%C2%B7%20LIVING%20ARTIFACTS%20%C2%B7%20INNERAURA%20LABS/brutalist-emerald.static?rows=1&direction=up"/></td>
<td><img src="https://hyperweave.app/v1/marquee/HYPERWEAVE%20%C2%B7%20LIVING%20ARTIFACTS%20%C2%B7%20INNERAURA%20LABS/chrome-horizon.static?rows=1&direction=up"/></td>
</tr>
<tr>
<td align="center"><strong>Icons<br/></strong></td>
<td>
  <img src="https://hyperweave.app/v1/icon/discord/brutalist-emerald.static?shape=circle" alt="discord" width="64"/>
  <img src="https://hyperweave.app/v1/icon/github/brutalist-emerald.static?shape=circle" alt="github" width="64"/>
  <img src="https://hyperweave.app/v1/icon/x/brutalist-emerald.static?shape=square" alt="x" width="64"/>
  <img src="https://hyperweave.app/v1/icon/spotify/brutalist-emerald.static?shape=square" alt="spotify" width="64"/>
</td>
<td>
  <img src="https://hyperweave.app/v1/icon/youtube/chrome-horizon.static?shape=circle" alt="youtube" width="64"/>
  <img src="https://hyperweave.app/v1/icon/notion/chrome-horizon.static?shape=circle" alt="notion" width="64"/>
  <img src="https://hyperweave.app/v1/icon/npm/chrome-horizon.static?shape=square" alt="npm" width="64"/>
  <img src="https://hyperweave.app/v1/icon/instagram/chrome-horizon.static?shape=square" alt="instagram" width="64"/>
</td>
</tr>
<tr>
<td align="center"><strong>Banner</strong></td>
<td><img src="https://hyperweave.app/v1/banner/HYPERWEAVE/brutalist-emerald.static"/></td>
<td><img src="https://hyperweave.app/v1/banner/HYPERWEAVE/chrome-horizon.static"/></td>
</tr>
</table>

| | brutalist-emerald | chrome-horizon |
|---|---|---|
| Surface | `#14532D` dark field | `#000a14` deep void |
| Signal | `#10B981` emerald | `#5ba3d4` metallic blue |
| Profile | brutalist (sharp, zero-radius) | chrome (smooth, env-mapped) |
| Motions | 5 border + 9 kinetic | 5 border only |

---

## Install

```bash
uv add hyperweave
# or
pip install hyperweave
```

Requires Python 3.12+.

---

## Entry Points

Four interfaces, one pipeline. Every path produces the same artifact through the same compositor.

<p align="center">
  <a href="https://hyperweave.app/docs/mcp">
    <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/f36c8969d15d76da4400ebcfaa04ec1e2eacb170/assets/cards/card-butterfly.svg" alt="MCP" width="48%">
  </a>
  <a href="https://hyperweave.app/docs/cli">
    <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/f36c8969d15d76da4400ebcfaa04ec1e2eacb170/assets/cards/card-sunflower.svg" alt="CLI" width="48%">
  </a>
  <br/>
  <a href="https://hyperweave.app/docs/api">
    <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/f36c8969d15d76da4400ebcfaa04ec1e2eacb170/assets/cards/card-waves.svg" alt="HTTP API" width="48%">
  </a>
  <a href="https://hyperweave.app/docs/python">
    <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/f36c8969d15d76da4400ebcfaa04ec1e2eacb170/assets/cards/card-python.svg" alt="Python SDK" width="48%">
  </a>
</p>

### MCP

```json
{
  "mcpServers": {
    "hyperweave": {
      "command": "hyperweave",
      "args": ["mcp"]
    }
  }
}
```

```
hw_compose(type="badge", title="build", value="passing", genome="brutalist-emerald")
hw_live(provider="github", identifier="anthropics/claude-code", metric="stars")
hw_kit(type="readme", genome="brutalist-emerald", badges="build:passing")
hw_discover(what="all")
```

### CLI

```bash
# Badge
hyperweave compose badge "build" "passing" --genome brutalist-emerald

# Strip with metrics
hyperweave compose strip "readme-ai" "STARS:2.9k,FORKS:278" -g brutalist-emerald

# Banner with kinetic motion
hyperweave compose banner "HYPERWEAVE" -g brutalist-emerald -m cascade

# Artifact kit
hyperweave kit readme -g brutalist-emerald --badges "build:passing,version:v0.2.0" --social "github,discord"

# Profile card (live GitHub data)
hyperweave compose stats eli64s -g chrome-horizon -o stats.svg

# Star history chart
hyperweave compose chart stars eli64s/readme-ai -g brutalist-emerald -o chart.svg

# Timeline / roadmap from JSON items
hyperweave compose timeline --data roadmap.json -g chrome-horizon -o timeline.svg

# Custom genome from a local JSON file (validated against the profile contract)
hyperweave compose badge "DEPLOY" "live" --genome-file ./my-genome.json
hyperweave validate-genome ./my-genome.json
```

### HTTP API

```bash
# URL grammar: /v1/{type}/{title}/{value}/{genome}.{motion}
curl https://hyperweave.app/v1/strip/readme-ai/brutalist-emerald.static?value=STARS:2.9k,FORKS:278

# Live data binding
curl https://hyperweave.app/v1/live/github/anthropics/claude-code/stars/chrome-horizon

# POST compose
curl -X POST https://hyperweave.app/v1/compose \
  -H "Content-Type: application/json" \
  -d '{"type":"banner","title":"HYPERWEAVE","genome":"brutalist-emerald","motion":"drop"}'

# Local server
hyperweave serve --port 8000
```

---

## Session Telemetry

HyperWeave parses Claude Code transcripts into visual receipts &mdash; cost, tokens, tool distribution, cognitive phases. The artifact isn't a visualization of data. It *is* the record.

```bash
# Manual
hyperweave session receipt .claude/session.jsonl -o receipt.svg

# Autonomous — install once, every session gets a receipt
hyperweave install-hook
```

After `install-hook`, every Claude Code session automatically drops a receipt SVG into `.hyperweave/receipts/`. No config, no server, no manual step.

<p align="center">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/main/assets/examples/telemetry/receipt.svg" alt="session receipt" width="800"/>
</p>
<p align="center">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/main/assets/examples/telemetry/rhythm_strip.svg" alt="rhythm strip" width="800"/>
</p>
<!--
<p align="center">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/f36c8969d15d76da4400ebcfaa04ec1e2eacb170/assets/examples/telemetry/master_card.svg" alt="master card" width="800"/>
</p>
-->

---

## How It Works

Every artifact is the output of a single composition formula:

```
ARTIFACT = FRAME × PROFILE × GENOME × SLOTS × MOTION × ENVIRONMENT
```

Python builds context dicts. Jinja2 builds SVG. YAML defines config. Three layers, no mixing. Zero f-string SVG in Python.

```
ComposeSpec → engine.py → assembler.py (CSS) → lanes.py (validate) → templates.py (Jinja2) → SVG
```

Every artifact ships with:

- **Semantic metadata** &mdash; provenance, reasoning, spatial trace, aesthetic DNA. Machine-readable context so the next agent in the chain knows what it's looking at and why.
- **CSS state machines** &mdash; `data-hw-status`, `data-hw-state`, `data-hw-regime` drive visual transitions through the Custom Property Bridge. No JavaScript.
- **Pure CSS/SMIL animation** &mdash; all motion uses compositor-safe properties (`transform`, `opacity`, `filter`). No script tags. Works inside GitHub's Camo proxy, email clients, Notion embeds &mdash; anywhere SVGs render.
- **Accessibility** &mdash; WCAG AA, `prefers-reduced-motion`, `prefers-color-scheme`, `forced-colors`, ARIA markup. Structural, not decorative.

| Dimension | Count |
|---|---|
| Frame types | 15 (badge, strip, banner, icon, divider, marquee-h/v/counter, receipt, rhythm-strip, master-card, catalog, stats, chart, timeline) |
| Genomes | 2 (brutalist-emerald, chrome-horizon) |
| Motion configs | 16 (1 static + 5 border SMIL + 10 kinetic CSS) |
| Glyphs | 97 (91 Simple Icons + 6 geometric) |
| Divider variants | 5 (block, current, takeoff, void, zeropoint) |
| Metadata tiers | 5 (Tier 0 silent &rarr; Tier 4 reasoning) |
| Paradigms | 3 per frame (default, brutalist, chrome) — per-frame dispatch from genome |
| Bundled fonts | 2 (JetBrains Mono, Orbitron, base64-embedded) |

Stack: Pydantic, FastAPI, FastMCP v3, Jinja2, Typer.

---

## Roadmap

<p>
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/f36c8969d15d76da4400ebcfaa04ec1e2eacb170/assets/timelines/hyperweave-roadmap.svg" alt="roadmap" width="100%"/>
</p>

---

## Contributing

HyperWeave is early. If you're interested in building genomes, extending frame types, or just seeing what this looks like in your own README &mdash; [join the Discord](https://discord.gg/wVmcAZPQZ8).

---

<p align="center">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/f36c8969d15d76da4400ebcfaa04ec1e2eacb170/assets/footers/inneraura-footer-liquid.svg" alt="InnerAura Labs" width="100%"/>
</p>

<p align="center">
  <a href="https://discord.gg/wVmcAZPQZ8">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/f36c8969d15d76da4400ebcfaa04ec1e2eacb170/assets/icons/cobalt-sapphire-discord.svg" width="48" alt="Discord"/>
  </a>
  &nbsp;
  <a href="https://www.instagram.com/hyperweave.ai/">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/f36c8969d15d76da4400ebcfaa04ec1e2eacb170/assets/icons/cobalt-sapphire-instagram.svg" width="48" alt="Instagram"/>
  </a>
  &nbsp;
  <a href="https://www.linkedin.com/company/inneraura">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/f36c8969d15d76da4400ebcfaa04ec1e2eacb170/assets/icons/cobalt-sapphire-linkedin.svg" width="48" alt="LinkedIn"/>
  </a>
  &nbsp;
  <a href="https://www.tiktok.com/@hyperweave.ai">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/f36c8969d15d76da4400ebcfaa04ec1e2eacb170/assets/icons/cobalt-sapphire-tiktok.svg" width="48" alt="TikTok"/>
  </a>
  &nbsp;
  <a href="https://x.com/InnerAuraLabs">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/f36c8969d15d76da4400ebcfaa04ec1e2eacb170/assets/icons/cobalt-sapphire-x.svg" width="48" alt="X"/>
  </a>
  &nbsp;
  <a href="https://www.youtube.com/@InnerAuraLabs">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/f36c8969d15d76da4400ebcfaa04ec1e2eacb170/assets/icons/cobalt-sapphire-youtube.svg" width="48" alt="YouTube"/>
  </a>
</p>

<div align="center">

[![][return-top]](#top)

</div>

<!-- REFERENCE LINKS -->
[inneraura.ai]: https://inneraura.ai/
[discord]: https://discord.gg/wVmcAZPQZ8
[docs]: https://hyperweave.readthedocs.io/
[github]: https://github.com/InnerAura/hyperweave
[instagram]: https://www.instagram.com/hyperweave.ai/
[linkedin]: https://www.linkedin.com/company/inneraura
[tiktok]: https://www.tiktok.com/@hyperweave.ai
[x]: https://x.com/InnerAuraLabs
[youtube]: https://www.youtube.com/@InnerAuraLabs

[return-top]: https://raw.githubusercontent.com/InnerAura/hyperweave/f36c8969d15d76da4400ebcfaa04ec1e2eacb170/assets/buttons/button-liquid.svg