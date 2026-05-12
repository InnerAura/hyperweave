<div id="top">

<p align="center">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/f36c8969d15d76da4400ebcfaa04ec1e2eacb170/assets/hyperweave-banner.svg" alt="HyperWeave" width="800"/>
</p>

<p align="center">
  <strong>Headless visual output layer for AI agents.</strong><br/>
  One API call &rarr; self-contained SVG. No JavaScript. No dependencies. No runtime.<br/>
  Works everywhere an <code>&lt;img&gt;</code> tag works.
</p>

<!-- <p align="center">
  <img src="https://hyperweave.app/v1/badge/STARS/chrome.static?data=gh:InnerAura/hyperweave.stars" alt="stars"/>
  <img src="https://hyperweave.app/v1/badge/FORKS/chrome.static?data=gh:InnerAura/hyperweave.forks" alt="forks"/>
  <img src="https://hyperweave.app/v1/badge/VERSION/chrome.static?data=pypi:hyperweave.version" alt="version"/>
  <img src="https://hyperweave.app/v1/badge/LICENSE/chrome.static?data=gh:InnerAura/hyperweave.license" alt="license"/>
  <img src="https://hyperweave.app/v1/badge/PYTHON/chrome.static?data=pypi:hyperweave.python_requires" alt="python"/>
</p> -->

<p align="center">
  <img src="https://hyperweave.app/v1/strip/hyperweave/chrome.static?data=gh:InnerAura/hyperweave.build,pypi:hyperweave.version,gh:InnerAura/hyperweave.license&glyph=github" alt="strip"/>
</p>

<!--
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

When an agent needs to produce something visual &mdash; a status card, a dashboard, a receipt of its work &mdash; it generates React, HTML, or pixels, locked in the environment that made it. Embed it in markdown, pass it to another agent &mdash; it breaks or loses context. There's no portable visual primitive for agents.

HyperWeave is that primitive. One API call returns a self-contained SVG with data binding, branding, and machine-readable metadata baked in. No JavaScript, no dependencies, no runtime. It renders in GitHub READMEs, Slack, Notion, docs, your site, email, VS Code, or terminal. Every surface that renders an `<img>` tag is a HyperWeave surface.

---

## Agentic Artifacts

Every AI coding session produces a receipt &mdash; cost, tokens, tool distribution, session rhythm. One install, fully automatic.

```bash
hyperweave install-hook
```

<p align="center">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/main/assets/examples/telemetry/receipt_voltage_xlarge.svg" alt="session receipt — voltage livery showing 262M tokens, 562 calls, 52 stages, divergence flag" width="800"/>
</p>
<p align="center"><sub>262M tokens &middot; 562 calls &middot; 52 stages &middot; $175 &mdash; voltage</sub></p>

<p align="center">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/main/assets/examples/telemetry/rhythm_strip_voltage_xlarge.svg" alt="session rhythm strip — same session data at 92px tall" width="800"/>
</p>
<p align="center"><sub>Rhythm strip &mdash; the same session data at 92px tall</sub></p>

<p align="center">
  <img src="https://raw.githubusercontent.com/InnerAura/hyperweave/main/assets/examples/telemetry/receipt_claude-code_medium.svg" alt="session receipt — claude-code livery on warm paper substrate" width="800"/>
</p>
<p align="center"><sub>Same data, different livery &mdash; claude-code</sub></p>

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

## Genomes &mdash; Aesthetic DNA

A genome is a portable, machine-readable aesthetic specification. It encodes the complete visual identity &mdash; chromatic system, surface material, motion vocabulary, geometric form language &mdash; as a set of CSS custom properties that any agent can consume and apply consistently across every artifact type.

Three production genomes ship today. Custom genome generation via AI skill files coming soon.

<!--
Why genome and not theme? Because brand isn't a design problem, it's an infrastructure problem. When an agent says "build me a status page," it has zero memory of visual identity. A genome solves that: define once, express everywhere, from a 90px badge to a 900px star history chart. The same genome produces different artifacts that feel like they came from the same hand.
-->

<p align="center">
  <a href="#brutalist"><kbd>brutalist</kbd></a>
  &middot;
  <a href="#automata"><kbd>automata</kbd></a>
  &middot;
  <a href="#chrome"><kbd>chrome</kbd></a>
</p>

<h3 id="brutalist">brutalist</h3>

