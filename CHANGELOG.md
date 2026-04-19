# Changelog

All notable changes to HyperWeave are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.6] - 2026-04-19

### Added

- **Font-aware text measurement.** `measure_text` dispatches to per-font LUTs via a `FontRegistry` (Inter, Orbitron, JetBrains Mono). Callers pass `font_family`, `font_size`, `font_weight`, `letter_spacing_em` — no more `bold` / `monospace` booleans. `scripts/extract_font_metrics.py` decodes base64 WOFF2 sources via fontTools and emits JSON matching the existing `inter.json` schema. The measurement contract (ASCII glyph set, linear size scaling, kerning and ligatures ignored, unknown family falls back to Inter with a one-shot warning) is documented verbatim at the top of `core/font_metrics.py`.
- **Paradigm config files.** `data/paradigms/{default,chrome,brutalist}.yaml` carry per-paradigm layout and typography config. `ParadigmSpec` Pydantic model with nested frame configs (`badge`, `strip`, `banner`, `chart`, `stats`, `icon`) in `core/paradigm.py`. Loader + registry parity via `load_paradigms()` and `get_paradigms()`.
- **Paradigm/genome cross-validation.** `compose/validate_paradigms.py::validate_genome_against_paradigms()` runs at `ConfigLoader.load`. Genomes that opt into a paradigm must declare every field in its `requires_genome_fields` or load raises `ValueError` with a structured message listing every missing `(paradigm, field)` pair. Kept out of `GenomeSpec` as a `@model_validator` to avoid a circular loader dependency.
- **Invariant 11** (CLAUDE.md Verify block): no specimen colors in template fallbacks. `grep "default('#"` in templates must be zero.
- **Invariant 12** (CLAUDE.md Verify block): adding a new paradigm within the existing frame contract requires zero Python edits. `grep 'paradigm == "'` in `.py` files and `grep '{% if paradigm'` in templates must both be zero.
- Six extensibility-proof tests in `tests/test_paradigm_extensibility.py`. `tests/helpers.py::build_partial_genome_for_testing` provides an explicit test-only bypass for the validator.
- `PROFILE_CONTRACTS.md` documents the paradigm contract: required genome fields per paradigm, how the dispatcher routes through `_resolve_paradigm` and `load_paradigms`, how to add a new paradigm from YAML + templates alone.

### Fixed

- **Brutalist badge value text collided with the status indicator.** The pre-v0.2.6 resolver measured monospace text at a cross-platform-safe 7.2 px/char; per-font LUTs measure JetBrains Mono at its accurate 6.6 px/char, so the old safety margin is gone. Brutalist badge, strip, and banner defs now embed `@font-face` declarations via `{{ font_faces | safe }}` so rendered widths equal measured widths in any viewer — not just those that happen to have the system font installed. `default.yaml` font_family declarations corrected to JetBrains Mono to match what the default partials (which alias brutalist) actually render.
- **Chrome templates no longer carry chrome-horizon's palette as fallback.** Every `| default('#hex')` specimen-leak chain is stripped from stats, chart, strip, banner, badge, icon, and all three marquee chrome templates. A future chrome genome that omits `envelope_stops`, `well_top`, `well_bottom`, `chrome_text_gradient`, `hero_text_gradient`, or `highlight_color` now fails at load time instead of silently inheriting chrome-horizon's cyan.

### Changed

- **`banner.svg.j2` split.** 224-line monolith with inline `{% if paradigm_banner == "chrome" %}` branches replaced by a 23-line dispatcher plus `frames/banner/{chrome,default}-content.j2` partials. Banner now matches the partial-dispatch pattern used by strip, badge, stats, and chart.
- **Resolvers consume `paradigm_spec` directly.** `resolve_badge`, `resolve_strip`, `resolve_chart`, `resolve_stats`, `resolve_icon`, and `resolve_banner` read `paradigm_spec.{frame}.{key}` instead of comparing the paradigm slug inline. `_PROFILE_SHAPES` and `_STATS_HEIGHTS` dicts are gone; their content lives in the paradigm YAMLs.
- **Strip inline paradigm branches replaced with context vars.** `divider_render_mode` and `status_shape_rendering` are injected by the resolver from paradigm config; the template branches on resolved values, not on slug strings.
- `_profile_visual_context` renamed to `_genome_material_context` — it has always read from `genome`, not `profile`.
- `measure_text` signature is now keyword-only after the leading `text` positional. `bold` and `monospace` kwargs removed.

### Removed

