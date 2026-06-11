<div id="top">

<p align="center">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/main/assets/banners/hyperweave-banner-chirp.svg" alt="HyperWeave" width="100%"/>
</p>

<p align="center">
  <strong>Portable visual output layer for agents.</strong><br/>
  One API call, one SVG. No JavaScript. Works everywhere.
</p>

<!--
<p align="center">
  <img src="https://hyperweave.app/v1/badge/STARS/chrome.static?data=gh:InnerAura/hyperweave.stars" alt="stars"/>
  <img src="https://hyperweave.app/v1/badge/FORKS/chrome.static?data=gh:InnerAura/hyperweave.forks" alt="forks"/>
  <img src="https://hyperweave.app/v1/badge/VERSION/chrome.static?data=pypi:hyperweave.version" alt="version"/>
  <img src="https://hyperweave.app/v1/badge/LICENSE/chrome.static?data=gh:InnerAura/hyperweave.license" alt="license"/>
  <img src="https://hyperweave.app/v1/badge/PYTHON/chrome.static?data=pypi:hyperweave.python_requires" alt="python"/>
</p>
-->

<p align="center">
  <img src="https://hyperweave.app/v1/strip/hyperweave/chrome.static?data=gh:InnerAura/hyperweave.build,pypi:hyperweave.version,gh:InnerAura/hyperweave.license&glyph=hyperweave" alt="strip"/>
</p>

<!--
<p align="center">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/3d46165fff7cf46e6c3feab6f96cfe09a63b1655/assets/rapid-match-cuts/rapid-match-cut-stat-cards.svg" alt="rapid match cuts"/>
</p>
-->

<!--
AI agents need to explain what they did, what they found, and what changed — HyperWeave gives them a visual language that works anywhere.

---
HyperWeave lets agents compose portable visual artifacts that can live inside reports, detach into Slack/email/docs, and carry their source, state, and drilldown with them.

---

A brand agent for repos.
Generate a cohesive visual identity layer for README, profile, status, and releases — automatically.

A brand agent for repos. Generate a cohesive visual identity — README, profile, metrics, releases — from a single genome.
---

HyperWeave is the generative visual identity system for the agentic era. A user defines a genome — their aesthetic DNA — and HyperWeave renders coherent visual artifacts across any surface, for any context, from any data. Badges for repos. Cards for stats. Charts for data. Artifact sets for research papers. Release kits for product launches. Marketing assets for startups. Static when static. Live when live. Generated when generative. Their brand, as infrastructure, for everything their agents will ever need to render.

The list in the middle ("Badges for repos. Cards for stats. Charts for data...") reads long. It proves the surface area is broad but it also reads like a features list. Investors skim past enumeration. You could collapse it: "Every surface agents render on, from repos to research papers to product launches." The breadth lands harder when it's a claim than when it's a list.

HyperWeave is the brand agent for engineering teams. Define your identity once; every artifact your team ships carries it wherever their work appears.

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

Prompting Guide for AI Agents
-->

---

## The Problem

When an agent needs to produce something visual, it generates React, HTML, or pixels: a status card, a dashboard, a receipt of its work, locked in the environment that made it. Embed it in markdown or pass it to another agent and it breaks or loses context. There's no portable visual primitive for agents.

HyperWeave is that primitive. One API call returns a self-contained SVG with data binding, branding, and machine-readable metadata baked in. No JavaScript, no dependencies, no runtime. It renders in GitHub READMEs, Slack, Notion, docs, your site, email, VS Code, or terminal. Every surface that renders an `<img>` tag is a HyperWeave surface.

<p align="center">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/main/assets/tables/hw-format-comparison-matrix-v2.svg" alt="HyperWeave" width="100%"/>
</p>

---

## Agentic Artifacts

Every AI coding session produces a receipt: cost, tokens, tool distribution, session rhythm. One install, fully automatic.

```bash
hyperweave install-hook
```

<p align="center">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/main/assets/examples/telemetry/receipt_voltage_xlarge.svg" alt="session receipt — voltage livery showing 262M tokens, 562 calls, 52 stages, divergence flag" width="800"/>
</p>
<p align="center"><sub>262M tokens &middot; 562 calls &middot; 52 stages &middot; $175 &middot; voltage</sub></p>

<p align="center">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/main/assets/examples/telemetry/rhythm_strip_voltage_xlarge.svg" alt="session rhythm strip — same session data at 92px tall" width="800"/>
</p>
<p align="center"><sub>Rhythm strip &middot; the same session data at 92px tall</sub></p>

<p align="center">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/main/assets/examples/telemetry/receipt_claude-code_medium.svg" alt="session receipt — claude-code livery on warm paper substrate" width="800"/>
</p>
<p align="center"><sub>Same data, different livery &middot; claude-code</sub></p>

<p align="center">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/main/assets/examples/telemetry/receipt_codex_large.svg" alt="session receipt — codex agent transcript auto-detected from JSONL shape" width="800"/>
</p>
<p align="center"><sub>Codex transcripts auto-detect from the JSONL shape</sub></p>

The livery matches the agent that produced the session:

| Agent | Livery |
|-------|--------|
| Claude Code | `claude-code` |
| Codex | `codex` |
| &mdash; | `voltage` |
| &mdash; | `cream` |

Auto-detected from the session transcript. Pin a different default with `hyperweave install-hook --genome voltage`.

---

## Matrices - Generative Tables

A matrix is a table described in JSON and rendered as an SVG. Columns choose from eight cell kinds (text, check, dot, bar, pill, numeric heat, chip, glyph), which is enough to cover comparisons, registries, tiers, bar scales, plans, and benchmarks. The output embeds anywhere markdown renders.