<p align="center">
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=celadon" alt="PYPI — celadon variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=carbon" alt="PYPI — carbon variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=alloy" alt="PYPI — alloy variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=temper" alt="PYPI — temper variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=pigment" alt="PYPI — pigment variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=ember" alt="PYPI — ember variant"/>
  <br/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=archive" alt="PYPI — archive variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=signal" alt="PYPI — signal variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=pulse" alt="PYPI — pulse variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=depth" alt="PYPI — depth variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=afterimage" alt="PYPI — afterimage variant"/>
  <img src="https://hyperweave.app/v1/badge/PYPI/brutalist.static?data=pypi:hyperweave.version&glyph=python&variant=primer" alt="PYPI — primer variant"/>
</p>

<p align="center">
  <sub>12 variants: <code>celadon</code> &middot; <code>carbon</code> &middot; <code>alloy</code> &middot; <code>temper</code> &middot; <code>pigment</code> &middot; <code>ember</code> &middot; <code>archive</code> &middot; <code>signal</code> &middot; <code>pulse</code> &middot; <code>depth</code> &middot; <code>afterimage</code> &middot; <code>primer</code></sub>
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
<li><sub><code>/v1/badge/{title}/{value}/{genome}.static?state={state}&variant={celadon|carbon|alloy|temper|pigment|ember|archive|signal|pulse|depth|afterimage|primer}</code></sub></li>
<li><sub><code>hyperweave.app/v1/badge/BUILD/passing/brutalist.static?state=passing&variant=celadon</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Dashboard<br/><sub>strip</sub></th>
<td>
  <img src="https://hyperweave.app/v1/strip/readme-ai/brutalist.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,pypi:readmeai.version&subtitle=eli64s/readme-ai&glyph=github&variant=celadon" alt="strip"/>
  <br/>
  <ul>
<li><sub><code>/v1/strip/{title}/{genome}.static?data={tokens}&subtitle={text}&glyph={glyph}&variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/strip/readme-ai/brutalist.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,pypi:readmeai.version&subtitle=eli64s/readme-ai&glyph=github&variant=celadon</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Profile<br/><sub>stats card</sub></th>
<td>
  <img src="https://hyperweave.app/v1/stats/eli64s/brutalist.static?variant=celadon" alt="stats" width="100%"/>
  <br/>
  <ul>
<li><sub><code>/v1/stats/{username}/{genome}.static?variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/stats/eli64s/brutalist.static?variant=celadon</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Star Chart<br/><sub>star history</sub></th>
<td>
  <img src="https://hyperweave.app/v1/chart/stars/eli64s/readme-ai/brutalist.static?variant=celadon" alt="star chart" width="100%"/>
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
  <img src="https://hyperweave.app/v1/marquee/readme-ai/brutalist.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,pypi:readmeai.version,pypi:readmeai.downloads,docker:zeroxeli/readme-ai.pull_count&variant=celadon" alt="marquee"/>
  <br/>
  <ul>
<li><sub><code>/v1/marquee/{title}/{genome}.static?data={tokens}&variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/marquee/readme-ai/brutalist.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,pypi:readmeai.version,pypi:readmeai.downloads,docker:zeroxeli/readme-ai.pull_count&variant=celadon</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Icons<br/><sub>circle + square</sub></th>
<td>
  <img src="https://hyperweave.app/v1/icon/github/brutalist.static?shape=circle&variant=celadon" alt="github — celadon" width="56"/>
  <img src="https://hyperweave.app/v1/icon/discord/brutalist.static?shape=circle&variant=carbon" alt="discord — carbon" width="56"/>
  <img src="https://hyperweave.app/v1/icon/docker/brutalist.static?shape=circle&variant=alloy" alt="docker — alloy" width="56"/>
  <img src="https://hyperweave.app/v1/icon/npm/brutalist.static?shape=square&variant=temper" alt="npm — temper" width="56"/>
  <img src="https://hyperweave.app/v1/icon/spotify/brutalist.static?shape=square&variant=pigment" alt="spotify — pigment" width="56"/>
  <img src="https://hyperweave.app/v1/icon/anthropic/brutalist.static?shape=square&variant=ember" alt="anthropic — ember" width="56"/>
  <br/>
  <ul>
<li><sub><code>/v1/icon/{glyph}/{genome}.static?shape={circle|square}&variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/icon/github/brutalist.static?shape=circle&variant=celadon</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Divider<br/><sub>seam</sub></th>
<td>
  <img src="https://hyperweave.app/v1/divider/seam/brutalist.static?variant=celadon" alt="brutalist seam divider"/>
  <br/>
  <ul>
<li><sub><code>/v1/divider/seam/{genome}.static?variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/divider/seam/brutalist.static?variant=celadon</code></sub></li>
</ul>
</td>
</tr>
</table>
<h3 id="automata">automata</h3>