- `text_metrics` field on `GenomeSpec`. The per-zone width multiplier (`badge_value_width_factor: 1.35` on chrome-horizon) was a workaround for the Inter-only LUT; with per-font LUTs it is redundant.
- `font_scale` heuristic in the marquee row-width helper. Replaced by font-family-aware measurement.
- Dead `specular_sweep_dur` and `specular_sweep_peak` fields from `GenomeSpec`, `chrome.contract.json`, and `chrome-horizon.json`. `highlight_opacity` is retained — it has live consumers in badge and strip chrome content.

### Dev dependencies

- `fontTools` and `brotli` added so the font-metrics extraction script can decode WOFF2.

## [0.2.5] - 2026-04-13

### Fixed

- **Chart bezier regression on certain data ranges.** The chrome chart bezier path used horizontal tangents at every anchor, which produced a smooth curve only when input points were widely and evenly spaced. On tighter or uneven distributions — common with real GitHub stargazer data — the curve degenerated into flat-then-vertical segments. Replaced with Fritsch-Carlson monotonic cubic interpolation (the same algorithm D3's `curveMonotoneX` uses), which guarantees the curve passes through every anchor, never overshoots between points, and handles any point spacing robustly.

## [0.2.4] - 2026-04-13

### Added

- **Truthful chart rendering.** Charts now reflect what the data actually says. When a GitHub fetch fails, the chart renders a clear `DATA UNAVAILABLE` overlay instead of a synthesized placeholder curve. Brand-new repos with zero stars render `NEW REPO · NO STARS YET`. Every chart carries a status attribute (`fresh`, `stale`, `empty`) that downstream consumers can read.
- **Adaptive chart axes.** Y-tick values auto-generate from the data range using round numbers (1, 2, 5 × powers of 10), so labels agree with the curve at any scale. X-axis year labels come from actual point timestamps — the old hardcoded `EARLY '24` / `LATE '24` placeholders are gone.
- **Single-page stargazer granularity.** Repos with ≤30 stars now render with individual stargazer timestamps instead of collapsed samples, so early-stage projects produce visible curves instead of flat lines.
- **Adaptive strip metric cell pitch.** Strip cells size themselves to fit the widest metric, then propagate that pitch uniformly. Long values no longer overflow; the grid stays balanced.

### Fixed

- **Live state now reflects live data.** Badges, strips, and live routes across HTTP, CLI, and MCP auto-detect pass/fail/warning/critical state from fetched values. Previously this inference ran only inside `hw kit readme`, so a live badge fetching `build=failing` rendered as green ("active") instead of red. Explicit overrides (`?state=passing`, `--state failing`, MCP `state` argument) continue to win.
- **Generated SVGs advertised the wrong version in their embedded metadata.** The `version` variable that feeds `<hw:artifact version="...">`, `<hw:generator>`, `<hw:genome>`, and `<dc:creator>` was never populated, so every SVG from v0.2.0–v0.2.3 declared itself as `0.1.0` regardless of installed version. The metadata now reflects the real release.
- **Stats card activity bars blurred on mobile.** Bars now render with a solid fill and pixel-crisp edges rather than a multi-stop vertical gradient. The icy highlight lives in the horizon shelf-glow above the bars, so small-viewport rendering stays sharp.
- **Strip chrome typography drifted from badge.** Chrome strip metric values render in Orbitron 17px upright, matching the chrome badge — replacing the previous Impact-italic treatment. Chrome strip and chrome badge now share one typographic system.
- **Strip chrome filter stack caused mobile blur.** Removed specular lighting and the text-shadow filter, both of which rasterized poorly on small frames. Replaced the sheen with vector hairlines so highlights stay pixel-perfect at every size.
- **Chart axis labels no longer hardcoded.** Both brutalist and chrome chart templates read axis labels from the chart engine; changing the data range updates the labels automatically.
- **User-Agent header reported the wrong version.** Outbound HTTP requests identify as the installed HyperWeave version rather than a stale `0.1.0`.

### Changed

- **Chart resolver is a three-state machine.** `stale` (fetch failed), `empty` (zero-value repo), or `fresh` (real data). The previous behavior of synthesizing a placeholder curve on failure is removed — data truthfulness is now a rendering contract.
- **Strip skew is profile-declared.** The hardcoded italic skew on chrome strips has been removed; profiles that want a skew opt in explicitly via a profile field.

### Known follow-ups (not blocking v0.2.4)

- **Chart hero strip placeholders.** The static repo slug and date-range label on charts are not yet data-driven; only the curve and axes are.
- **Chart/stats data-provenance states lack dedicated styling.** Charts with failed fetches render a `stale` status, but no CSS rule matches it — the visual is covered by the text overlay rather than a distinct chrome color. Same for `empty`.
- **`loop` artifact status is declared but unused.** The status enum includes `loop`, exposed via MCP schema, but no inference logic produces it and no CSS animation exists for it.

## [0.2.3] - 2026-04-13

### Added

- **Genome-level `text_metrics` field.** Genomes can now declare per-zone text width multipliers (`badge_label_width_factor`, `badge_value_width_factor`) so the resolver sizes frames correctly for non-default display fonts. Defaults preserve pre-v0.2.3 behavior; new fonts (e.g. Orbitron on chrome-horizon) opt in without touching the resolver. Extensible to future zones without a schema change.
- chrome-horizon ships `badge_value_width_factor = 1.35` to match Orbitron 900 glyph advances at the compositor badge scale.

### Fixed

- **Orbitron was not actually loading on badges and strips.** The v0.2.0 font bundler emits `@font-face` via a `{{ font_faces | safe }}` Jinja variable, but that variable was only rendered in `stats/chrome-defs.j2` and `chart/chrome-defs.j2` — badge and strip chrome-defs templates omitted it. As a result, v0.2.1's switch to `var(--dna-font-display)` fell through to the system-ui fallback instead of rendering Orbitron. `{{ font_faces | safe }}` is now emitted in `badge/chrome-defs.j2` and `strip/chrome-defs.j2` so the bundled WOFF2 actually loads.
- **chrome-horizon badge typography overflow.** Compounded by the font-loading bug above, v0.2.1's badge font sizes (11/17 label/value) matched the magazine's 200x52 showcase badge but the compositor badge is 125x22 (~40% of magazine scale). Scaled to 8/11 and combined with the new `text_metrics` width factor so the value text and status diamond no longer collide.
- **Activity bar vector halos produced visible "fat bar" artifacts on mobile.** The v0.2.1 fix replaced `feGaussianBlur` with 2-layer sibling-rect halos, but those expanded the visual width of each 7px bar by 4px total, which read as blurry on small viewports. The magazine specimen's light-cyan top highlight is carried by the `ch-bar` gradient's first stop (#C8DAE6) alone, not by any halo — so the halos are removed entirely. Bars render as crisp gradient rects at every scale.
- `tier2/` added to ruff `extend-exclude` so `just fmt` no longer trips on internal research files.

## [0.2.2] - 2026-04-13

### Fixed

- **CI test job** was red on the v0.2.1 push because `tests/test_proofset.py` imports `scripts/generate_proofset.py`, but `scripts/` was excluded from version control by `.gitignore`. The three test runners saw `FileNotFoundError: No such file or directory: scripts/generate_proofset.py`. `scripts/` is now tracked (it is a dev-tools directory, not a runtime dependency, and remains excluded from the PyPI wheel by `[tool.hatch.build.targets.wheel].packages`).

## [0.2.1] - 2026-04-13

Post-v0.2.0 stabilization: typography alignment, mobile rendering fix, and a streak computation correction.

### Fixed

- **Stats card "streak" reports 0d for active contributors.** The contribution-calendar parser walked backwards from the latest cell and broke on the first zero, which is always today's empty cell before the user has committed. The streak calculator now treats the most-recent cell as a single grace day — if today hasn't happened yet, the streak continues from yesterday. Any zero day after the first one still breaks the streak as before.
- **Activity bars blur on mobile.** The `barglow` filter on the stats card's 52-week activity bars used `feGaussianBlur`, which rasterizes to a pixel buffer and gets downsampled when the SVG is scaled to smaller mobile viewports — producing soft, fuzzy bars. Replaced with a pure-vector 2-layer halo (sibling rects at decreasing opacity). Same cyan halo aesthetic from the chrome-horizon magazine specimen, but crisp at every scale. The `{uid}-barglow` filter definition was removed from `stats/chrome-defs.j2`.
- **chrome-horizon badge and strip typography** now match the stats and chart cards introduced in v0.2.0. Badge values render in Orbitron (the bundled display font) instead of the prior Impact+skew treatment; strip metric values keep the shields.io-style Impact+skew but gain the silver `ct-hero` gradient fill, tying them visually to the hero numbers on the stats and chart frames. Identity and metric labels render in JetBrains Mono at the sizes and letter-spacing used by the chrome-horizon magazine specimen.
- Badge and strip chrome templates migrated to the same class-based `<style>` pattern stats and chart already use (`.{uid}-label`, `.{uid}-value`, `.{uid}-identity`, `.{uid}-metric-label`, `.{uid}-metric-value`). Inline `font-family` / `font-size` / `font-weight` attributes removed from `strip.svg.j2`, `badge/chrome-content.j2`, and replaced with class references defined in each paradigm's `*-defs.j2` file. This is chrome-paradigm-only — brutalist-emerald output is unchanged.
- Applied `ruff format` to three files added in v0.2.0 (`config/genome_validator.py`, `connectors/github.py`, `render/chart_engine.py`). No behavior change — CI's `ruff format --check` job runs separately from `ruff check` and was the only thing red on the v0.2.0 push.

## [0.2.0] - 2026-04-12

Live-data profile artifacts. HyperWeave can now render GitHub profile cards, star-history charts, and milestone timelines directly from a single API call, the CLI, or an MCP tool. Genomes gain a per-frame paradigm layer so two genomes on the same profile can diverge structurally, not just chromatically. Custom genomes can be loaded from a local JSON file and validated against a profile contract. Fonts are bundled as base64 WOFF2 for fully self-contained SVGs. Test suite: 435 passing.

### Added

**Three new frame types**
- `stats` — GitHub profile summary with language breakdown, commit streak, pull requests, issues, contribution heatmap, and top repositories. Live data via the GitHub API.
- `chart` — star-history time series with polyline, area fill, and milestone markers. Sampled from the GitHub stargazers endpoint (12 evenly-spaced pages with cumulative reconstruction from `starred_at` timestamps).
- `timeline` — vertical milestone chain with per-node opacity cascade and dash-flow spine animation.

**Custom genome support**
- `hyperweave compose --genome-file ./my-genome.json` loads an arbitrary genome from disk and validates it against the declared profile's contract before composing. Required `--dna-*` fields and WCAG AA contrast pairs are enforced.
- `hyperweave validate-genome ./my-genome.json` validates without composing. Useful in CI.
- `genome_override` parameter on the MCP `hw_compose` tool and the HTTP compose body accept an inline genome dict (same effect as the CLI flag).
- Profile contract schemas ship alongside the profiles: `data/profiles/brutalist.contract.json` and `chrome.contract.json`.

**Paradigm dispatch**
- Each genome now declares a `paradigms` dict mapping frame type to a template variant (`default`, `brutalist`, `chrome`, or custom). Templates resolve to `frames/{type}/{paradigm}-content.j2`.
- `default` partials added for badge, banner, icon, and strip so new genomes can ship without per-profile template work.
- Two genomes on the same profile can now produce structurally different output from identical data (e.g., brutalist-emerald's stats card uses square markers and angular grids; chrome-horizon's uses diamond markers and beveled envelopes).

**Font bundling**
- JetBrains Mono and Orbitron are bundled as base64 WOFF2 with accompanying metadata. Genomes declare which fonts to embed via a `fonts` JSON field, and `@font-face` declarations are generated automatically.
- Artifacts remain fully self-contained — no external font requests.

**GitHub connector expansion**
- `fetch_user_stats(username)` — composite profile fetch: repos, commits, stars, language breakdown, contribution streak, pull request and issue counts.
- `fetch_stargazer_history(owner, repo)` — sampled star history suitable for chart rendering. 12 evenly distributed pages with the `application/vnd.github.v3.star+json` accept header.
- Contribution calendar HTML scraping (`github.com` added to the connector host allowlist; usernames are regex-sanitized before URL interpolation).
- 1-hour cache TTL on both user-stats and stargazer-history results.

**CLI**
- `hyperweave compose stats <username>` — fetches profile data and renders the stats card.
- `hyperweave compose chart stars <owner/repo>` — fetches star history and renders the chart.
- `hyperweave compose timeline --data ./items.json` — renders a timeline from a JSON file of milestone items.
- `hyperweave compose <frame> --genome-file ./genome.json` — compose any frame type with a custom genome.
- `hyperweave validate-genome <path>` — validate a genome file against its profile contract.
- `hyperweave mcp` — start the MCP server (previously only available via `python -m hyperweave.mcp`).
- Connector failures downgrade gracefully: stats/chart runs emit a stderr warning and still produce an SVG marked `data-hw-status="stale"`.

**HTTP API**
- `GET /v1/stats/{username}/{genome}.{motion}` — profile card with connector data fetched server-side. 1-hour cache.
- `GET /v1/chart/stars/{owner}/{repo}/{genome}.{motion}` — star-history chart. 1-hour cache.
- `POST /v1/timeline/{genome}.{motion}` — timeline from a JSON body of the form `{"items": [...]}`.
- All three routes degrade gracefully: a connector fetch failure produces a stale-marked SVG rather than a 5xx.

**MCP**
- `hw_compose` gains `stats_username`, `chart_owner`, `chart_repo`, `connector_data`, `timeline_items`, and `genome_override` parameters.
- Network I/O is intentionally excluded from the MCP tool — agents must pre-fetch via `hw_live` or a connector call and pass results through `connector_data`. This preserves pure-function, deterministic semantics for agent workflows.

**Telemetry**
- Model pricing externalized to `data/telemetry/model-pricing.yaml`. Rates for every current Claude model are bundled (Opus 4.5 and 4.6 at $5/$25, Sonnet 4.5 and 4.6 at $3/$15, Haiku 4.5 at $1/$5) alongside preserved legacy entries. Cache read/write multipliers are configurable.
- Session contract now includes `project_path` alongside the existing `model` and `git_branch` fields, so receipts reflect where the work happened.
- Internal `telemetry-void` palette ships for the telemetry frames (receipt, rhythm-strip, master-card), which remain genome-independent.

**Chart rendering engine**
- A shared rendering kernel (`render/chart_engine.py`) produces polyline, area, marker, gridline, and milestone fragments from a viewport and a list of data points. Used by the standalone `chart` frame and embedded inside the `stats` frame's chrome paradigm.
- Pure-function: no CSS, no network, no f-string SVG. Callers pass colors as `var(--dna-*)` references.

**Proof set**
- `scripts/generate_proofset.py` grows to 80 static artifacts (was 74) with a new section producing stats, chart, and timeline samples per genome.
- Live fetch against `eli64s` / `eli64s/readme-ai` with a mock-data fallback when the network is unavailable or rate-limited.

### Changed

- `FrameType` enum grows to 15 members (was 12) — adds `STATS`, `CHART`, `TIMELINE`.
- Template tree reorganized: every paradigm-dispatched frame type has its own `templates/frames/{type}/` directory with `{paradigm}-content.j2` and `{paradigm}-defs.j2` partials.
- Genome JSON schema formally documents the `paradigms` dict, the `structural` block (`data_point_shape`, `data_point_size`, `data_layout`, `fill_density`, `stroke_linejoin`, `shape_rendering`), the `fonts` list, and the `typography` block.
- Profile schema gains `strip_divider_color` and `strip_divider_opacity` parametric knobs.
- `ComposeSpec.genome_id` is typed as `str` (was `GenomeId`) to accept custom genomes loaded via `--genome-file`. `GenomeId` is still a StrEnum, so existing `spec.genome_id == GenomeId.BRUTALIST_EMERALD` comparisons continue to work unchanged.
- `ArtifactMetadata.genome` is typed as `str` for the same reason.
- MCP server and HTTP app `version` metadata now read from `hyperweave.__version__` instead of a hardcoded string — version reporting stays in sync with the git tag automatically.
- Connector base `fetch_text` now defaults to `Accept: text/html` and accepts caller-supplied headers (was XML-only).

### Fixed

- **Session metadata parser** — receipts now correctly capture `sessionId`, `cwd`, and `gitBranch` when they appear on different transcript lines. Previously, sessions where the permission-mode line appeared before the first user message produced receipts with empty `project_path` and `git_branch`.
- **Model pricing** — Opus 4 token costs corrected from $15 / $75 to $5 / $25 per million tokens. Receipts generated for Opus 4.5 and 4.6 sessions now report accurate dollar totals.
- **Receipt and rhythm-strip templates** realigned against the updated parser; committed example artifacts regenerated.
- **Badge and icon partials** — brutalist and chrome variants realigned after the paradigm-dispatch reorganization.

### Known follow-ups (not blocking v0.2.0)

- Two low-impact version references still hardcode `0.1.0`: the `User-Agent` string in `connectors/base.py` and a `{{ version | default('0.1.0') }}` fallback in `templates/components/metadata.svg.j2`. The fallback only surfaces if a frame renders without the runtime-provided version, which does not happen on normal compose paths.
- Older `assets/examples/*/` SVGs (badges, banners, strips, marquees, icons) still carry the pre-v0.1.3 `hyperweave.dev/hw/v8.0` XML namespace. They are not linked by the current README and render fine as-is; regenerate via `compose()` when convenient.

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