<p align="center">
  <img src="https://hyperweave.app/v1/matrix/custom/primer.static?variant=porcelain&spec=eyJ0aXRsZSI6Ik9uZSBhcnRpZmFjdC4gTWFueSByZWFkZXJzLiIsInN1YnRpdGxlIjoiaG93IGVhY2ggY29uc3VtZXIgaW5nZXN0cyB0aGUgc2FtZSBTVkciLCJjb2x1bW5zIjpbeyJpZCI6InJlYWRlciIsImxhYmVsIjoiUkVBREVSIiwicm9sZSI6ImxhYmVsIn0seyJpZCI6Im1hcmsiLCJsYWJlbCI6IiIsImtpbmQiOiJnbHlwaCIsImdseXBoX3RpbnQiOiJmdWxsIn0seyJpZCI6InBpeGVscyIsImxhYmVsIjoiUElYRUxTIiwia2luZCI6ImNoZWNrIn0seyJpZCI6Im1vdGlvbiIsImxhYmVsIjoiTU9USU9OIiwia2luZCI6InBpbGwifSx7ImlkIjoidmlhIiwibGFiZWwiOiJSRUFEUyBWSUEiLCJraW5kIjoiY2hpcCJ9XSwicm93cyI6W3sibGFiZWwiOiJHaXRIdWIgUkVBRE1FIiwiY2VsbHMiOlt7ImdseXBoIjoiZ2l0aHViIn0seyJzdGF0ZSI6ImZ1bGwifSx7InN0YXRlIjoib24ifSx7ImNoaXBzIjpbImNhbW8iLCJjc3MgYW5pbWF0aW9uIl19XX0seyJsYWJlbCI6IlZTIENvZGUgcHJldmlldyIsImNlbGxzIjpbeyJnbHlwaCI6InZzY29kZSJ9LHsic3RhdGUiOiJmdWxsIn0seyJzdGF0ZSI6Im9mZiJ9LHsiY2hpcHMiOlsibWFya2Rvd24gcHJldmlldyJdfV19LHsibGFiZWwiOiJTbGFjayB1bmZ1cmwiLCJjZWxscyI6W3siZ2x5cGgiOiJzbGFjayJ9LHsic3RhdGUiOiJwYXJ0aWFsIn0seyJzdGF0ZSI6Im9mZiJ9LHsiY2hpcHMiOlsiaW1hZ2UgcHJveHkiXX1dfSx7ImxhYmVsIjoiR21haWwgYm9keSIsImNlbGxzIjpbeyJnbHlwaCI6ImdtYWlsIn0seyJzdGF0ZSI6InBhcnRpYWwifSx7InN0YXRlIjoib2ZmIn0seyJjaGlwcyI6WyJpbWcgdGFnIl19XX0seyJsYWJlbCI6IkFJIGFnZW50IiwiY2VsbHMiOlt7ImdseXBoIjoiY2xhdWRlIn0seyJzdGF0ZSI6Im5vbmUifSx7InN0YXRlIjoib2ZmIn0seyJjaGlwcyI6WyJodzpwYXlsb2FkIiwiaHd6LzEiLCJtYXJrZG93biB0d2luIl19XX1dLCJub3RlcyI6InBpeGVscyBmb3IgaHVtYW5zIMK3IGh3OnBheWxvYWQgZm9yIGFnZW50cyJ9&v=3" alt="comparison matrix: how GitHub, VS Code, Slack, Gmail, and AI agents each ingest the same SVG" width="100%"/>
</p>

<p align="center"><sub>One frame, every table &middot; generated, not drawn</sub></p>

Inside that SVG, alongside the pixels — two tiers, two jobs:

**recreate & modify — the complete table IR**

```xml
<hw:payload schema="matrix/1" media-type="application/json">
{
  "title": "One artifact. Many readers.",
  "subtitle": "how each consumer ingests the same SVG",
  "columns": [
    { "id": "reader", "label": "READER",    "kind": "text",  "align": "left",   "role": "label" },
    { "id": "mark",   "label": "",          "kind": "glyph", "align": "center", "glyph_tint": "full" },
    { "id": "pixels", "label": "PIXELS",    "kind": "check", "align": "center" },
    { "id": "motion", "label": "MOTION",    "kind": "pill",  "align": "center" },
    { "id": "via",    "label": "READS VIA", "kind": "chip",  "align": "left" }
  ],
  "rows": [
    { "label": "GitHub README", "cells": [{ "glyph": "github" }, { "state": "full" }, { "state": "on" }, { "chips": ["camo", "css animation"] }] }
    <!-- … 4 more rows · lossless -->
  ]
}
</hw:payload>
```

**read at a budget — ≈200 tokens to know what an artifact is**

```xml
<hw:envelope format="hwz/1" media-type="application/json">
{
  "v": "hwz/1",
  "id": "sha256:7021648adf306e15cc4b954d7113aaf2f8a53717e69cf3421576ce3c007ad1e6",
  "k": "matrix",
  "title": "One artifact. Many readers.",
  "intent": "structured comparison: One artifact. Many readers.",
  "state": "active",
  "data": {
    "subvariant": "registry",
    "cols": ["mark", "pixels", "motion", "via"],
    "rows": {
      "GitHub README": "github",
      "VS Code preview": "vscode",
      "Slack unfurl": "slack",
      "Gmail body": "gmail",
      "AI agent": "claude"
    },
    "rows_total": 5
  },
  "frames": [{ "t": "matrix", "l": "One artifact. Many readers." }],
  "prov": { "by": "hyperweave", "ver": "0.4.0a2", "genome": "primer.porcelain", "ts": "2026-06-11T15:51:03.185542+00:00" }
}
</hw:envelope>
```

The envelope is the lossy digest; only the payload round-trips.

- **The round-trip:** extract `hw:payload`, edit the JSON, `POST /v1/compose` with it as `matrix`: byte-identical re-render. The envelope's `id` is the sha256 of the payload, so an agent verifies "this artifact really is this data" before trusting either.
- **The look is a pointer, not a copy:** `prov.genome: "primer.porcelain"` names the aesthetics; payload + that one string is the entire recreation recipe.
- **Markdown twin:** every matrix has a GFM projection. `--markdown-out` on the CLI, `respond:"json"` over HTTP, `render_target="markdown"` over MCP.

```bash
# Connectors preset
https://hyperweave.app/v1/matrix/connectors/primer.static?variant=porcelain

# Any table, one URL: base64url MatrixSpec JSON (8 KB cap)
https://hyperweave.app/v1/matrix/custom/primer.static?spec=<base64url>

# CLI, with the markdown twin alongside
hyperweave compose matrix --spec-file table.json -g primer --variant porcelain --markdown-out table.md
```

---

## Genomes - Aesthetic DNA

A genome is a portable, machine-readable aesthetic specification. It encodes the complete visual identity (chromatic system, surface material, motion vocabulary, geometric form language) as a set of CSS custom properties that any agent can consume and apply consistently across every artifact type.

Four built-in genomes ship today. Custom genome generation via AI skill files coming soon.

<!--
Why genome and not theme? Because brand isn't a design problem, it's an infrastructure problem. When an agent says "build me a status page," it has zero memory of visual identity. A genome solves that: define once, express everywhere, from a 90px badge to a 900px star history chart. The same genome produces different artifacts that feel like they came from the same hand.
-->

<p align="center">
  <a href="#brutalist"><kbd>brutalist</kbd></a>
  &middot;
  <a href="#automata"><kbd>automata</kbd></a>
  &middot;
  <a href="#chrome"><kbd>chrome</kbd></a>
  &middot;
  <a href="#primer"><kbd>primer</kbd></a>
</p>

<h3 id="brutalist">brutalist</h3>