<p align="center">
  <img src="https://hyperweave.app/v1/badge/DOCKER/PULL/automata.static?glyph=docker&variant=teal" alt="DOCKER PULL — teal variant"/>
  <img src="https://hyperweave.app/v1/badge/DISCORD/JOIN/automata.static?glyph=discord&variant=violet" alt="DISCORD JOIN — violet variant"/>
  <img src="https://hyperweave.app/v1/badge/STARS/automata.static?data=gh:eli64s/readme-ai.stars&glyph=github&variant=amber" alt="STARS — amber variant"/>
  <img src="https://hyperweave.app/v1/badge/HF/MODELS/automata.static?glyph=huggingface&variant=sulfur" alt="HF MODELS — sulfur variant"/>
  <img src="https://hyperweave.app/v1/badge/SPOTIFY/LISTEN/automata.static?glyph=spotify&variant=jade" alt="SPOTIFY LISTEN — jade variant"/>
</p>

<p align="center">
  <sub>16 tones: <code>violet</code> &middot; <code>teal</code> &middot; <code>bone</code> &middot; <code>steel</code> &middot; <code>amber</code> &middot; <code>jade</code> &middot; <code>magenta</code> &middot; <code>cobalt</code> &middot; <code>toxic</code> &middot; <code>solar</code> &middot; <code>abyssal</code> &middot; <code>crimson</code> &middot; <code>sulfur</code> &middot; <code>indigo</code> &middot; <code>burgundy</code> &middot; <code>copper</code>. Pair any two via <code>?variant=primary&pair=secondary</code>.</sub>
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
  <img src="https://hyperweave.app/v1/stats/eli64s/automata.static?variant=bone&v=2" alt="stats" width="100%"/>
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
  <img src="https://hyperweave.app/v1/chart/stars/eli64s/readme-ai/automata.static?variant=bone&v=2" alt="star chart" width="100%"/>
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
  <img src="https://hyperweave.app/v1/marquee/readme-ai/automata.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,pypi:readmeai.version,pypi:readmeai.downloads,docker:zeroxeli/readme-ai.pull_count&variant=bone" alt="marquee"/>
  <br/>
  <ul>
<li><sub><code>/v1/marquee/{title}/automata.static?data={tokens}&variant={tone}</code></sub></li>
<li><sub><code>hyperweave.app/v1/marquee/readme-ai/automata.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,pypi:readmeai.version,pypi:readmeai.downloads,docker:zeroxeli/readme-ai.pull_count&variant=bone</code></sub></li>
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
  <img src="https://hyperweave.app/v1/badge/BUILD/chrome.static?data=gh:InnerAura/hyperweave.build&glyph=githubactions&variant=horizon" alt="BUILD — horizon variant"/>
  <img src="https://hyperweave.app/v1/badge/BLUESKY/POST/chrome.static?glyph=bluesky&variant=abyssal" alt="BLUESKY POST — abyssal variant"/>
  <img src="https://hyperweave.app/v1/badge/DOCKER/chrome.static?data=docker:zeroxeli/readme-ai.pull_count&glyph=docker&variant=lightning" alt="DOCKER pulls — lightning variant"/>
  <img src="https://hyperweave.app/v1/badge/STARS/chrome.static?data=gh:eli64s/readme-ai.stars&glyph=github&variant=graphite" alt="STARS — graphite variant"/>
  <img src="https://hyperweave.app/v1/badge/ANTHROPIC/CLAUDE/chrome.static?glyph=anthropic&variant=moth" alt="ANTHROPIC CLAUDE — moth variant"/>
</p>

<p align="center">
  <sub>5 variants: <code>horizon</code> &middot; <code>abyssal</code> &middot; <code>lightning</code> &middot; <code>graphite</code> &middot; <code>moth</code></sub>
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
<li><sub><code>/v1/badge/{title}/{value}/{genome}.static?state={state}&variant={horizon|abyssal|lightning|graphite|moth}</code></sub></li>
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
  <img src="https://hyperweave.app/v1/stats/eli64s/chrome.static?variant=horizon" alt="stats" width="100%"/>
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
  <img src="https://hyperweave.app/v1/chart/stars/eli64s/readme-ai/chrome.static?variant=horizon" alt="star chart" width="100%"/>
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
  <img src="https://hyperweave.app/v1/marquee/readme-ai/chrome.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,pypi:readmeai.version,pypi:readmeai.downloads,docker:zeroxeli/readme-ai.pull_count&variant=horizon" alt="marquee"/>
  <br/>
  <ul>
