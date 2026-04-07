# Changelog

All notable changes to HyperWeave are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.4] - 2026-04-07

### Fixed
- Unused variable lint error in badge resolver
- Line length lint error in ProfileConfig model
- Ruff format on context.py, resolver.py, models.py
- MCP config JSON formatting in README

## [0.1.3] - 2026-04-07

### Added
- **Profile/genome decoupling** — 30 template partials dispatch on data presence, not genome identity. New genomes under existing profiles require zero template changes.
- **Profile contract schemas** — `brutalist.contract.json` and `chrome.contract.json` define required `--dna-*` variables, types, and WCAG contrast pairs per profile
- `hyperweave validate-genome` CLI command — validates genome JSON against profile contract schema with WCAG AA contrast enforcement (4.5:1 primary, 3.0:1 secondary)
- **CSS assembler tree-shaking** — frame-type gating: bridge, expression, status, telemetry, and motion modules only included when relevant. `<!-- hw:css-modules: [...] -->` debug comment in output.
- 2 CSS gating tests (motion omission, frame-type exclusion)
- `docs/genome-coupling-audit.md` — full inventory of 41 decoupled template branches
- `docs/css-audit-report.md` — CSS module map with waste quantification per specimen

### Changed
- All `xmlns:hw` namespace URIs updated from `hyperweave.dev/hw/v8.0` to `hyperweave.app/hw/v1.0`
- Footer text and User-Agent updated from `hyperweave.dev` to `hyperweave.app`
- SVG gradient `<stop>` elements use resolved hex colors instead of `var()` (unreliable in some SVG renderers)
- Marquee resolvers fully parametrized via profile YAML (28 layout/styling keys per profile)
- Badge bevel/lighting extras gated on genome data presence, not profile identity

### Removed
- Dead `metadata.xml.j2` template and `_build_metadata_xml()` — rendered every compose call but never consumed by any template

## [0.1.2] - 2026-04-03

### Added
- `hyperweave mcp` CLI subcommand — MCP server now launchable from CLI (was only `python -m hyperweave.mcp`)
- `hw` as second CLI entry point (`hw` = `hyperweave` alias)
- 2 new glyphs: `linkedin`, `email` (hand-authored, 99 total) with `gmail`/`mail` inference aliases
- `?subtitle=` query parameter on banner route
- `?t=` title override query parameter on badge, strip, banner, and marquee routes (for titles containing slashes)
- `url_grammar` section in `hw_discover` MCP tool — returns URL patterns, query params, and examples per frame type

### Fixed
- **install-hook command name** — hook wrote `hw session receipt` but binary was `hyperweave`; every session receipt since install was silently lost
- **Orphan `data-hw-glyph` attribute** — tightened guard to `has_glyph` instead of `glyph_id`
- **Banner excessive whitespace** — viewBox height reduced from 600px to 400px
- **Banner subtitle** — kinetic motion incorrectly used footer label ("V0.1 . CHROME HORIZON") as subtitle; now uses actual user-provided subtitle
- **Banner footer** — removed hardcoded "V0.1" version string from banner footer text
- **Stale accessibility comment** — "placeholder is intentionally empty" removed (genomes provide real light mode alleles)

## [0.1.1] - 2026-04-01

### Added
- PyPI publishing workflow via trusted publishing (OIDC, no API tokens)
- Tag-driven versioning via hatch-vcs (replaces hardcoded version)
- Build status connector queries GitHub Checks API (GitHub Actions support)

### Fixed
- Docker build: create `src/hyperweave/` directory before `uv sync` so hatch-vcs can write `_version.py`
- Deploy workflow: convert `git describe` output to PEP 440 format
- CI: `fetch-depth: 0` for hatch-vcs tag discovery
- `pyproject.toml`: move `dependencies` above `[project.urls]` to fix TOML scoping bug
- Build status badge: query Checks API first, fall back to legacy Status API (fixes perpetual "building" state)
- README: relative image paths replaced with absolute URLs for PyPI rendering

## [0.1.0] - 2026-03-27

Clean-room rewrite. Specimen-first compositor for self-contained SVG artifacts.

### Added