<p align="center">
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=celadon" alt="PYPI — celadon variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=alloy" alt="PYPI — alloy variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=carbon" alt="PYPI — carbon variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=pigment" alt="PYPI — pigment variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=umber" alt="PYPI — umber variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=ember" alt="PYPI — ember variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=temper" alt="PYPI — temper variant"/>
  <br/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=onyx" alt="PYPI — onyx variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=primer" alt="PYPI — primer variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=depth" alt="PYPI — depth variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=pulse" alt="PYPI — pulse variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=archive" alt="PYPI — archive variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=signal" alt="PYPI — signal variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=afterimage" alt="PYPI — afterimage variant"/>
</p>

<p align="center">
  <sub>22 variants &middot; 8 dark: <code>celadon</code> &middot; <code>alloy</code> &middot; <code>carbon</code> &middot; <code>pigment</code> &middot; <code>umber</code> &middot; <code>ember</code> &middot; <code>temper</code> &middot; <code>onyx</code><br/>14 light (6 shown): <code>primer</code> &middot; <code>depth</code> &middot; <code>pulse</code> &middot; <code>archive</code> &middot; <code>signal</code> &middot; <code>afterimage</code></sub>
</p>

<table>
<tr>
<th align="left" width="160">Signals<br/><sub>state machine</sub></th>
<td>
  <img src="https://hyperweave.app/v1/badge/BUILD/passing/brutalist.static?state=passing&variant=celadon" alt="passing"/>
  <img src="https://hyperweave.app/v1/badge/BUILD/warning/brutalist.static?state=warning&variant=celadon" alt="warning"/>
  <img src="https://hyperweave.app/v1/badge/BUILD/critical/brutalist.static?state=critical&variant=celadon" alt="critical"/>
  <br/>
  <ul>
<li><sub><code>/v1/badge/{title}/{value}/{genome}.static?state={state}&variant={celadon|carbon|alloy|temper|pigment|ember|umber|onyx|archive|signal|pulse|depth|afterimage|primer}</code></sub></li>
<li><sub><code>hyperweave.app/v1/badge/BUILD/passing/brutalist.static?state=passing&variant=celadon</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Dashboard<br/><sub>strip</sub></th>
<td>
  <img src="https://hyperweave.app/v1/strip/hyperweave/brutalist.static?data=gh:InnerAura/hyperweave.stars,pypi:hyperweave.version,gh:InnerAura/hyperweave.build&subtitle=InnerAura/hyperweave&glyph=github&variant=celadon" alt="strip"/>
  <br/>
  <ul>
<li><sub><code>/v1/strip/{title}/{genome}.static?data={tokens}&subtitle={text}&glyph={glyph}&variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/strip/hyperweave/brutalist.static?data=gh:InnerAura/hyperweave.stars,pypi:hyperweave.version,gh:InnerAura/hyperweave.build&subtitle=InnerAura/hyperweave&glyph=github&variant=celadon</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Profile<br/><sub>stats card</sub></th>
<td>
  <img src="https://hyperweave.app/v1/stats/eli64s/brutalist.static?variant=pulse" alt="stats — pulse (light)"/>
  <br/>
  <img src="https://hyperweave.app/v1/stats/eli64s/brutalist.static?variant=celadon" alt="stats — celadon (dark)"/>
  <br/>
  <ul>
<li><sub><code>/v1/stats/{username}/{genome}.static?variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/stats/eli64s/brutalist.static?variant=pulse</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Star Chart<br/><sub>star history</sub></th>
<td>
  <img src="https://hyperweave.app/v1/chart/stars/eli64s/readme-ai/brutalist.static?variant=celadon" alt="star chart"/>
  <br/>
  <ul>
<li><sub><code>/v1/chart/stars/{owner}/{repo}/{genome}.static?variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/chart/stars/eli64s/readme-ai/brutalist.static?variant=celadon</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Marquee<br/><sub>horizontal ticker</sub></th>
<td>
  <img src="https://hyperweave.app/v1/marquee/readme-ai/brutalist.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,gh:eli64s/readme-ai.contributors,gh:eli64s/readme-ai.watchers,pypi:readmeai.downloads,gh:eli64s/readme-ai.last_push,gh:eli64s/readme-ai.pull_requests,gh:eli64s/readme-ai.issues,gh:eli64s/readme-ai.build,pypi:readmeai.version,gh:eli64s/readme-ai.language&variant=celadon" alt="marquee"/>
  <br/>
  <ul>
<li><sub><code>/v1/marquee/{title}/{genome}.static?data={tokens}&variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/marquee/readme-ai/brutalist.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,gh:eli64s/readme-ai.contributors,gh:eli64s/readme-ai.watchers,pypi:readmeai.downloads,gh:eli64s/readme-ai.last_push,gh:eli64s/readme-ai.pull_requests,gh:eli64s/readme-ai.issues,gh:eli64s/readme-ai.build,pypi:readmeai.version,gh:eli64s/readme-ai.language&variant=celadon</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Icons<br/><sub>circle + square</sub></th>
<td>
  <img src="https://hyperweave.app/v1/icon/spotify/brutalist.static?shape=circle&variant=celadon" alt="spotify — celadon" width="56"/>
  <img src="https://hyperweave.app/v1/icon/docker/brutalist.static?shape=circle&variant=alloy" alt="docker — alloy" width="56"/>
  <img src="https://hyperweave.app/v1/icon/github/brutalist.static?shape=circle&variant=carbon" alt="github — carbon" width="56"/>
  <img src="https://hyperweave.app/v1/icon/discord/brutalist.static?shape=circle&variant=pigment" alt="discord — pigment" width="56"/>
  <img src="https://hyperweave.app/v1/icon/rust/brutalist.static?shape=square&variant=umber" alt="rust — umber" width="56"/>
  <img src="https://hyperweave.app/v1/icon/anthropic/brutalist.static?shape=square&variant=ember" alt="anthropic — ember" width="56"/>
  <img src="https://hyperweave.app/v1/icon/codex/brutalist.static?shape=square&variant=temper" alt="codex — temper" width="56"/>
  <img src="https://hyperweave.app/v1/icon/hyperweave/brutalist.static?shape=square&variant=onyx" alt="hyperweave — onyx" width="56"/>
  <br/>
  <ul>
<li><sub><code>/v1/icon/{glyph}/{genome}.static?shape={circle|square}&variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/icon/github/brutalist.static?shape=circle&variant=celadon</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Divider<br/><sub>seam &middot; sigil</sub></th>
<td>
  <img src="https://hyperweave.app/v1/divider/seam/brutalist.static?variant=celadon" alt="brutalist seam divider (dark)"/>
  <br/>
  <img src="https://hyperweave.app/v1/divider/sigil/brutalist.static?variant=pulse" alt="brutalist sigil divider (light)"/>
  <br/>
  <ul>
<li><sub><code>/v1/divider/{seam|sigil}/{genome}.static?variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/divider/sigil/brutalist.static?variant=pulse</code></sub></li>
</ul>
</td>
</tr>
</table>
<h3 id="automata">automata</h3>