<li><sub><code>/v1/marquee/{title}/{genome}.static?data={tokens}&variant={variant}</code></sub></li>
<li><sub><code>hyperweave.app/v1/marquee/readme-ai/chrome.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,pypi:readmeai.version,pypi:readmeai.downloads,docker:zeroxeli/readme-ai.pull_count&variant=horizon</code></sub></li>
</ul>
</td>
</tr>
<tr>
<th align="left">Icons<br/><sub>circle + square</sub></th>
<td>
  <img src="https://hyperweave.app/v1/icon/youtube/chrome.static?shape=circle&variant=horizon" alt="youtube" width="56"/>
  <img src="https://hyperweave.app/v1/icon/notion/chrome.static?shape=circle&variant=horizon" alt="notion" width="56"/>
  <img src="https://hyperweave.app/v1/icon/npm/chrome.static?shape=square&variant=horizon" alt="npm" width="56"/>
  <img src="https://hyperweave.app/v1/icon/instagram/chrome.static?shape=square&variant=horizon" alt="instagram" width="56"/>
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

<br />

| | brutalist | automata | chrome |
|---|---|---|---|
| Aesthetic | Raw material | Living cellular grid | Metallic precision |
| Variants | 12 (6 dark, 6 light) | 16 tones, any two pair | 5 named |
| Motion | Animated border SMIL | Animated cell grid | Animated border SMIL |
| Divider | `seam` | `dissolve` | `band` |

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

<h3 id="error-fallback">Error fallback &mdash; SMPTE NO SIGNAL</h3>

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

- **Semantic metadata** &mdash; provenance, reasoning, spatial trace, aesthetic DNA. Machine-readable context so the next agent in the chain knows what it's looking at and why.
- **CSS state machines** &mdash; `data-hw-status`, `data-hw-state`, `data-hw-regime` drive visual transitions through the Custom Property Bridge. No JavaScript.
- **Pure CSS/SMIL animation** &mdash; all motion uses compositor-safe properties (`transform`, `opacity`, `filter`). No script tags. Works inside GitHub's Camo proxy, email clients, Notion embeds &mdash; anywhere SVGs render.
- **Accessibility** &mdash; WCAG AA, `prefers-reduced-motion`, `prefers-color-scheme`, `forced-colors`, ARIA markup. Structural, not decorative.

| Dimension | Count |
|---|---|
| Frame types | 9 (badge, strip, icon, divider, marquee-horizontal, stats, chart, receipt, rhythm-strip) |
| Genomes | 3 (automata, brutalist, chrome) |
| Motion configs | 6 (1 static + 5 border SMIL) |
| Glyphs | 99 (93 Simple Icons + 6 geometric) |
| Divider variants | 8 &mdash; 3 genome-themed (`band` chrome, `seam` brutalist, `dissolve` automata) + 5 genome-agnostic (`block`, `current`, `takeoff`, `void`, `zeropoint`) at <code>/a/inneraura/dividers/</code> |
| Metadata tiers | 5 (Tier 0 silent &rarr; Tier 4 reasoning) |
| Bundled fonts | 3 (JetBrains Mono, Orbitron, Chakra Petch — base64-embedded) |

Stack: Pydantic, FastAPI, FastMCP v3, Jinja2, Typer.

---

## Data Connectors

HyperWeave binds live data into any artifact through a unified token grammar (`?data=...`). Tokens are comma-separated; each token is either a literal (`text:`, `kv:`) or a live fetch (`<provider>:<identifier>.<metric>`).

| Prefix | Source | Identifier shape | Metrics |
|--------|--------|------------------|---------|
| `gh` / `github` | GitHub | `owner/repo` | `stars`, `forks`, `watchers`, `issues`, `license`, `language`, `build` |
| `pypi` | PyPI + pypistats.org | `package` | `version`, `license`, `python_requires`, `downloads` |
| `npm` | npm registry | `package` | `version`, `license`, `downloads` |
| `hf` / `huggingface` | HuggingFace Hub | `org/model` | `downloads`, `likes`, `tags`, `pipeline_tag`, `library_name` |
| `docker` | Docker Hub | `namespace/repo` | `pull_count`, `star_count`, `last_updated` |
| `arxiv` | arXiv API | `id` (e.g. `2310.06825`) | `title`, `authors`, `published`, `categories`, `summary` |
| `text` | literal | &mdash; | renders the payload as displayed text |
| `kv` | literal | `KEY=VALUE` | static role-tagged value |

Live tokens cache for 5&ndash;10 minutes per provider. Failures cache for 60s and surface as the em-dash sentinel (`—`) instead of fabricating zero values. Each provider runs through its own circuit breaker so a single upstream outage cannot trip unrelated fetches.

Embedded commas inside `text:` and `kv:` values escape as `\,`.

&rarr; [Open an issue](https://github.com/InnerAura/hyperweave/issues/new) to request a connector.

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