**Composition Engine**
- Core `compose()` entry point: `ARTIFACT = Frame x Genome x Profile x Motion x Slots`
- 12 frame-specific resolvers: badge, strip, banner, icon, divider, marquee (h/v/counter), receipt, rhythm-strip, master-card, catalog
- Multi-artifact branding kits via `compose_kit()`
- Frame-aware CSS assembly (each artifact only includes CSS it uses)
- Policy lane enforcement: CIM compliance + WCAG contrast checking

**Genomes & Profiles (Specimen-Backed)**
- 2 launch genomes: brutalist-emerald (dark/sharp), chrome-horizon (dark/metallic)
- 2 structural profiles: brutalist, chrome
- Genome JSON with full `--dna-*` CSS custom property vocabulary (~35 properties)
- Profile YAML with typography, geometry, glyph backing, status shape config
- Chrome-horizon: fully separate rendering path (envelope gradients, bevel filters, specular highlights)

**Frame Types (12)**
- badge (shields.io-grade, auto-width from text measurement)
- strip (52px, metric cells with dividers)
- banner (1200x600 full / 800x220 compact)
- icon (64x64, 3 distinct frame systems by profile)
- divider (5 specimen-faithful variants: block, current, takeoff, void, zeropoint)
- marquee-horizontal, marquee-vertical, marquee-counter (SMIL scroll animation)
- receipt, rhythm-strip, master-card (telemetry frames, genome-independent)
- catalog (editorial layout)

**Motion System (14 primitives)**
- 5 border motions (SMIL): chromatic-pulse, corner-trace, dual-orbit, entanglement, rimrun
- 9 kinetic typography motions (CSS/SMIL): bars, broadcast, cascade, collapse, converge, crash, drop, breach, pulse
- All motion SVG via Jinja2 templates (zero f-string SVG in Python)
- Rimrun traces badge/strip seams, not outer perimeter
- CIM compliance tracking with waiver documentation per motion

**Glyph System**
- 97 glyphs: 91 from Simple Icons + 6 geometric shapes
- Build-time extraction script (npm simple-icons -> data/glyphs.json)
- 3 rendering modes: auto, fill, wire
- Auto-inference from label text (e.g. "github" -> github glyph)

**Telemetry Parsing Engine**
- 5-pass JSONL transcript parser (tool calls, outcomes, user text, agent spans, durations)
- 3-signal weighted stage detector (temporal 0.3, class shift 0.4, explicit 0.3)
- Dual-signal correction classifier (lexical + behavioral patterns)
- Per-model cost calculator with cache breakdown
- Data contract builder (<50 lines orchestration glue)
- All config in YAML (tool-classes, tool-colors, stage-labels, stage-config)

**Interfaces**
- CLI (Typer): compose, kit, render, genomes, serve, version
- HTTP API (FastAPI): URL grammar routes, POST /v1/compose, discovery endpoints, live data badges, specimen serving (/a/), genome registry (/g/)
- MCP Server (FastMCP v3): 4 tools (hw_compose, hw_live, hw_kit, hw_discover), 3 resources

**Data Connectors**
- 6 providers: GitHub, PyPI, npm, Docker Hub, arXiv, HuggingFace
- SSRF protection with host allowlist and private IP blocking
- Circuit breaker pattern (5 failures -> open -> half-open 60s)
- In-memory connector cache with TTL

**Living Artifacts**
- CSS state machine embedding for data-bound badges
- Threshold rules: coverage, uptime, latency, score, error_rate, build
- Attribute-driven visual updates via CSS cascade (no recomposition)

**Infrastructure**
- Zero f-string SVG in Python (all SVG via 40 Jinja2 templates)
- All config in YAML/JSON in data/ (zero hardcoded mappings in Python)
- Type discipline: StrEnum throughout, FrozenModel base, ResolvedArtifact typed output
- Self-contained SVG: inline styles, scoped IDs, no external resources
- Tier 3 metadata by default (Reproducible + Aesthetic + Reasoning)
- WCAG-AA accessibility (role, aria-*, prefers-reduced-motion, prefers-color-scheme, forced-colors)
- ID scoping with `hw-{uuid}` prefix for multi-artifact coexistence
- Generation event capture (fire-and-forget telemetry on every compose())