<p align="center">
  <img src="https://hyperweave.app/v1/badge/PYPI/automata.static?data=pypi:hyperweave.version&glyph=python&variant=crimson&size=compact" alt="PYPI — crimson variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/automata.static?data=pypi:hyperweave.version&glyph=python&variant=copper&size=compact" alt="PYPI — copper variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/automata.static?data=pypi:hyperweave.version&glyph=python&variant=bone&size=compact" alt="PYPI — bone variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/automata.static?data=pypi:hyperweave.version&glyph=python&variant=solar&size=compact" alt="PYPI — solar variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/automata.static?data=pypi:hyperweave.version&glyph=python&variant=amber&size=compact" alt="PYPI — amber variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/automata.static?data=pypi:hyperweave.version&glyph=python&variant=sulfur&size=compact" alt="PYPI — sulfur variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/automata.static?data=pypi:hyperweave.version&glyph=python&variant=toxic&size=compact" alt="PYPI — toxic variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/automata.static?data=pypi:hyperweave.version&glyph=python&variant=jade&size=compact" alt="PYPI — jade variant"/>
  <br/>
  <img src="https://hyperweave.app/v1/badge/PYPI/automata.static?data=pypi:hyperweave.version&glyph=python&variant=abyssal&size=compact" alt="PYPI — abyssal variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/automata.static?data=pypi:hyperweave.version&glyph=python&variant=teal&size=compact" alt="PYPI — teal variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/automata.static?data=pypi:hyperweave.version&glyph=python&variant=steel&size=compact" alt="PYPI — steel variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/automata.static?data=pypi:hyperweave.version&glyph=python&variant=cobalt&size=compact" alt="PYPI — cobalt variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/automata.static?data=pypi:hyperweave.version&glyph=python&variant=indigo&size=compact" alt="PYPI — indigo variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/automata.static?data=pypi:hyperweave.version&glyph=python&variant=violet&size=compact" alt="PYPI — violet variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/automata.static?data=pypi:hyperweave.version&glyph=python&variant=magenta&size=compact" alt="PYPI — magenta variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/automata.static?data=pypi:hyperweave.version&glyph=python&variant=burgundy&size=compact" alt="PYPI — burgundy variant"/>
</p>

<p align="center">
  <sub>16 tones &middot; <code>crimson</code> &middot; <code>copper</code> &middot; <code>bone</code> &middot; <code>solar</code> &middot; <code>amber</code> &middot; <code>sulfur</code> &middot; <code>toxic</code> &middot; <code>jade</code><br/><code>abyssal</code> &middot; <code>teal</code> &middot; <code>steel</code> &middot; <code>cobalt</code> &middot; <code>indigo</code> &middot; <code>violet</code> &middot; <code>magenta</code> &middot; <code>burgundy</code><br/>pair any two via <code>?variant=primary&pair=secondary</code></sub>
</p>

<table>
<tr>
<th align="left" width="160">Signals<br/><sub>state machine</sub></th>
<td>
  <img src="https://hyperweave.app/v1/badge/BUILD/passing/automata.static?state=passing&variant=bone" alt="passing"/>
  <img src="https://hyperweave.app/v1/badge/BUILD/warning/automata.static?state=warning&variant=bone" alt="warning"/>
  <img src="https://hyperweave.app/v1/badge/BUILD/critical/automata.static?state=critical&variant=bone" alt="critical"/>
  <br/>
  <ul>
<li><sub><code>/v1/badge/{title}/{value}/{genome}.static?state={state}</code></sub></li>
<li><sub><code>hyperweave.app/v1/badge/BUILD/passing/automata.static?state=passing&variant=bone</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Dashboard<br/><sub>strip</sub></th>
<td>
  <img src="https://hyperweave.app/v1/strip/readme-ai/automata.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,pypi:readmeai.version&subtitle=eli64s/readme-ai&variant=bone&glyph=github" alt="strip"/>
  <br/>
  <ul>
<li><sub><code>/v1/strip/{title}/automata.static?data={tokens}&variant={tone}&pair={tone}&subtitle={text}&glyph={glyph}</code></sub></li>
<li><sub><code>hyperweave.app/v1/strip/readme-ai/automata.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,pypi:readmeai.version&subtitle=eli64s/readme-ai&variant=bone&pair=steel&glyph=github</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Profile<br/><sub>stats card</sub></th>
<td>
  <img src="https://hyperweave.app/v1/stats/eli64s/automata.static?variant=bone&v=2" alt="stats"/>
  <br/>
  <ul>
<li><sub><code>/v1/stats/{username}/{genome}.static?variant={tone}</code></sub></li>
<li><sub><code>hyperweave.app/v1/stats/eli64s/automata.static?variant=bone</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Star Chart<br/><sub>star history</sub></th>
<td>
  <img src="https://hyperweave.app/v1/chart/stars/eli64s/readme-ai/automata.static?variant=bone&v=2" alt="star chart"/>
  <br/>
  <ul>
<li><sub><code>/v1/chart/stars/{owner}/{repo}/{genome}.static?variant={tone}</code></sub></li>
<li><sub><code>hyperweave.app/v1/chart/stars/eli64s/readme-ai/automata.static?variant=bone</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Marquee<br/><sub>horizontal ticker</sub></th>
<td>
  <img src="https://hyperweave.app/v1/marquee/readme-ai/automata.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,gh:eli64s/readme-ai.contributors,gh:eli64s/readme-ai.watchers,pypi:readmeai.downloads,gh:eli64s/readme-ai.last_push,gh:eli64s/readme-ai.pull_requests,gh:eli64s/readme-ai.issues,gh:eli64s/readme-ai.build,pypi:readmeai.version,gh:eli64s/readme-ai.language&variant=bone" alt="marquee"/>
  <br/>
  <ul>
<li><sub><code>/v1/marquee/{title}/automata.static?data={tokens}&variant={tone}</code></sub></li>
<li><sub><code>hyperweave.app/v1/marquee/readme-ai/automata.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,gh:eli64s/readme-ai.contributors,gh:eli64s/readme-ai.watchers,pypi:readmeai.downloads,gh:eli64s/readme-ai.last_push,gh:eli64s/readme-ai.pull_requests,gh:eli64s/readme-ai.issues,gh:eli64s/readme-ai.build,pypi:readmeai.version,gh:eli64s/readme-ai.language&variant=bone</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Icons<br/><sub>square</sub></th>
<td>
  <img src="https://hyperweave.app/v1/icon/docker/automata.static?shape=square&variant=cobalt" alt="docker cobalt" width="56"/>
  <img src="https://hyperweave.app/v1/icon/discord/automata.static?shape=square&variant=indigo" alt="discord indigo" width="56"/>
  <img src="https://hyperweave.app/v1/icon/github/automata.static?shape=square&variant=bone" alt="github bone" width="56"/>
  <img src="https://hyperweave.app/v1/icon/huggingface/automata.static?shape=square&variant=sulfur" alt="huggingface sulfur" width="56"/>
  <img src="https://hyperweave.app/v1/icon/anthropic/automata.static?shape=square&variant=solar" alt="anthropic solar" width="56"/>
  <img src="https://hyperweave.app/v1/icon/youtube/automata.static?shape=square&variant=crimson" alt="youtube crimson" width="56"/>
  <img src="https://hyperweave.app/v1/icon/spotify/automata.static?shape=square&variant=jade" alt="spotify jade" width="56"/>
  <br/>
  <ul>
<li><sub><code>/v1/icon/{glyph}/automata.static?shape=square&variant={tone}</code></sub></li>
<li><sub><code>hyperweave.app/v1/icon/docker/automata.static?shape=square&variant=cobalt</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Divider<br/><sub>dissolve</sub></th>
<td>
  <img src="https://hyperweave.app/v1/divider/dissolve/automata.static?variant=bone" alt="automata dissolve divider"/>
  <br/>
  <ul>
<li><sub><code>/v1/divider/dissolve/{genome}.static?variant={tone}&pair={tone}</code></sub></li>
<li><sub><code>hyperweave.app/v1/divider/dissolve/automata.static?variant=bone&pair=steel</code></sub></li>
</ul>
</td>
</tr>
</table>
<h3 id="chrome">chrome</h3>

<p align="center">
  <img src="https://hyperweave.app/v1/badge/PYPI/chrome.static?data=pypi:hyperweave.version&glyph=python&variant=horizon" alt="PYPI — horizon variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/chrome.static?data=pypi:hyperweave.version&glyph=python&variant=lightning" alt="PYPI — lightning variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/chrome.static?data=pypi:hyperweave.version&glyph=python&variant=abyssal" alt="PYPI — abyssal variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/chrome.static?data=pypi:hyperweave.version&glyph=python&variant=moth" alt="PYPI — moth variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/chrome.static?data=pypi:hyperweave.version&glyph=python&variant=graphite" alt="PYPI — graphite variant"/>
</p>

<p align="center">
  <sub>5 variants: <code>horizon</code> &middot; <code>lightning</code> &middot; <code>abyssal</code> &middot; <code>moth</code> &middot; <code>graphite</code></sub>
</p>

<table>
<tr>
<th align="left" width="160">Signals<br/><sub>state machine</sub></th>
<td>
  <img src="https://hyperweave.app/v1/badge/BUILD/passing/chrome.static?state=passing&variant=horizon" alt="passing"/>
  <img src="https://hyperweave.app/v1/badge/BUILD/warning/chrome.static?state=warning&variant=horizon" alt="warning"/>
  <img src="https://hyperweave.app/v1/badge/BUILD/critical/chrome.static?state=critical&variant=horizon" alt="critical"/>
  <br/>
  <ul>
<li><sub><code>/v1/badge/{title}/{value}/{genome}.static?state={state}&variant={horizon|lightning|abyssal|moth|graphite}</code></sub></li>
<li><sub><code>hyperweave.app/v1/badge/BUILD/passing/chrome.static?state=passing&variant=horizon</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Dashboard<br/><sub>strip</sub></th>
<td>
  <img src="https://hyperweave.app/v1/strip/readme-ai/chrome.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,pypi:readmeai.version&subtitle=eli64s/readme-ai&glyph=github&variant=horizon" alt="strip"/>
  <br/>
  <ul>
<li><sub><code>/v1/strip/{title}/{genome}.static?data={tokens}&subtitle={text}&glyph={glyph}&variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/strip/readme-ai/chrome.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,pypi:readmeai.version&subtitle=eli64s/readme-ai&glyph=github&variant=horizon</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Profile<br/><sub>stats card</sub></th>
<td>
  <img src="https://hyperweave.app/v1/stats/eli64s/chrome.static?variant=horizon" alt="stats" />
  <br/>
  <ul>
<li><sub><code>/v1/stats/{username}/{genome}.static?variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/stats/eli64s/chrome.static?variant=horizon</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Star Chart<br/><sub>star history</sub></th>
<td>
  <img src="https://hyperweave.app/v1/chart/stars/eli64s/readme-ai/chrome.static?variant=horizon" alt="star chart" />
  <br/>
  <ul>
<li><sub><code>/v1/chart/stars/{owner}/{repo}/{genome}.static?variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/chart/stars/eli64s/readme-ai/chrome.static?variant=horizon</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Marquee<br/><sub>horizontal ticker</sub></th>
<td>
  <img src="https://hyperweave.app/v1/marquee/readme-ai/chrome.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,gh:eli64s/readme-ai.contributors,gh:eli64s/readme-ai.watchers,pypi:readmeai.downloads,gh:eli64s/readme-ai.last_push,gh:eli64s/readme-ai.pull_requests,gh:eli64s/readme-ai.issues,gh:eli64s/readme-ai.build,pypi:readmeai.version,gh:eli64s/readme-ai.language&variant=horizon" alt="marquee"/>
  <br/>
  <ul>
<li><sub><code>/v1/marquee/{title}/{genome}.static?data={tokens}&variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/marquee/readme-ai/chrome.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,gh:eli64s/readme-ai.contributors,gh:eli64s/readme-ai.watchers,pypi:readmeai.downloads,gh:eli64s/readme-ai.last_push,gh:eli64s/readme-ai.pull_requests,gh:eli64s/readme-ai.issues,gh:eli64s/readme-ai.build,pypi:readmeai.version,gh:eli64s/readme-ai.language&variant=horizon</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Icons<br/><sub>circle + square</sub></th>
<td>
  <img src="https://hyperweave.app/v1/icon/github/chrome.static?shape=circle&variant=horizon" alt="github — horizon" width="56"/>
  <img src="https://hyperweave.app/v1/icon/notion/chrome.static?shape=circle&variant=graphite" alt="notion — graphite" width="56"/>
  <img src="https://hyperweave.app/v1/icon/rust/chrome.static?shape=square&variant=moth" alt="rust — moth" width="56"/>
  <img src="https://hyperweave.app/v1/icon/docker/chrome.static?shape=square&variant=lightning" alt="docker — lightning" width="56"/>
  <img src="https://hyperweave.app/v1/icon/spotify/chrome.static?shape=square&variant=abyssal" alt="spotify — abyssal" width="56"/>
  <br/>
  <ul>
<li><sub><code>/v1/icon/{glyph}/{genome}.static?shape={circle|square}&variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/icon/youtube/chrome.static?shape=circle&variant=horizon</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Divider<br/><sub>band</sub></th>
<td>
  <img src="https://hyperweave.app/v1/divider/band/chrome.static?variant=horizon" alt="chrome band divider"/>
  <br/>
  <ul>
<li><sub><code>/v1/divider/band/{genome}.static?variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/divider/band/chrome.static?variant=horizon</code></sub></li>
</ul>
</td>
</tr>
</table>
<h3 id="primer">primer</h3>

<p align="center">
  <img src="https://hyperweave.app/v1/badge/PYPI/primer.static?data=pypi:hyperweave.version&glyph=python&variant=porcelain" alt="PYPI — porcelain variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/primer.static?data=pypi:hyperweave.version&glyph=python&variant=cream" alt="PYPI — cream variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/primer.static?data=pypi:hyperweave.version&glyph=python&variant=dusk" alt="PYPI — dusk variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/primer.static?data=pypi:hyperweave.version&glyph=python&variant=petrol" alt="PYPI — petrol variant"/>
  <br/>
  <img src="https://hyperweave.app/v1/badge/PYPI/primer.static?data=pypi:hyperweave.version&glyph=python&variant=noir" alt="PYPI — noir variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/primer.static?data=pypi:hyperweave.version&glyph=python&variant=carbon" alt="PYPI — carbon variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/primer.static?data=pypi:hyperweave.version&glyph=python&variant=space" alt="PYPI — space variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/primer.static?data=pypi:hyperweave.version&glyph=python&variant=anvil" alt="PYPI — anvil variant"/>
</p>

<p align="center">
  <sub>8 variants &middot; 4 light: <code>porcelain</code> &middot; <code>cream</code> &middot; <code>dusk</code> &middot; <code>petrol</code><br/>4 dark: <code>noir</code> &middot; <code>carbon</code> &middot; <code>space</code> &middot; <code>anvil</code></sub>
</p>

<table>
<tr>
<th align="left" width="160">Signals<br/><sub>animated state marks</sub></th>
<td>
  <img src="https://hyperweave.app/v1/badge/BUILD/passing/primer.static?state=passing&variant=porcelain" alt="passing"/>
  <img src="https://hyperweave.app/v1/badge/BUILD/building/primer.static?state=building&variant=porcelain" alt="building"/>
  <img src="https://hyperweave.app/v1/badge/BUILD/warning/primer.static?state=warning&variant=porcelain" alt="warning"/>
  <img src="https://hyperweave.app/v1/badge/BUILD/critical/primer.static?state=critical&variant=porcelain" alt="critical"/>
  <br/>
  <ul>
<li><sub>ping (passing) &middot; spinner (building) &middot; throb (warning) &middot; shake (critical). One mark system, shared with the strip.</sub></li>
<li><sub><code>/v1/badge/{title}/{value}/primer.static?state={state}&variant={porcelain|cream|dusk|petrol|noir|carbon|space|anvil}</code></sub></li>
<li><sub><code>hyperweave.app/v1/badge/BUILD/passing/primer.static?state=passing&variant=porcelain</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Dashboard<br/><sub>strip</sub></th>
<td>
  <img src="https://hyperweave.app/v1/strip/readme-ai/primer.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,pypi:readmeai.version&subtitle=eli64s/readme-ai&glyph=github&variant=porcelain" alt="strip"/>
  <br/>
  <ul>
<li><sub><code>/v1/strip/{title}/primer.static?data={tokens}&subtitle={text}&glyph={glyph}&variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/strip/readme-ai/primer.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,pypi:readmeai.version&subtitle=eli64s/readme-ai&glyph=github&variant=porcelain</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Profile<br/><sub>stats card</sub></th>
<td>
  <img src="https://hyperweave.app/v1/stats/eli64s/primer.static?variant=porcelain" alt="stats"/>
  <br/>
  <ul>
<li><sub><code>/v1/stats/{username}/primer.static?variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/stats/eli64s/primer.static?variant=porcelain</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Star Chart<br/><sub>star history</sub></th>
<td>
  <img src="https://hyperweave.app/v1/chart/stars/eli64s/readme-ai/primer.static?variant=porcelain" alt="star chart"/>
  <br/>
  <ul>
<li><sub><code>/v1/chart/stars/{owner}/{repo}/primer.static?variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/chart/stars/eli64s/readme-ai/primer.static?variant=porcelain</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Marquee<br/><sub>horizontal ticker</sub></th>
<td>
  <img src="https://hyperweave.app/v1/marquee/readme-ai/primer.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,gh:eli64s/readme-ai.contributors,pypi:readmeai.downloads,gh:eli64s/readme-ai.last_push,pypi:readmeai.version,gh:eli64s/readme-ai.language&variant=porcelain" alt="marquee"/>
  <br/>
  <ul>
<li><sub><code>/v1/marquee/{title}/primer.static?data={tokens}&variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/marquee/readme-ai/primer.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,gh:eli64s/readme-ai.contributors,pypi:readmeai.downloads,gh:eli64s/readme-ai.last_push,pypi:readmeai.version,gh:eli64s/readme-ai.language&variant=porcelain</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Icons<br/><sub>circle + square</sub></th>
<td>
  <img src="https://hyperweave.app/v1/icon/vercel/primer.static?shape=circle&variant=noir" alt="vercel — noir" width="56"/>
  <img src="https://hyperweave.app/v1/icon/cloudflare/primer.static?shape=circle&variant=carbon" alt="cloudflare — carbon" width="56"/>
  <img src="https://hyperweave.app/v1/icon/docker/primer.static?shape=circle&variant=space" alt="docker — space" width="56"/>
  <img src="https://hyperweave.app/v1/icon/github/primer.static?shape=circle&variant=anvil" alt="github — anvil" width="56"/>
  <img src="https://hyperweave.app/v1/icon/deepseek/primer.static?shape=square&variant=porcelain" alt="deepseek — porcelain" width="56"/>
  <img src="https://hyperweave.app/v1/icon/anthropic/primer.static?shape=square&variant=cream" alt="anthropic — cream" width="56"/>
  <img src="https://hyperweave.app/v1/icon/ollama/primer.static?shape=square&variant=dusk" alt="ollama — dusk" width="56"/>
  <img src="https://hyperweave.app/v1/icon/nousresearch/primer.static?shape=square&variant=petrol" alt="nousresearch — petrol" width="56"/>
  <br/>
  <ul>
<li><sub><code>/v1/icon/{glyph}/primer.static?shape={circle|square}&variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/icon/github/primer.static?shape=circle&variant=noir</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Divider<br/><sub>aura</sub></th>
<td>
  <img src="https://hyperweave.app/v1/divider/aura/primer.static?variant=porcelain" alt="primer aura divider"/>
  <br/>
  <ul>
<li><sub><code>/v1/divider/aura/primer.static?variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/divider/aura/primer.static?variant=porcelain</code></sub></li>
</ul>
</td>
</tr>
</table>

<br />

| | brutalist | automata | chrome | primer |
|---|---|---|---|---|
| Aesthetic | Raw material | Cellular | Metallic | Minimal |
| Variants | 22 (8 dark, 14 light) | 16 tones, any two pair | 5 named | 8 (4 dark, 4 light) |
| Motion | Animated border SMIL | Animated cell grid | Animated border SMIL | Animated state marks |
| Divider | `seam` &middot; `sigil` | `dissolve` | `band` | `aura` |

<br />

<h3 id="dividers"><code>/a/inneraura/dividers/</code></h3>

<table>
<tr>
<th align="left" width="160">block<br/><sub>De Stijl composition</sub></th>
<td>
  <img src="https://hyperweave.app/a/inneraura/dividers/block" alt="block divider"/>
  <br/>
  <ul>
<li><sub><code>/a/inneraura/dividers/{slug}</code></sub></li>
<li><sub><code>hyperweave.app/a/inneraura/dividers/block</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">current<br/><sub>animated rainbow bezier</sub></th>
<td>
  <img src="https://hyperweave.app/a/inneraura/dividers/current" alt="current divider"/>
  <br/>
  <ul>
<li><sub><code>/a/inneraura/dividers/{slug}</code></sub></li>
<li><sub><code>hyperweave.app/a/inneraura/dividers/current</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">takeoff<br/><sub>rocket trajectory + thrust</sub></th>
<td>
  <img src="https://hyperweave.app/a/inneraura/dividers/takeoff" alt="takeoff divider"/>
  <br/>
  <ul>
<li><sub><code>/a/inneraura/dividers/{slug}</code></sub></li>
<li><sub><code>hyperweave.app/a/inneraura/dividers/takeoff</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">void<br/><sub>spectral bloom + hover state</sub></th>
<td>
  <img src="https://hyperweave.app/a/inneraura/dividers/void" alt="void divider"/>
  <br/>
  <ul>
<li><sub><code>/a/inneraura/dividers/{slug}</code></sub></li>
<li><sub><code>hyperweave.app/a/inneraura/dividers/void</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">zeropoint<br/><sub>aurora rule + nexus beacon</sub></th>
<td>
  <img src="https://hyperweave.app/a/inneraura/dividers/zeropoint" alt="zeropoint divider"/>
  <br/>
  <ul>
<li><sub><code>/a/inneraura/dividers/{slug}</code></sub></li>
<li><sub><code>hyperweave.app/a/inneraura/dividers/zeropoint</code></sub></li>
</ul>
</td>
</tr>
</table>

<h3 id="error-fallback">Error fallback: SMPTE NO SIGNAL</h3>

Every broken `<img>` URL renders the SMPTE RP 219 test pattern with `ERR_NNN` matching the HTTP status, instead of a browser broken-image icon.

<p align="center">
  <img src="https://hyperweave.app/v1/badge/TEST/value/unknown-genome.static" alt="404 error fallback (intentionally broken URL)"/>
</p>

<p align="center">
  <ul>
<li><sub><code>/v1/badge/{title}/{value}/{unknown-genome}.static</code></sub></li>
<li><sub><code>hyperweave.app/v1/badge/TEST/value/unknown-genome.static</code></sub></li>
</ul>
</p>

---

## Install

```bash
uv add hyperweave            # CLI + SVG rendering (the base)
uv add 'hyperweave[serve]'   # + HTTP server  (hyperweave serve)
uv add 'hyperweave[mcp]'     # + MCP server   (hyperweave mcp)
uv add 'hyperweave[all]'     # + both servers
# or swap `uv add` for `pip install`
```

Requires Python 3.12+. The base install is CLI + rendering; the HTTP and MCP servers are optional extras so the core stays lean.

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
# Static badge
hw_compose(type="badge", title="BUILD", value="passing", genome="brutalist")

# Data-driven badge — unified token grammar (gh:owner/repo.metric, pypi:pkg.metric, ...)
hw_compose(type="badge", title="STARS", data="gh:anthropics/claude-code.stars", genome="brutalist")

# Strip with multiple live metrics
hw_compose(type="strip", title="readme-ai",
           data="gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,pypi:readmeai.version",
           genome="chrome")

# Marquee with mixed text + live tokens
hw_compose(type="marquee-horizontal",
           data="text:NEW RELEASE,gh:anthropics/claude-code.stars,text:DOWNLOAD",
           genome="brutalist")

# Discoverable shortcut for single-metric live badges
hw_live(provider="github", identifier="anthropics/claude-code", metric="stars")

hw_kit(type="readme", genome="brutalist", badges="build:passing")
hw_discover(what="all")
```

### CLI

```bash
# Badge
hyperweave compose badge "build" "passing" --genome brutalist

# Strip with metrics
hyperweave compose strip "readme-ai" "STARS:2.9k,FORKS:278" -g brutalist

# Live data through the unified --data token grammar
hyperweave compose badge "STARS" --data 'gh:anthropics/claude-code.stars' -g brutalist

# Marquee with mixed text + live tokens
hyperweave compose marquee-horizontal --data 'text:NEW RELEASE,gh:owner/repo.stars,text:DOWNLOAD' -g brutalist

# Artifact kit
hyperweave kit readme -g brutalist --badges "build:passing,version:v0.2.0" --social "github,discord"

# Profile card (live GitHub data, path-segment identity)
hyperweave compose stats eli64s -g chrome -o stats.svg

# Star history chart
hyperweave compose chart stars eli64s/readme-ai -g brutalist -o chart.svg

# Custom genome from a local JSON file (validated against the profile contract)
hyperweave compose badge "DEPLOY" "live" --genome-file ./my-genome.json
hyperweave validate-genome ./my-genome.json
```

### HTTP API

```bash
# URL grammar: /v1/{type}/{title}/{value}/{genome}.{motion}
curl 'https://hyperweave.app/v1/strip/readme-ai/brutalist.static?value=STARS:2.9k,FORKS:278'

# Live data via the unified ?data= grammar (works on badge / strip / marquee)
curl 'https://hyperweave.app/v1/badge/STARS/chrome.static?data=gh:anthropics/claude-code.stars'
curl 'https://hyperweave.app/v1/strip/readme-ai/brutalist.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks'
curl 'https://hyperweave.app/v1/marquee/SCROLL/brutalist.static?data=text:NEW%20RELEASE,gh:anthropics/claude-code.stars'

# Chromatic variants (automata: 16 solo tones, pair any two via &pair=...; chrome: horizon/abyssal/lightning/graphite/moth)
curl 'https://hyperweave.app/v1/badge/PYPI/automata.static?variant=teal&pair=violet&data=pypi:hyperweave.version'
curl 'https://hyperweave.app/v1/badge/build/passing/automata.static?size=compact'

# Genome-themed dividers
curl 'https://hyperweave.app/v1/divider/band/chrome.static'
curl 'https://hyperweave.app/v1/divider/seam/brutalist.static'
curl 'https://hyperweave.app/v1/divider/dissolve/automata.static'

# Genome-agnostic dividers
curl 'https://hyperweave.app/a/inneraura/dividers/zeropoint'

# POST compose
curl -X POST https://hyperweave.app/v1/compose \
  -H "Content-Type: application/json" \
  -d '{"type":"strip","title":"hyperweave","genome":"brutalist","value":"STARS:2.9k"}'

# Local server
hyperweave serve --port 8000
```

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

- **Semantic metadata:** provenance, reasoning, spatial trace, aesthetic DNA. Machine-readable context so the next agent in the chain knows what it's looking at and why.
- **CSS state machines:** `data-hw-status`, `data-hw-state`, `data-hw-regime` drive visual transitions through the Custom Property Bridge. No JavaScript.
- **Pure CSS/SMIL animation:** all motion uses compositor-safe properties (`transform`, `opacity`, `filter`). No script tags. Works anywhere SVGs render: GitHub's Camo proxy, email clients, Notion embeds.
- **Accessibility:** WCAG AA, `prefers-reduced-motion`, `prefers-color-scheme`, `forced-colors`, ARIA markup. Structural, not decorative.

| Dimension | Count |
|---|---|
| Frame types | 10 (badge, strip, icon, divider, marquee-horizontal, stats, chart, matrix, receipt, rhythm-strip) |
| Genomes | 4 (automata, brutalist, chrome, primer) |
| Motion configs | 6 (1 static + 5 border SMIL) |
| Glyphs | 189 (183 brand marks + 6 geometric shapes) |
| Divider variants | 10: 5 genome-themed (`band` chrome, `seam` + `sigil` brutalist, `dissolve` automata, `aura` primer) + 5 genome-agnostic (`block`, `current`, `takeoff`, `void`, `zeropoint`) at <code>/a/inneraura/dividers/</code> |
| Metadata tiers | 5 (Tier 0 silent &rarr; Tier 4 reasoning) |
| Bundled fonts | 5 (JetBrains Mono, Orbitron, Chakra Petch, Barlow Condensed, Inter), embedded per artifact, no external font requests |

Stack: Pydantic, FastAPI, FastMCP v3, Jinja2, Typer.

---

## Data Connectors

HyperWeave binds live data into any artifact through a unified token grammar (`?data=...`). Tokens are comma-separated; each token is either a literal (`text:`, `kv:`) or a live fetch (`<provider>:<identifier>.<metric>`).

<p align="center">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/main/assets/tables/hw-data-connectors-matrix-v2.svg" alt="Data connectors matrix: 9 live providers — GitHub, PyPI, npm, crates.io, Hugging Face, Docker Hub, arXiv, OpenSSF Scorecard, GitHub Actions — plus text and kv literal tokens" width="100%"/>
</p>

<details>
<summary>Copy a token &middot; view as table</summary>

| Prefix | Source | Identifier shape | Metrics |
|--------|--------|------------------|---------|
| `gh` / `github` | [GitHub](https://github.com) | `owner/repo` | `stars`, `forks`, `watchers`, `contributors`, `issues`, `pull_requests`, `last_push`, `build`, `license`, `language` |
| `pypi` | [PyPI](https://pypi.org) + [pepy.tech](https://pepy.tech) | `package` | `version`, `license`, `python_requires`, `downloads` |
| `npm` | [npm](https://www.npmjs.com) | `package` | `version`, `license`, `downloads` |
| `crates` / `cargo` | [crates.io](https://crates.io) | `crate` | `version`, `downloads`, `recent_downloads`, `license` |
| `hf` / `huggingface` | [Hugging Face](https://huggingface.co) | `org/model` | `downloads`, `likes`, `tags`, `pipeline_tag`, `library_name`, `license`, `gated`, `last_modified` |
| `docker` | [Docker Hub](https://hub.docker.com) | `namespace/repo` | `pull_count`, `star_count`, `last_updated` |
| `arxiv` | [arXiv](https://arxiv.org) | `id` (e.g. `2310.06825`) | `title`, `authors`, `published`, `updated`, `categories`, `summary`, `journal_ref`, `doi` |
| `scorecard` | [OpenSSF Scorecard](https://github.com/ossf/scorecard) | `owner/repo` | `score` (overall trust), plus per-check: `code_review`, `maintained`, `vulnerabilities`, `token_permissions`, ... |
| `dora` | [GitHub Actions](https://github.com/features/actions) | `owner/repo` | `deploy_frequency`, `lead_time`, `change_failure_rate`, `mttr` (30-day window) |
| `text` | literal | &mdash; | renders the payload as displayed text |
| `kv` | literal | `KEY=VALUE` | static role-tagged value |

</details>

- **Caching:** live values for 5&ndash;10 min; a failed fetch caches 60s and shows `—` rather than a fabricated zero.
- **Isolation:** each provider has its own circuit breaker, so one upstream outage can't trip the others.
- **Escaping:** commas inside `text:` / `kv:` values escape as `\,`.

&rarr; [Open an issue](https://github.com/InnerAura/hyperweave/issues/new) to request a connector.

---

## Contributing

HyperWeave is early. If you're interested in building genomes, extending frame types, or just seeing what this looks like in your own README, [join the Discord](https://discord.gg/wVmcAZPQZ8).

---

<p align="center">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/main/assets/footers/inneraura-footer-liquid.svg" alt="InnerAura Labs" width="100%"/>
</p>

<p align="center">
  <a href="https://discord.gg/wVmcAZPQZ8">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/main/assets/icons/cobalt-sapphire-discord.svg" width="48" alt="Discord"/>
  </a>
  &nbsp;
  <a href="https://www.instagram.com/hyperweave.ai/">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/main/assets/icons/cobalt-sapphire-instagram.svg" width="48" alt="Instagram"/>
  </a>
  &nbsp;
  <a href="https://www.linkedin.com/company/inneraura">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/main/assets/icons/cobalt-sapphire-linkedin.svg" width="48" alt="LinkedIn"/>
  </a>
  &nbsp;
  <a href="https://www.tiktok.com/@hyperweave.ai">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/main/assets/icons/cobalt-sapphire-tiktok.svg" width="48" alt="TikTok"/>
  </a>
  &nbsp;
  <a href="https://x.com/InnerAuraLabs">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/main/assets/icons/cobalt-sapphire-x.svg" width="48" alt="X"/>
  </a>
  &nbsp;
  <a href="https://www.youtube.com/@InnerAuraLabs">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/main/assets/icons/cobalt-sapphire-youtube.svg" width="48" alt="YouTube"/>
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

[return-top]: https://raw.githubusercontent.com/InnerAura/hyperweave/main/assets/buttons/button-liquid.svg
