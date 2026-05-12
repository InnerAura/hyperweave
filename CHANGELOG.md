# Changelog

All notable changes to HyperWeave are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.2] - 2026-05-11

Brutalist gets 12 variants split by substrate: 6 dark monochromes (celadon, carbon, alloy, temper, pigment, ember) and 6 light scholars (archive, signal, pulse, depth, afterimage, primer). Metadata pipeline wires 12 fields that were silently hardcoded. Per-frame reasoning populates `hw:reasoning` from per-genome YAML.

### Added

- Brutalist 12 variants with substrate dispatch (dark | light template routing).
- Per-frame reasoning architecture &mdash; `data/reasoning/{genome}.yaml` loader; brutalist authored, chrome/automata follow.
- `hw:variant` and `hw:stratum` metadata fields.
- Barlow Condensed 700/900 embedded for display typography.
- Semantic chart CSS vars (`--dna-chart-main`, `--dna-chart-highlight`) decouple data color from accent signal across substrates.

### Fixed

- Metadata pipeline: 12 context variables now wired from genome/variant config (version, series, platform, theme, palette, fonts, rhythm, material, form language, contrast, motion compliance).
- Version string reflects current release (was 0.2.4).
- `hw:reasoning` fields populate (were always empty).

### Notes

- Chrome and automata reasoning YAML queued for follow-up.

## [0.3.1] - 2026-05-10

Receipt user-turn count and filenames now reflect actual session content. Voltage receipts always render dark regardless of viewer color scheme. Star chart x-axis labels no longer collide on short-history repos.

### Fixed

- **Receipt user-turn count** &mdash; the footer "N user turns" now reports actual prompt count; slash commands and tool results no longer skew the number.
- **Star chart x-axis labels on short histories** &mdash; "Apr 2026" / "May 2026" no longer overlap on charts spanning under two years. Spacing now accounts for actual label width and drops middle labels when their bounding boxes would touch.

### Changed

- **Receipt filenames are human-readable** &mdash; saved as `{date}_{time}_{session-name}.svg` (was UUID-only). Session name comes from Claude Code's auto-titled session or Codex's thread name; UUID stays in the SVG metadata.
- **Voltage receipts always render dark** &mdash; the light-mode adaptation block is removed; voltage stays dark across all viewers.
- **Codex receipts carry git branch and thread name** &mdash; both are now extracted from Codex transcripts and surfaced in receipt provenance and filenames.

### Notes

- 1067 tests (was 1035).

## [0.3.0] - 2026-05-10

Chrome ships five named variants. Automata ships sixteen tones with a pairing grammar that composes any two into a bifamily strip or divider. Stat cards, star charts, marquees, and icons redesigned. Per-frame font filtering cuts artifact payloads.

### Added

- **Chrome variants** &mdash; horizon, abyssal, lightning, graphite, moth. Each carries its own gradient, glyph tone, text color, and status indicator.
- **Automata 16 tones** &mdash; violet, teal, bone, steel, amber, jade, magenta, cobalt, toxic, solar, abyssal, crimson, sulfur, indigo, burgundy, copper.
- **Pairing grammar** &mdash; `?variant=primary&pair=secondary` composes any two tones into a bifamily strip or divider. Other frame types silently ignore the parameter. Available on CLI, HTTP, and MCP.
- **Redesigned automata stat card, star chart, marquee, and icon** &mdash; contribution heatmap, star history with threshold markers, scrolling marquee, and social icon with living cell grid.

### Changed

- **Chrome glyph dimensions match cellular** &mdash; both paradigms declare `glyph_size: 12`.
- **Star chart threshold labels** &mdash; offset increased so annotations sit clearly above the polyline glow.
- **Per-frame font filtering** &mdash; each frame embeds only the fonts its templates use. Icons and dividers ship font-free.

### Notes

- 1035 tests (was 960).

## [0.2.26] - 2026-05-07

Two follow-ups to v0.2.25's badge state architecture: strip status indicators now color correctly when CI metrics fail, and the snapshot test suite no longer fails on local-vs-CI version differences.

### Fixed

- **Strip status indicator color tracks the most severe CI metric** &mdash; a strip with `BUILD:failing` next to `STARS` and `VERSION` now renders the right-edge diamond red, matching pre-v0.2.25 behavior. The v0.2.25 narrowing inadvertently dropped this for strips because their title is the repo identifier (`HYPERWEAVE`, `readme-ai`), not a state-bearing label. The engine now parses strip metric cells, runs state inference per allowlisted cell (`BUILD`, `COVERAGE`, `LINT`, etc.), and rolls up to the most severe state across them. Pure data strips (no allowlisted cells) stay neutral.
- **Snapshot tests handle local-vs-CI version differences** &mdash; the URL stability suite was treating package version strings as content (`version="0.2.20"` vs `version="0.2.25"` from dynamic git-tag versioning), failing CI when local snapshots were captured at a different version than the runner. Versions in metadata are now normalized for comparison alongside UUIDs and timestamps.

### Notes

- 960 tests (was 955). 5 new tests pin the strip rollup contract across failing / passing / mixed-severity / pure-data / explicit-override cases.

## [0.2.25] - 2026-05-07

Production badges on data-driven URLs (`STARS`, `FORKS`, `VERSION`, `LICENSE`, `PYTHON`) no longer trigger false-alarm status indicators on numeric values. Badge value text now centers correctly for every value length across all genomes.

### Fixed

- **Data badges no longer show false status indicators** &mdash; a `STARS` badge with value `6` rendered an orange warning diamond because the leading digit matched a threshold rule designed for percentages. Indicators now only appear on common build / test / CI / quality / deployment / monitoring titles (`BUILD`, `TESTS`, `CI`, `PIPELINE`, `WORKFLOW`, `COVERAGE`, `LINT`, `DEPLOY`, `RELEASE`, `STATUS`, `HEALTH`, `UPTIME`, etc.) or when explicitly set via `?state=`. Hyphen and underscore variants like `BUILD-STATUS` and `CI_CD` match the same canonical title without separate config entries.
- **Badge value text centers correctly across all genomes** &mdash; values drifted 1&ndash;3px right of true center, with automata badges drifting further than chrome and brutalist. Centering now verified within 0.5px across short percentages, version strings, license slugs, python_requires, and long names.
- **Monospace labels had extra padding on the right** &mdash; width measurement double-counted letter-spacing for mono labels like `BUILD` and `COVERAGE`; labels now match their actual rendered width.
- **Data-only strips drop the status diamond** &mdash; `STARS | FORKS | VERSION` strips render as pure data; mixed strips like `BUILD | STARS` keep the right-edge indicator; `?state=` always overrides.

### Notes

- 955 tests (was 914). Divider and icon URLs render unchanged; existing badge URLs continue to work, with corrected centering and tighter widths where false indicators were removed.

## [0.2.24] - 2026-05-07

Receipts no longer clip past the right edge of the card when one tool dominates the session. Cleanup pass removes an unused template, an unused styling table, and two silent default-position fallbacks in the receipt template.

### Fixed

- **Token map row could overflow the receipt's right edge** &mdash; sessions where a single tool used most of the tokens (for example 95% by one tool, the rest split between two others) made the smallest tool's cell extend past the card's right edge, hiding part of its label. The token map now shrinks cells proportionally when the row would otherwise overflow, with a minimum width that keeps every cell visible as a readable colored block.

### Removed

- **Unused template `templates/components/treemap.svg.j2`** &mdash; orphan from before v0.2.21 with no remaining callers in the rendering pipeline.
- **Unused styling table in `compose/resolver.py`** &mdash; values had drifted from the live source in `treemap.py` and no template read it.
- **Silent default-position fallbacks for the provider and model labels** &mdash; these positions are always computed from the actual rendered text width; missing values now raise a clear template error instead of silently rendering at the legacy hardcoded position.

### Notes

- 914 tests (was 910); 4 new tests cover token-map cell widths under heavy and balanced tool distributions plus the row of small tool cells fitting within the card.
- The row of small tool cells was already safe by construction (8 cells * 90px + 7 gaps * 4px = 748 <= 752); a defensive test now locks that contract.
- ruff + format + mypy --strict green.

## [0.2.23] - 2026-05-06

Multi-runtime tool registry replaces v0.2.22's single empirical `tool-classes.yaml`. Codex receipts ship as the second runtime via spec-driven YAML registries dispatched by JSONL-shape auto-detection.

### Added

- **Codex receipts** &mdash; new `telemetry-codex` skin renders OpenAI Codex sessions on an atmospheric gradient substrate. `codex_parser.py` handles three tool-call shapes: `function_call`, `custom_tool_call`, `web_search_call`.
- **Receipt geometry moves to the compose layer** &mdash; width-aware positioning via `measure_text` LUTs handles hero label x-offset, treemap detail truncation in narrow cells, and footer path truncation when the receipt id would collide with the right-aligned session date. `atmosphere_stops` + `card_inset` on `GenomeSpec` declare optional gradient backdrops.
- **Codex translucent borders** &mdash; card border `rgba(53,70,255,0.20)` and divider stroke `rgba(67,87,246,0.14)` let the atmospheric gradient carry the edge definition.
- **Per-runtime registries at `data/telemetry/runtimes/{claude-code,codex}.yaml`** &mdash; adding a runtime is a YAML drop-in plus parser module; no dispatcher / resolver / classifier edits needed.
- **`parse_transcript_auto` dispatcher in `telemetry/contract.py`** &mdash; sniffs JSONL envelope shape and routes to the matching parser; mutual-exclusion guard prevents a Claude line from sniffing as Codex.
- **`hyperweave install-hook --runtime codex`** &mdash; writes a Stop hook to the Codex hooks config and enables the `codex_hooks` feature flag; per-turn caveat surfaces in CLI help.
- **Claude Code tool registry completed** &mdash; 9 tools previously unmapped (MultiEdit, Agent, ToolSearch, ScheduleWakeup, Cron×3, EnterWorktree, ExitWorktree); MCP tools resolve via `mcp__` prefix pattern.

### Changed

- **Three hardcoded runtime registries deleted** from `compose/resolver.py`: `_PROVIDER_BY_RUNTIME`, `_TOOL_CLASS`, and the runtime-string branch in `_resolve_telemetry_genome`. All routes go through `telemetry.runtimes`.
- **Unknown-tool policy: warn, never silent** &mdash; `parser.py` no longer falls through to `ToolClass.EXPLORE` without an audit trail; the warning surfaces tool name + runtime so the YAML can be patched.
- **`SessionTelemetry.runtime`** is a required field stamped by each parser; `contract._RUNTIME` constant deleted.

### Notes

- 910 tests (was 866); ruff + format + mypy --strict green.

## [0.2.22] - 2026-05-05

Adaptive time-axis tick algorithm replaces v0.2.21's hardcoded two-tier threshold; one helper now drives both labels and grid lines so they can never drift. README "Agent Receipts" swaps body copy for a skin table and reorders the receipt examples.

### Fixed

- **Time-axis label explosion** &mdash; `compute_time_axis_ticks` produced 600+ overlapping labels for multi-day sessions; new adaptive picker keeps the visible major count ≤14 with a 50px label-gap floor.
- **Grid lines absent on short sessions** &mdash; sessions under 5 minutes emitted no grid lines; same adaptive helper now drives `layout_bar_chart`'s grid generator for any positive duration.

### Changed

- **`compute_time_axis_ticks` signature** &mdash; dropped keyword-only `short_session_threshold_m` parameter (encoded the dead two-tier model).
- **Terminal-collision guard widened 35→50px** to match the new label-gap floor.
- **README "Agent Receipts" body** swaps text-only intro for an images-first layout (voltage receipt → voltage rhythm strip → claude-code receipt) followed by a per-agent livery table.

### Notes

- 866 tests (was 855); ruff + format + mypy --strict green.
- 30-minute sessions now get 5-minute granularity; intentional behavior change, surfaces in proofset visual diff.

## [0.2.21] - 2026-05-05

Agent receipts ship as a token-driven compositor frame: three telemetry skins (voltage, claude-code, cream), zero template conditionals, faithful to specimen SVGs. Auto-detects the coding agent's runtime via the JSONL `runtime` field; adding a new skin is a JSON file, not a code change.

### Added

- **Three telemetry skins** with specimen-faithful palettes — voltage (titanium dark + champagne), claude-code (warm paper + terra-coral), cream (risograph + fluoro-orange).
- **`hyperweave install-hook`** — Claude Code `SessionEnd` hook drops a receipt SVG per session; `--genome cream|voltage|claude-code` pins a specific skin.
- **Runtime auto-detection** picks the agent's skin (`claude-code` → claude-code; else voltage); 12 genome tokens for pill / glyph / card-frame, `"transparent"` hides elements without conditionals.
- **Compose modules:** `treemap.py` (3-tier + `+N more` overflow), `bar_chart.py` (opacity stagger 0.78/0.85, BAR_MIN_W=6, 35px time-axis collision guard), `rhythm_strip.py` (v2 4-zone).
- **Active-window duration** — chart uses sum of stage durations; hero shows `"Xm active · Ym total"` when active < 50% of session (sessions left open render honestly).
- **Rhythm header** surfaces `(N SHOWN)` when `merge_consecutive_same_class` compacts stages; `#receipt-card-shape` clipPath rounds substrate + top-accent corners.
- **Provider glyph partial** (claude + codex glyphs from v9 specimens); 26 compliance tests; 5 real transcripts in proofset (small → xxlarge / 109 stages).

### Fixed

- **212% dominant-phase** — denominator self-normalizes against classified time; never exceeds 100%.
- **Provider identity runtime-keyed** (was skin-keyed) — Claude Code glyph appears on voltage receipts when JSONL runtime is `claude-code`, regardless of palette skin.
- **XML-safe model labels** — `<synthetic>` and other angle-bracketed model tokens stripped at the resolver boundary so test transcripts no longer break SVG parsing.

### Changed

- **`{% if skin_mode %}` branches deleted** from `receipt.svg.j2`; all variation through genome tokens; resolver's hardcoded `genome.id == "telemetry-claude-code"` check replaced by token lookup; pill silhouette normalized to `pill_rx=0` across all skins (cross-skin coherence over per-specimen fidelity).
- **Voltage palette re-authored** from titanium specimen (champagne signal + teal/magenta/gold tool palette; was Tailwind indigo/purple inherited from telemetry-void).
- **README "Session Telemetry" → "Agent Receipts"**, repositioned above the genome catalog with three captioned examples.

### Notes

- 855 tests; ruff + format + mypy --strict green; Codex runtime falls through to voltage (dedicated codex skin planned).

## [0.2.20] - 2026-05-02

Hotfix for two v0.2.19 regressions + README subtitle clarity.

### Fixed

- **Marquee bifamily palette lost on data-token marquees.** Resolver still read `chrome_ctx.get("family")` after the v0.2.19 family→variant rename — `bifamily_active` evaluated False and the cellular tspan palette never applied, so automata marquees with `gh:`/`pypi:`/`docker:` data tokens rendered grey instead of teal+amethyst.
- **404 SMPTE error SVG had duplicate `data-hw-variant` attributes** (`rainbow-static` + `universal-fallback`) — XML parsers rejected it. Renamed the second to `data-hw-fallback="universal"`.

### Changed

- **README subtitles reformatted as bullet pairs per artifact** (route pattern + paste-ready URL). Long URLs that wrap stay scannable; readers can copy either line directly.

## [0.2.19] - 2026-05-02

Genome slug renames, chromatic axis rename, and divider namespace split. Frees the `variant` axis name for the universal chromatic chooser and gives genome-agnostic dividers their own URL space.

### Changed

- **Genome slugs:** `chrome-horizon → chrome`, `brutalist-emerald → brutalist`. Hard cut, no aliases.
- **`family` → `variant`** across CLI/HTTP/MCP, paradigm YAML, genome JSON keys, templates, tests.
- **Badge size axis renamed `variant → size`** to free `variant` for the chromatic axis.
- **Path B grammar:** genomes declare `variants: [...]` + `flagship_variant`; resolver enforces the whitelist at resolve-time (422 on violation). Pydantic `_ALLOWED_FAMILIES` deleted.
- **Divider rename:** `cellular-dissolve → dissolve` (slug carries the design name only; genome identifies the paradigm).

### Added

- **`/a/inneraura/dividers/<slug>`** route for genome-agnostic dividers (block, current, takeoff, void, zeropoint).
- **Chrome `band`** (envelope drift, phi3 6.854s) and **brutalist `seam`** (concrete expansion-joint) dividers.
- **Genome-declared `dividers: [...]` whitelist** + slug-interpolation template dispatch (`frames/divider/<genome>-<slug>.svg.j2`).

### Notes

- 681 tests; ruff + format + mypy --strict green.
- `/v1/divider/{variant}` path-param renamed to `{divider_variant}` (avoids collision with new `?variant=` query).

## [0.2.18] - 2026-05-01

Tier 2 of the production reliability rollout (Tier 1 shipped as v0.2.17). Three coupled architectural changes target the remaining first-traffic-after-deploy spike: a singleton `httpx.AsyncClient` with HTTP/2 multiplexing replacing per-request fresh TLS handshakes, a FastAPI lifespan handler that pre-warms the compose pipeline, and a readiness-gating `/health` that returns 503 (not 500) on compose failure so Fly's load balancer holds a freshly-woken machine out of rotation until warmup completes.

### Changed

- **Singleton `httpx.AsyncClient` with HTTP/2 + connection pool** in `connectors/base.py`. Module-level `_client` lazy-initialized via `get_client()`, closed via `close_client()`. `fetch()` and `fetch_graphql()` reuse the singleton instead of `async with httpx.AsyncClient(...)` per call. Pool: `max_keepalive_connections=20`, `max_connections=40`, `keepalive_expiry=30s`. Marquee fan-out (5 tokens / 3 providers) now multiplexes over already-open connections instead of paying 5 fresh TLS handshakes.
- **`pyproject.toml`** dependency: `httpx>=0.28` → `httpx[http2]>=0.28`. Pulls in `h2` / `hpack` / `hyperframe`. `AsyncClient(http2=True)` requires the `h2` package; without it, ImportError at startup.
- **FastAPI lifespan handler** in `serve/app.py`. Calls `get_client()` (eagerly opens HTTP/2 pool) and `compose(_PROBE_SPEC)` (force-loads `compose/engine.py`'s internal lazy imports + Jinja env + font lru_caches). Warmup measured at 0.10s locally — well under the 5s deployability budget.
- **30 lazy hyperweave imports inside async handlers moved to module scope** in `serve/app.py`. The cold-import cliff (Python's GIL-protected import lock serializing first-request imports) is paid once at process startup instead of per-request. The lifespan's warmup compose is what loads the inner lazy imports inside `compose/engine.py`.
- **`/health` exercises the compose pipeline** instead of returning a static dict. Success: `{"status": "ok"}` 200. Failure: `{"status": "degraded"}` **503** — semantically correct for "process up but cannot serve yet" so load balancers retry rather than hard-fail.
- **`_PROBE_SPEC` shared between lifespan and `/health`.** Module-scope constant; `ComposeSpec` validators (`core/models.py:82-97`) are pure (read only `_GENOME_PROFILE_MAP` + `ProfileId` enum) so import-time construction is safe.
- **`tests/conftest.py` autouse fixture** `_reset_singleton_client` calls `close_client()` after every test. pytest-asyncio (`asyncio_mode = "auto"`) creates a fresh loop per test; without the fixture, the singleton from test N is bound to a now-closed loop by test N+1, producing flaky "Event loop is closed" errors.
- **`close_client()` cross-loop tolerance.** Suppresses `RuntimeError` from `aclose()` when the client was bound to a different (closed) loop — sync tests using `asyncio.run()` internally. OS reaps sockets at process exit.

### Fixed

- **7 test mocks in `tests/test_connectors.py`** migrated from `httpx.AsyncClient` patches (with `__aenter__` / `__aexit__`) to `get_client` patches. Mock at the function boundary the test exercises, not the underlying transport.
- **8 `compose` patch targets in `tests/test_serve.py`** updated from `hyperweave.compose.engine.compose` to `hyperweave.serve.app.compose`. Module-scope import binds the function reference at import time; "patch where it's used, not where it's defined."
- **`AsyncIterator` import** moved into a `TYPE_CHECKING` block (used only in the lifespan annotation under `from __future__ import annotations`).

### Notes

- 669 tests pass; net diff +279 / −139 across 8 files.
- Tier 1 (v0.2.17) measured outcomes: `/health` cold TTFB 11.5s → 0.099s (115×); memory 192/256 (75%) → 186/512 (36%); 30-concurrent burst p99 2.08 minutes → 0.17–0.39s (~300×). Tier 2's target is the remaining first-traffic-after-deploy spike (~5s p99 on freshly-deployed images): should drop to sub-second.
- Annotated tags only — v0.2.17 was inadvertently lightweight which broke `git push --follow-tags`. Ship with `git tag -a -m "..."`.

## [0.2.17] - 2026-05-01

Tier 1 of a two-step production reliability rollout (Tier 2 ships as v0.2.18). Config-only changes addressing the README scatter-loading symptom: machine sizing + `auto_stop="suspend"` flip eliminate the wake-from-stop cold-import cliff, concurrency limits gate Fly autoscale before OOM, and a cache TTL split per route role stops Camo from refetching pure-compose artifacts every 5 minutes against a cold origin.

### Fixed

- **`fly.toml auto_stop_machines`: `"stop"` → `"suspend"`.** Wake-from-suspend is ~1–2s vs wake-from-stop ~5–15s; preserves process state across idle so `/health` cold TTFB drops from 11.5s to sub-2s.
- **`fly.toml [[vm]] memory`: `"256mb"` → `"512mb"`.** 192 MiB was sustained at 75% of cap with no burst headroom for the ~80 KB × 30 README-image fan-out — the "Run 2 slower than Run 1" OOM-thrashing signature was directly observed in Grafana.
- **`fly.toml [http_service.concurrency]`: added `soft_limit=20, hard_limit=40`.** App Concurrency peaked at ~33 during README bursts; backpressure prevents the unbounded queue that drove p99 to 2.08 minutes when ~33 concurrent requests hit the throttled CPU slice.
- **`config/settings.py` cache TTL split.** `data_cache_ttl=300` was uniformly applied to pure-compose AND data-bound routes, forcing Camo to refetch static badges every 5 minutes against a cold origin. Three new fields: `compose_cache_ttl=86400` (pure-compose, daily refresh), `data_cache_ttl=300` + `stale-while-revalidate=3600` (data-bound), `error_cache_ttl=5` + `stale-while-revalidate=60` for SMPTE errors (was hardcoded `max-age=60` — 60s sticky errors amplified short outages into minute-long broken-image cascades).
- **`serve/app.py` 8 Cache-Control sites updated.** `_compose_and_respond` now reads `compose_cache_ttl`. Six error-fallback sites consolidated into `_error_response_headers(status_code)` so the TTL is configurable via `HW_ERROR_CACHE_TTL` without source edits.

### Notes

- Diagnosis converged from three independent surfaces: local codebase audit (per-request `httpx.AsyncClient`, 30 lazy handler imports, 5-min static TTL), external probing (Run-2-slower-than-Run-1 OOM signature, /health 11.5s, marquee 12–30s, p99 2.08min), and Fly.io Grafana (memory pinned at 75%, CPU 100% spikes, machine restarts wiping in-process cache, App Concurrency ~33).
- Post-deploy success signal: HTTP Response Times p99 stays under 2 seconds during a README burst (was 2.08 minutes pre-deploy).
- Tier 2 (singleton `httpx.AsyncClient` + lifespan warmup + module-scope imports + readiness-gating `/health`) ships in v0.2.18 to close the remaining first-traffic-after-deploy gap.

## [0.2.16] - 2026-05-01

Chrome icon + chrome/brutalist marquee templates rewritten against production specimens. Chrome icons (circle + square) render at 64×64 with the v2 specimen's 120-unit material discipline preserved (5/6-layer chrome bezel + bevel filter + rim sweep + embedded Orbitron). Chrome and brutalist marquees adopt their specimen dimensions (1040×56 / 720×32), drop the LIVE label panel entirely, and gain a layered render order so scrolling text disappears UNDER perimeter chrome at the edges instead of overlapping it. Marquee scroll loop is now seamless across all paradigms (content-aware repetition + trailing separators); cellular's bullet-text overlap from CSS-var font-measurement drift is fixed at the architectural boundary. Star history reliability hardened with token pinning + GraphQL cross-check against per-token GitHub edge-cache disagreement.

### Added

- **`ParadigmIconConfig.viewbox_w` / `viewbox_h`**: paradigm-driven `viewBox` override on `templates/document.svg.j2`. Chrome icons render the v2 specimen's 120-unit coordinate system at 64px output. Default `0` preserves prior behavior.
- **`ParadigmMarqueeConfig` extended** with width/height, font_*/letter_spacing, separator_kind/separator_size, text_fill_mode/text_fill_gradient_id/text_fill_cycle, and clip_inset_*/clip_rx fields. Defaults match v0.2.15 behavior; chrome and brutalist paradigms declare specimen-derived overrides.
- **Layered render for marquee**: new `{paradigm}-overlay.j2` partials (chrome / brutalist / cellular) render perimeter chrome ABOVE the scroll-track text. Shared template uses `{% include ... ignore missing %}` so paradigms without an overlay opt out without a stub file.
- **`_layout_marquee_items` + `_resolve_font_for_measurement`** helpers in `compose/resolver.py`: per-item absolute x layout via `measure_text` with content-aware item repetition for short content, plus a CSS-var-to-actual-font resolver so paradigms using `var(--dna-font-mono)` defaults measure correctly instead of silently falling back to Inter.
- **Token pinning** (`pin_github_token` + `auth_token` parameter on `fetch`/`fetch_json`/`fetch_graphql`) so multi-request operations like `fetch_stargazer_history` use ONE token across all sub-calls. GraphQL second-source cross-check on `stargazerCount` returns empty-state with verified hero when REST and GraphQL disagree by >2x.
- **`icon_well_top` / `icon_well_bottom`** genome fields for the v2-specific deep-navy radial well in chrome icons. Falls back to `well_top` / `well_bottom` for genomes that don't declare them.
- **Per-shape icon variants in proofset**: chrome-horizon and brutalist-emerald ship `base/icon_circle.svg` + `base/icon_square.svg` alongside the default-shape icon.
- **Metric display label map** (`_METRIC_DISPLAY_LABELS` in `serve/data_tokens.py`): `pull_count → PULLS`, `star_count → STARS`, `pipeline_tag → TASK`, `library_name → LIBRARY`, `python_requires → PYTHON`, `last_updated → UPDATED`. Connector code keeps API field names verbatim; the display layer normalizes them at the marquee/badge render boundary.
- **25 new tests** across `tests/test_marquee_v0_2_16.py` (paradigm-driven dimensions, LIVE-block residue, content-aware scroll, text-fill modes, viewBox override, loop-boundary smoothness) and `tests/test_chart_frame.py` (cross-check disagreement → empty-state, agreement → GraphQL count, token pinning across sub-requests).

### Removed

- **LIVE label panel infrastructure** entirely. `ParadigmMarqueeConfig.suppress_live_block` field, 15 LIVE-block context vars, the LIVE label `<text>` and status diamond `<g>` in chrome/brutalist content templates, and the edge-fade gradient defs. Three new grep gates (`suppress_live_block`, `marquee_label`, `label_panel_width`) added to prevent residue.
- **`_MOCK_CHART_POINTS`** in `scripts/generate_proofset.py`. When chart fetch fails or cross-check disagrees, the artifact is SKIPPED rather than substituted with fake history. README image link breaks loudly — that's the intended signal.
- **Old chrome icon filter** (`{{ uid }}-sh`, basic feDropShadow + clip paths). Replaced by the full bevel filter (`feDropShadow` + `feSpecularLighting` + arithmetic composite) — same chain as marquee/badge/strip.

### Changed

- **Chrome icon templates** (`icon/chrome-content.j2` + `chrome-defs.j2`) full rewrite to match v2 specimens. Five-layer circle (env stroke r=46 + radial well r=42 + dark hairline + rim sweep + bevel); six-layer square (96×96 card + 6px env-rail + top accent + rim sweep). Embedded fonts via `@font-face` data URIs.
- **Chrome marquee templates** (`marquee-horizontal/{chrome-defs,chrome-content,chrome-overlay}.j2`): chrome material stack matching the 1040×56 specimen with embedded Orbitron and a brightened 3-stop chrome-text gradient. Opaque well backing under the env-rail prevents text bleed-through.
- **Brutalist marquee templates**: 720×32 flat slab with rect bullets and `[ink, info]` text-fill cycle. Layered into content + overlay so text scrolls UNDER the accent bar.
- **`templates/document.svg.j2`**: root SVG includes `shape-rendering="geometricPrecision"` and uses the paradigm `viewBox` override.
- **`marquee-horizontal.svg.j2`** rewritten around absolute-x scroll items. Set-A and Set-B sibling groups under one SMIL `animateTransform`; Set-B at `translate(scroll_distance, 0)` for seamless wrap. Branches on `separator_kind` for glyph vs rect (structural data dispatch — Invariant 12 compliant).
- **Genome JSON paradigms maps**: chrome-horizon and brutalist-emerald add `"marquee-horizontal"` routing entries.

### Fixed

- **Marquee scroll loop boundary** matches inter-item rhythm exactly. Trailing separator after every item + `scroll_distance = R × single_period` (with `R = ceil(viewport / single_period)` for short content) eliminates the perceptible "lag" at every cycle.
- **Bullet-text overlap in cellular marquee**: `measure_text` was silently falling back to Inter while the rendered SVG used JetBrains Mono via CSS var, causing ~20-30% width drift. The new `_resolve_font_for_measurement` helper resolves CSS var() to the genome's actual font at the layout boundary.
- **Wrong star history in chart artifacts** (e.g. 400 stars instead of 2,894): per-token GitHub edge-cache disagreement when `fetch_stargazer_history`'s sub-calls landed on different rotated tokens. Token pinning + GraphQL cross-check eliminate this; when sources disagree, chart shows verified hero with HISTORY UNAVAILABLE; when they agree, GraphQL count is trusted and REST sampling proceeds normally.
- **Marquee text rendering ON TOP of perimeter chrome** at the frame edges. Layered render order (background → text → overlay) plus per-paradigm `clip_inset_*` insets eliminate it for all three paradigms.

### Notes

- 669 tests pass (was 644 pre-v0.2.16). Net diff: +1,778 / −451 across 29 files.
- Chrome icon at 64×64 with `viewBox="0 0 120 120"` is a uniform-scale presentation of the v1 (120×120) specimen — coordinate system preserved. Subpixel hairlines (0.6-unit → 0.32px rendered) anti-alias as fine machined edges thanks to `shape-rendering: geometricPrecision`. If 64-native tuning is later required it ships as v3.
- Marquee `text_fill_cycle` mode hardcodes `["#D1FAE5", "#34D399"]` in brutalist.yaml because brutalist-emerald is currently the only genome opting into brutalist paradigm. If a second genome adopts brutalist later, this should migrate to a "genome-field-name" indirection per Invariant 11.
- Genome-design rules from this iteration are logged separately in `tier2/_genome_feedback_log.md` (rules 57-59).

## [0.2.15] - 2026-04-30

Marquee data-token rendering + badge data-route bug fix + README live-data dogfood. The unified `?data=` grammar shipped in v0.2.14 was technically working but visually flat: marquee-horizontal flattened structured `(label, value)` token pairs into a single combined string before reaching the template, so `gh:repo.stars` rendered as one uniform `"STARS 1234"` instead of label-muted-value-bright. This release plumbs the structured fields through the resolver into the template's two-tspan rendering so kv/live tokens display the way the spec always intended. The badge data-route had a separate bug (renders `"VERSION:0.2.14"` instead of `"0.2.14"`) caused by routing through the multi-cell strip formatter; that's fixed too.

### Added

- **`format_for_badge(tokens) -> str`** in `src/hyperweave/serve/data_tokens.py`. Returns the first resolved token's value with no label prefix, so badges (single-value slot, title in path) get the raw value while strip continues to use `format_for_value` for its multi-cell `LABEL:VALUE` pair shape. Three formatters now exist as peers — one per consumer shape (badge / strip / marquee). Added to `__all__`.
- **Two-tspan marquee rendering for kv/live tokens.** `_resolve_horizontal` now preserves the structured `role` / `label` / `value` fields from `format_for_marquee` (was: discarded after extracting the pre-flattened `text` field). Each scroll item carries optional `label` + `label_color` alongside the existing `text` + `color` + `font_weight`. Template branches on `item.label`: empty → single tspan (text-role, legacy behavior), non-empty → two sibling tspans (label muted in `var(--dna-ink-muted)`, value bright in primary ink, separated by `dx="6"`). Bifamily palette dispatch retained.
- **Multi-provider data marquee in `outputs/README.md`.** New `_generate_multi_provider_marquee()` in `scripts/generate_proofset.py` renders the same five-token URL (`?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,pypi:readmeai.version,pypi:readmeai.downloads,docker:zeroxeli/readme-ai.pull_count`) across all three genomes. README inlines them next to each genome's custom-text marquee under `### Base Frames` so the genome-vs-data axis is visible side-by-side: same tokens, three paradigm skins.
- **Five new unit tests** in `tests/test_data_tokens.py` covering `format_for_badge`: live-token returns value-only with regression-guard against the `"VERSION:0.2.14"` shape, kv-token returns value-only, text-token returns payload, multi-token first-wins, empty input returns empty string. Existing `test_badge_data_route_resolves_live_token` upgraded to capture the `ComposeSpec` passed to `compose()` and assert `spec.value == "12345"` (raw value), not `"STARS:12345"`.

### Fixed

- **Badge data-route renders `"VERSION:0.2.14"` when it should render `"0.2.14"`.** `compose_badge_data_url` was calling `_resolve_data_param` which uses `format_for_value` (correct for strip's multi-cell layout: `"K1:V1,K2:V2"`), but badge has a single value slot — title is in the path, value is the rendered string after the title. The label prefix was leaking. Route now calls `parse_data_tokens` + `resolve_data_tokens` + `format_for_badge` directly, bypassing `_resolve_data_param`. Strip's call site is unchanged.
- **README cellular-dissolve broken-image links.** `generate_readme()` iterated `DividerVariant` and emitted image references unconditionally, while `generate_static()` (the loop that actually writes the SVGs) skipped `CELLULAR_DISSOLVE` for non-automata genomes. Result: brutalist-emerald and chrome-horizon README sections referenced files that didn't exist on disk. README generator now mirrors the static-generator's filter.

### Changed

- **`README.md` marquee URLs** in all three genome sections updated to use the live multi-provider data tokens (`?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,pypi:readmeai.version,pypi:readmeai.downloads,docker:zeroxeli/readme-ai.pull_count`). Replaces the previous static raw-text demo (`HYPERWEAVE | LIVING ARTIFACTS | INNERAURA LABS`). Three providers, five tokens, one URL — dogfoods the `?data=` grammar's composability claim. Subtitles updated to match.
- **`outputs/README.md` Live Data section** consolidated. The bottom-of-page Multi-Provider Data Marquee subsection (with one image per genome) was removed because each genome's `### Base Frames` now contains both the custom-text marquee and the data-token marquee inline. The bottom Live Data section is now a single descriptive paragraph pointing readers at the inline placements.
- **`scripts/generate_proofset.py`** + 83 LOC for the multi-provider marquee generator + README inline emission + cellular-dissolve filter mirror.

### Notes

- Net diff: +271 / -49 across 8 files. Inverse rhythm to v0.2.14's massive deletion: this release is depth-on-the-survivors. Same surface area, more polish per surface.
- The bug class `format_for_value` was serving (one formatter, two consumer shapes) is closed by the new `format_for_badge` peer. Three explicit formatters — one per consumer shape (badge single-value, strip multi-cell, marquee scroll-items) — replace the prior overload. Adding a fourth consumer (e.g., a sparkline frame needing array values) becomes a one-function addition with no callers to refactor.
- Docker Hub's connector exposes `pull_count` (matching the upstream API field exactly), not `pulls`. The proofset's multi-provider marquee data string and the README documentation use the correct metric name. PYPI's `pypistats.org` rate-limits aggressive fetches with HTTP 429 — failed live tokens degrade to `value="--"` per `resolve_data_tokens`'s contract; partial-failure rendering is itself part of the demo.

## [0.2.14] - 2026-04-30

Frame deletion + URL-grammar consolidation. Four frame types come out of the surface (banner, marquee-counter, marquee-vertical, timeline) along with the nine kinetic typography motions that only banners used. In their place: a single unified data-token grammar (`?data=` on HTTP, `--data` on CLI, `data=` on MCP) replaces the patchwork of `?live=` / `/v1/live/...` / per-frame ad-hoc inputs that had accumulated across data-bearing artifacts.

### Removed

- **Banner frame.** Templates (`templates/frames/banner.svg.j2` + paradigm partials), resolver (`resolve_banner`), context builder (`_ctx_banner`), `ParadigmBannerConfig`, `banner_height` profile field, kit composer banner block, MCP `hw_compose` banner mention, banner section in all four paradigm YAMLs, banner key in genome JSONs' `paradigms` map, banner-specific test cases. Banner returns when AI custom genome generation ships with the InnerAura golden-200 dataset for UI inspiration.
- **Marquee-counter and marquee-vertical frames.** Templates (`templates/frames/marquee-counter*`, `templates/frames/marquee-vertical*`), resolvers (`_resolve_counter` ~262 LOC, `_resolve_vertical` ~78 LOC), helper functions (`_parse_counter_metrics`, `_build_counter_status_items`, `_build_vertical_rows`), counter / vertical profile fields, `marquee_rows` ComposeSpec field, the HTTP route's subtype-by-query-param dispatch (`?rows=` / `?direction=up`). Marquee-horizontal is now the single marquee frame.
- **Timeline frame.** Template (`templates/frames/timeline*`), resolver (`compose/resolvers/timeline.py`), context builder (`_ctx_timeline`), `TimelineRequest` Pydantic model, `compose_timeline` HTTP route (POST `/v1/timeline/...`), `timeline_items` ComposeSpec field + matching MCP/CLI parameters, proofset timeline generation, `_MOCK_TIMELINE_ITEMS`. Timeline returns when there's an actual data source feeding milestones.
- **Nine kinetic typography motions** (drop, cascade, breach, pulse, converge, crash, collapse, bars, broadcast). Templates (`templates/motions/kinetic/`), data configs (`data/motions/kinetic/`), Python builder (`build_kinetic_motion_svg`), `_KINETIC_TEMPLATES` frozenset, `KineticMotionId` enum class, `_build_per_letter_layers`, motion-injection branch in `_ctx*` infrastructure. Border motion YAMLs no longer list `banner` in `applies_to`.
- **Legacy `/v1/live/{provider}/{identifier:path}/{metric}/{genome}.{motion}` HTTP route.** Replaced by the new 2-segment data-driven badge route (`/v1/badge/{title}/{genome}.{motion}?data=...`) plus the unified `?data=` grammar on every other data-bearing frame.
- **Legacy `?live=` query parameter on `/v1/strip/...`.** Replaced by `?data=` with the same fan-out semantics.

### Added

- **Unified data-token grammar** (`src/hyperweave/serve/data_tokens.py`). Comma-separated DSL with three token kinds: `text:STRING` (raw display text), `kv:KEY=VALUE` (static literal, role-tagged), and `<provider>:<identifier>.<metric>` (live token resolved via `connectors.fetch_metric`). Providers: `gh` / `github` / `pypi` / `npm` / `hf` / `huggingface` / `arxiv` / `docker`. Embedded commas in text/kv payloads escape as `\,`; embedded backslashes as `\\`. The escape rule is positional and survives URL decoding (URL-encoding the comma as `%2C` does not work because URL decoding happens before the parser runs). Identifier-with-dots (e.g. `arxiv:2310.06825.citations`) parses correctly because the parser splits on the *last* dot.
- **`?data=` HTTP query parameter on badge / strip / marquee routes.** Replaces `?live=` on strip; new on badge (via the 2-segment data-driven route shape) and marquee. Failed live fetches degrade to `value="--"` with a 60s TTL; successful fetches use the connector's reported TTL with `stale-while-revalidate` headers. Malformed `?data=` returns the SMPTE error SVG with HTTP 200 + `X-HW-Error-Code: 400` (so Camo proxies the response — same pattern as v0.2.12 fallbacks).
- **New 2-segment data-driven badge route** (`/v1/badge/{title}/{genome}.{motion}?data=...`). Coexists with the existing 3-segment static route (`/v1/badge/{title}/{value}/{genome}.{motion}`) — FastAPI routes by path-segment count, so the two are unambiguous. Avoids requiring a throwaway placeholder in the path when the value comes from `?data=`.
- **`--data` CLI option and `data=` MCP parameter.** Same token grammar across all three transports. `hw_live` MCP tool kept as a discoverable shortcut (delegates to `hw_compose` with the equivalent `data=` payload).
- **`data_tokens` field on `ComposeSpec`** (`list[Any] | None`). Populated by the transport layer (HTTP / CLI / MCP) before `compose()` runs. Marquee-horizontal's resolver consumes this list directly to drive scroll items; other frames receive the formatted `"K1:V1,K2:V2"` string via `spec.value`.
- **Marquee-horizontal data-token mode.** `_resolve_horizontal` now accepts either pipe-split title text (existing contract) or resolved data tokens — text tokens render their payload, kv/live tokens render `"LABEL VALUE"`. Cellular bifamily palette alternation applies uniformly across both modes.
- **`tests/test_data_tokens.py`** — 26 unit tests covering single/multi-token parsing, comma-escape rules (with backslash-escape coverage), failure modes (unknown provider, malformed kv, missing dot, trailing backslash), and async resolution semantics (concurrent fetch, failure degradation, min-TTL aggregation).

### Changed

- **`KineticMotionId` enum removed; `MotionId` collapses to `STATIC | BorderMotionId`.** The remaining motion vocabulary is six primitives: static + 5 border SMIL (chromatic-pulse, corner-trace, dual-orbit, entanglement, rimrun).
- **`hw_compose` MCP tool** parameters reshaped: dropped `rows`, `timeline_items`; added `data: str = ""`. Docstring rewritten around the data-token grammar; `hw://schema` URL-grammar resource updated to advertise both badge route shapes plus the data-bearing frames.
- **`/v1/frames` discovery endpoint** lists 11 frame categories (badge, strip, icon, divider, marquee-horizontal, stats, chart, plus the four telemetry frames via POST `/v1/compose`); banner / marquee-counter / marquee-vertical / timeline are gone.
- **README and `CLAUDE.md` documentation** scrubbed of banner / marquee-counter / marquee-vertical / timeline references; URL examples updated to the `?data=` grammar; frame-type and motion-type counts updated.

### Notes

- Historical CHANGELOG entries (v0.2.0 release notes mentioning timeline / banner) are intentionally preserved — they document past behavior, not current capabilities.
- The CLI `--data` flag (previously a JSON-file path used only by the timeline command) is now repurposed for the data-token grammar. The transition is clean because the timeline branch was the only consumer of the old meaning, and it's also gone in this release.
- Net change: ~600 LOC deleted across templates / Python / YAML; ~280 LOC added (parser + tests + per-frame integration). Files touched: 70+. The deletion footprint exceeds additions despite the new grammar layer.

## [0.2.13] - 2026-04-29

Hotfix for a cascade bug exposed by v0.2.12. v0.2.12 changed the SMPTE error fallback's HTTP envelope from 4xx to 200 so GitHub Camo would proxy the body — but the body itself contained an HTML entity (`&middot;` in the `<title>` element) that strict XML/SVG parsers reject. While the server returned valid bytes, *every* SVG renderer (browsers, markdown previewers, image proxies) refused to construct a DOM and fell back to broken-image. The bug was hidden by v0.2.11's 4xx envelope (renderers never tried to parse 4xx responses) and surfaced only after v0.2.12 made the body reachable.

### Fixed

- **SMPTE error fallback now parses as valid XML.** `templates/error-badge.svg.j2` line 40 had `<title>NO SIGNAL &middot; ERR_NNN</title>`. SVG is XML, not HTML — only the five XML predefined entities (`&amp; &lt; &gt; &quot; &apos;`) are recognized. `&middot;` is an HTML extension that triggers `Entity 'middot' not defined` in any conforming XML parser, which causes the renderer to abandon DOM construction and show the broken-image icon. Replaced with the literal Unicode character `·` (U+00B7) — same glyph, no entity-resolution required. Verified end-to-end: `xml.etree.ElementTree.fromstring(_error_badge("test", 404))` now succeeds; `open` of the rendered SVG file shows the SMPTE bars in macOS Preview and Chrome.

### Notes

- **Lesson for future SVG templates.** SVG templates must use literal Unicode characters or numeric entities (`&#xB7;`), never HTML named entities. A grep gate for HTML entities in `templates/**/*.j2` is a candidate Invariant if this class of bug recurs.

## [0.2.12] - 2026-04-28

Post-deploy hotfix for three rendering issues surfaced in live v0.2.11 README artifacts. All three are user-visible regressions that the local proof set did not exercise: the proof set composes through Python directly, bypassing the HTTP surface where two of the bugs lived.

### Fixed

- **Cellular badge label bled into the pattern strip when no glyph was supplied.** `resolve_badge` computed `label_start = accent_w + 6` in the no-glyph branch, ignoring the paradigm's `glyph_left_offset` (cellular: 18) that reserves the left-edge decoration zone for the 3-cell pattern strip. Cellular badges without a glyph rendered the label text overlapping the pattern. The fix applies `glyph_left_offset` uniformly across both glyph and no-glyph branches: `label_start = accent_w + 6 + glyph_left_offset` when `has_glyph=False`. Brutalist and chrome are unaffected — their `glyph_left_offset` is 0, so the arithmetic is identical to the prior behavior. PYPI badge width on automata grew from 96 to 114 to fit the reserved decoration zone.
- **Strip HTTP route had no path to set the `eli64s/readme-ai` subtitle that the cellular strip resolver expected.** `resolve_strip` reads `connector_data.repo_slug` for the subtitle line beneath the identity, but the proofset was the only caller that populated it — the HTTP surface had no equivalent. Added `?subtitle=` query parameter to `/v1/strip/{title}/{genome}.{motion}`; the route builds `connector_data={"repo_slug": subtitle}` when the param is non-empty, and leaves `connector_data=None` otherwise so paradigms that do not opt into subtitles (brutalist, chrome) stay unaffected.
- **Universal SVG error fallback rendered as a broken-image icon in GitHub README despite the server producing a valid SMPTE SVG.** GitHub's Camo image proxy refuses to forward 4xx image responses (security: prevents content-confusion attacks where an image URL secretly returns an HTML error page), so v0.2.11's `status_code=404` envelope killed the fallback at the proxy. All five `_error_badge` call sites in `serve/app.py` now return HTTP 200 with the SMPTE SVG body; the original error class travels in a new `X-HW-Error-Code` response header (`404` / `422` / `500`) and is also embedded in the SVG as `data-hw-status-code` plus the `ERR_NNN` value slab. Programmatic consumers can read either; browsers and Camo proxies render the fallback successfully. Three `tests/test_serve.py` cases that asserted the 4xx HTTP envelope were updated to assert `status_code == 200` plus the `X-HW-Error-Code` header — semantic equivalence preserved, contract clarified.

### Documentation

- **README Genomes section pivoted from 3-column cross-genome table to stacked-per-genome layout.** Each genome now has its own `<h3>` section with a 2-column artifact table (label | image+url-caption); the prior 3-column-per-frame-type table compressed each artifact to ~33% of viewport width, which made the stats cards and star charts unreadable on narrower viewports. The new layout puts each artifact at full available width minus the label gutter, and the genome roster at the top (`<kbd>` chips linking to anchors) gives a fast-jump nav. Comparison table at the bottom is preserved.
- README PYPI badge URLs now include `?glyph=python` so the cellular pattern strip is paired with a glyph rather than crowded against an empty zone. Visually parallels the chrome-horizon and brutalist-emerald BUILD badges.
- README automata strip URL now includes `&subtitle=eli64s/readme-ai` so the rendered strip matches the proofset reference and the cellular paradigm's `show_subtitle: true` declaration.

### Notes

- **Stat/chart card heights differ across genome columns and this is not a regression.** Brutalist `card_height: 280` vs chrome/cellular `260`, and cellular `chart_height: 600` vs brutalist/chrome `500` are paradigm-specimen-correct dimensions declared in `data/paradigms/*.yaml`. The README's three-column table renders them at uniform width via `width="100%"`, so the heights visibly differ. Standardizing the dimensions would crop content on the cellular chart (which uses the bottom 66px for the flank/footer) and the brutalist stats card (which uses the top header strip). Treated as design surface, not a v0.2.12 fix.

## [0.2.11] - 2026-04-28

Adds the third production genome (`automata`) and the cellular paradigm that powers it, hardens the GitHub stats pipeline against silent zeroing under quota exhaustion, and lands a stack of cellular-paradigm rendering fixes.

### Added

- **Third production genome: `automata`.** A bifamily dark-on-dark cellular genome organized around two parallel chromatic families (teal and amethyst). The genome carries per-family rim gradients, pattern-cell trios, seam midpoints, and slab palettes, plus a bridge palette that feeds the static-baked `cellular-dissolve` divider. Adding the genome was a config-only change beyond a single enum entry — no rendering logic in Python.
- **New paradigm: `cellular`.** Per-frame opt-in via the genome's paradigm map: badge, strip, banner, icon, marquee, stats, and chart all dispatch to cellular partials; divider and timeline inherit existing defaults. The paradigm declares its own required genome fields — two family palettes, bridge palette, pulse-duration config, and a five-state palette — so a genome that opts in is forced to supply them or fail validation at load.
- **`ComposeSpec.family` axis.** New orthogonal field for per-composition chromatic choice: `blue`, `purple`, or `bifamily`. Empty resolves to a paradigm default (badges and icons → blue, strips and banners and marquees and dividers → bifamily). Wired through CLI (`--family`), HTTP (`?family=` on every GET route plus POST `/v1/compose`), and MCP (`hw_compose(family=...)`) with feature parity. Non-automata genomes ignore the field.
- **Paradigm-driven conditional zones.** Strip and badge zones — the right-edge status indicator, the bifamily flank columns, and the version-mode indicator allocation — are now declared per paradigm rather than universally reserved. Closes the "strip/badge zones should be conditional, not universal" gap that the cellular layout exposed: paradigm specimens emerge from config, not from hardcoded reservations that every paradigm has to override.
- **Slot-driven metric-state.** Strip metrics can now carry an optional state slot, sourced from the slot data payload or from the compose spec. Backward-compatible with the existing comma-separated value parsing, and the new field stays empty for regular metric zones.
- **`cellular-dissolve` divider variant.** Static-baked bifamily bridge divider (800×28). The dissolve effect comes from per-rect opacity attributes — zero CSS animation, zero `<style>` block — so it survives static-only renderers like Finder Quick Look, VS Code, and email clients.
- **Chakra Petch font LUT.** Weight-700 latin subset from Google Fonts (OFL-1.1), extracted at 12px baseline. Used for automata hero value text in badges and strips.
- **State palette on every genome.** Five passing/warning/critical/building/offline core+bright pairs are now declared on every genome and backfilled across brutalist-emerald, chrome-horizon, and telemetry-void with standard pairings. Safe addition — no pre-existing template consumed the fields, and future state-badge variants can route through them without per-genome edits.
- **Shared state-signal cascade partial.** A single template binding maps `[data-hw-status]` attribute values to phi-timed breathe/pulse/strobe/dim animations. Included by cellular badge defs for state-mode badges and by cellular strip defs for metric-state cells.
- **Connector adaptivity proof.** Three connector-strip variants (GitHub `eli64s/readme-ai`, PyPI `readmeai`, DockerHub `zeroxeli/readme-ai`) demonstrate that strip construction handles varied metric counts, value lengths, and label names consistently when fed live data. Generated for all production genomes and surfaced in the proof-set readme under a "Connector Adaptivity (live)" section per genome.
- **5-metric multi-connector stress test.** A connector-strip spec aggregates GitHub stars, GitHub forks, PyPI version, PyPI downloads, and Docker pulls into a single five-cell strip per genome. The widest plausible label (DOWNLOADS) and a heterogeneous value vocabulary (count, version-string, K-cascade) stress the per-cell adaptive layout. Acts as the regression guard for the centralized cell measurement below.
- **Proof set coverage.** The proof-set generator auto-pulls automata via genome enum iteration plus a `families/` section covering blue/purple × default/compact × version/state badge permutations, the bifamily strip, compact bifamily banner, and `cellular-dissolve` divider. 137 total artifacts (up from 115 at v0.2.10).
- **Universal SVG error fallback.** Every compose-pipeline failure now renders as the SMPTE RP 219 "NO SIGNAL" test pattern instead of a raw error string or a browser broken-image icon. A new `templates/error-badge.svg.j2` produces the chrome-rim-rainbow-bars-NO_SIGNAL-banner-ERR_NNN visual through the same `render_template` path as every composed artifact (Invariant 6 holds: zero f-string SVG). HTTP status maps via `_classify_compose_exception`: `GenomeNotFoundError` → 404, Pydantic `ValidationError` → 422, anything else → 500. The status code is rendered into the value slab (`ERR_404`/`ERR_422`/`ERR_500`) and emitted in the HTTP envelope so README `<img>` tags pointing at broken URLs render as a branded error state rather than a generic missing-image glyph. Each error badge gets a per-message uid prefix on every gradient, filter, clip-path, class, and keyframes name so two failing badges on the same page do not collide on document IDs. Fonts route through the bundled-font pipeline (`load_font_face_css(["chakra-petch", "orbitron"])`) and embed as base64 WOFF2 inside the SVG `<style>` block — no `@import` against `fonts.googleapis.com`, so the artifact renders correctly under the strict CSP that `serve/app.py` already applies (`default-src 'none'; style-src 'unsafe-inline'`) and behind GitHub Camo. Metadata declares `self-contained="true"` and `cim-compliant="paint-ok"` (the `hue-rotate` filter keyframe is paint-tier, honestly classified rather than the original mis-claimed `cim-compliant="true"`). SVG body grows from ~5 KB to ~35 KB; acceptable on the 60-second-cached error path.
- **`GenomeNotFoundError` exception.** A `KeyError` subclass raised by `_load_genome` when a genome slug is not registered. The KeyError lineage preserves backward compatibility for any caller that already writes `except KeyError`; the explicit subclass lets the HTTP layer dispatch a 404 distinctly from a 500. Replaces the previous silent fallback to a default crimson genome — broken URLs now fail loud.

### Changed

- **Strip text and cell-layout measurement is now centralized and paradigm-declared.** Previously the resolver measured labels without letter-spacing while the rendered CSS class applied 0.22em, and values were measured at weight 700 while brutalist and chrome rendered at 900 — long labels (DOWNLOADS, COMMITS) bled past the right divider while short values like `64` crowded into theirs. A single layout function now consumes paradigm-declared font specs (family, size, weight, letter-spacing) and emits per-cell coordinates the template renders verbatim. Adding a paradigm with different alignment is now a YAML-only edit.
- **Strip paradigm config carries the rendered font specs verbatim.** Six new fields — label and value weight, label and value letter-spacing, cell padding, minimum cell width — live in the paradigm YAML and feed the resolver's measurement. The paradigm declarations match the CSS class declarations exactly, so the two can no longer drift silently.
- **Identity and subtitle measurement does its inter-character math once.** A string of N characters has N-1 letter-spacing gaps, not N. The resolver previously over-counted by one character of letter-spacing for identity, subtitle, and metric labels alike. The measurement helper now takes letter-spacing as a kwarg and does the N-1-gap math in one place.

### Fixed

- **GitHub stats no longer reports failed sub-fetches as zeros.** Under search-API quota exhaustion in v0.2.10, sub-fetches for commits, PRs, and issues were silently coerced to zero — indistinguishable from a truly inactive account. Stat cards displayed `COMMITS=0 PRS=0 ISSUES=0` for accounts with thousands of each. The aggregator now tracks which sub-fetches failed, and the stats resolver renders those fields as em dashes (`—`) instead of fake zeros. Failure surfaces visibly instead of masquerading as a real value.
- **Three breaker domains for GitHub traffic.** All GitHub HTTP traffic was previously fronted by a single circuit-breaker, so a search-API quota 403 on the most rate-limited endpoint would trip the same breaker that protects core REST badge/strip/chart endpoints, taking the entire pipeline offline. Traffic is now split into core REST, search REST, and GraphQL breakers, with one circuit each. A grep gate in CLAUDE.md catches any missed migration site so a future caller can't silently land on a fourth dead breaker.
- **Stale stats results expire in 30 seconds when a sub-fetch failed.** User-stats results were cached for an hour regardless of whether sub-fetches succeeded — a transient rate-limit burst froze stale zeros into the cache. Results containing any failed sub-fetch now cache for 30 seconds; the success path keeps the original hour. Transient breaker-trips self-heal in seconds, not an hour.
- **PyPI downloads connector returned 0 for every package.** PyPI removed download counts from its package JSON payload in 2016, so the previous extractor read an always-empty field and reported 0. Downloads now route through `pypistats.org` (the same source the official `pypistats` CLI uses), with that host added to the SSRF allowlist and a separate circuit-breaker so a pypistats outage cannot trip the version/license/python-requires path that still hits `pypi.org`. Empirically, `readmeai` now reads 9,540 downloads/month (was 0); `httpx` reads 627M.
- **Stat card delta annotation now populates.** Production stat cards expect a green `▲ 2,431 /yr` annotation next to the STARS hero count, but the field had been a blank-string placeholder in the resolver. Now derived from year-over-year diff against the most recent stargazer-history sample within 365 days, with a graceful fallback when history is unavailable.
- **Star history charts no longer render with empty bodies.** Connector caches predating v0.2.10 retained empty stargazer histories; the chart engine correctly produced no polyline, area, or markers, leaving only a baseline. Cache key invalidated and a diagnostic log added when normalized history arrives empty so the failure surfaces in telemetry.
- **Cellular metric alignment now matches brutalist and chrome.** Cellular strips were rendering metrics flush-left while the other two paradigms centered them. The override was justified as "matching the v10 specimen," but specimens are visual targets, not behavioral spec — divergence on a paradigm-shared knob is regression, not character. Removed the overrides; all three production paradigms now share the canonical centered-metric anchor grid.
- **Cellular strip dropped its empty 28×28 glyph pocket.** The cellular icon-box was rendering unconditionally — when a strip had no glyph, the slot still drew a dark teal-bordered square in the identity zone, pushing the title ~36px later than the design intended. The strip template now branches three ways (icon-box with glyph, icon-box collapsed, no icon-box at all) and the resolver computes the identity coordinate in lockstep so both ends agree on the same x. Glyphless cellular strips now have title text flush against the accent bar.
- **Metric cell padding is uniform across every cell.** The first cell rendered a 24-pixel gap between its left seam and text while later cells used 12 — invisible until `12.4k` next to `1.2k` showed the `1` sitting noticeably right-shifted from where alignment expected it. Every cell now starts at its left seam with a single paradigm-declared inset providing breathing room; verified empirically by parsing rendered SVG, every metric group's transform x equals its left divider x exactly.
- **Strip first-divider and seams share one coordinate system.** In bifamily cellular strips, the first divider was returned in flank-less coordinates while seam positions were returned flank-shifted — same field, two coordinate systems, divider line slicing through the identity text. Both now report in the same shifted space. Brutalist and chrome strips are unaffected; their flank width is zero.
- **Cellular badge label slab gutter.** The label slab started two pixels past where the pattern cells ended, leaving a visible sliver of dark canvas between pattern and slab. The slab now starts flush with pattern end. The highlight and occlusion strips that intentionally start four pixels later are unchanged.
- **State-badge indicator vertical center moved to the resolver.** The visual-center formula was duplicated in the cellular badge template — every new paradigm would have re-derived it and risked regression. Now computed once at the resolver and consumed verbatim by the template.
- **Cellular marquees fully wired.** Marquee frames originally dispatched on envelope-stops presence rather than paradigm slug interpolation, so the bifamily tspan-alternation pattern wasn't reachable from cellular at the time the genome wiring landed. Marquee paradigm config now carries the per-item color cycle, separator glyph, and live-block suppression directly, and the cellular YAML declares teal/amethyst alternation with diamond separators and no LIVE block. New cellular templates extend the same vocabulary to vertical and counter marquees.

### Notes

- **`paradigm == "cellular"` is forbidden in Python.** All marquee dispatch routes through `paradigm_spec.marquee.*` attribute access; adding bifamily-tspan behavior to a future paradigm requires zero Python edits — only a `marquee:` block in that paradigm's YAML. Invariant 12 holds.
- **Comma-stripping bug discovered while building connector strips.** `_format_count(2896)` returns `"2,896"` (comma-grouped); spec.value uses comma as the metric-list separator (`STARS:2,896,FORKS:182` parsed as four phantom metrics). Connector-strip generator now strips commas from formatted values before feeding them into spec.value. Production strips are unaffected because they consume connector counts directly via slot `data` payload, not via the comma-separated spec.value path.
- **Automata specimens treated as sample compositions, not templates.** Prototype SVGs at `tier2/genomes/cellular-automata/production/` remain archive material — the compositor generates equivalent output algorithmically from arbitrary agent/user input. Strip v10's specific "identity | metric | metric | metric-state | state-indicator" composition is ONE instance; the resolver adapts to 0/1/5/10+ metrics, variable text lengths, optional glyph, conditional state indicator.
- **Rule 30 roadmap-ledger deferred to v1.1.** The `compute_cellular_windows(n, rule, seed, rows_per_window)` helper + `templates/frames/timeline/cellular-content.j2` + `variant=roadmap-ledger` branch are tracked in a separate plan. Risk control: NOTES.md 2026-04-16 observation (dense Rule 30 tableaux read as maze/QR at scale) requires threshold tuning before ship.
- **Family-aware glyph tint deferred.** Inline glyph SVGs currently bake `genome.glyph_inner` regardless of family; purple-family badges still render glyphs in the blue-family tint. Family-aware glyph coloring requires routing through `currentColor` — a v1.1 polish item.

### Dev

- 22 new test files across the release: 11 cellular-paradigm coverage files (`test_genome_automata.py`, `test_compose_family_field.py`, `test_font_metrics_chakra.py`, `test_paradigm_cellular.py`, `test_strip_status_toggle.py`, `test_slot_metric_state.py`, `test_family_default_resolution.py`, `test_badge_cellular.py`, `test_strip_cellular.py`, `test_icon_banner_marquee_cellular.py`, `test_divider_cellular.py`), 9 follow-on cellular regression files (badge/strip/banner/icon/marquee variants), and 2 pypistats coverage tests. Six additional tests in `test_serve.py` cover the universal SVG error fallback: status-code classification (`GenomeNotFoundError` → 404, Pydantic `ValidationError` → 422, generic exception → 500), SMPTE template rendering (NO SIGNAL banner, ERR_NNN value slab, `data-hw-class="error-state"` marker), uid isolation across multiple errors on the same page, and an end-to-end HTTP integration test against an unknown genome slug. Test suite grows from 551 to 636 passing.

## [0.2.10] - 2026-04-20

### Fixed

- **Star history charts are readable at every repo size.** v0.2.8 introduced a GraphQL cursor-offset sampler that constructed `base64("cursor:<N-1>")` anchors to fetch the Nth stargazer at arbitrary offsets. The assumption was that GitHub's stargazer cursors decode to the literal text `cursor:<N>` — they don't. Real cursors are opaque `cursor:v2:<MessagePack binary>` pointers. For most constructed offsets GitHub returned `INVALID_CURSOR_ARGUMENTS`; for a handful it silently returned a recent stargazer instead. The result: charts collapsed into one of three broken shapes — a flat-then-spike (`eli64s/readme-ai`, 2.9K stars), a flat horizontal line at the total (`JuliusBrussee/caveman`, 40K stars), or a single-diagonal with stacked markers at the origin (`openclaw/openclaw`, 361K stars). v0.2.10 removes the broken sampler entirely; REST sampling is now the only path. For the same three repos, charts now show genuine growth curves — the 3-year S-curve for readme-ai, the 16-day viral logistic for caveman, and the first-40K detail + now-point for openclaw (bounded by GitHub's 400-page REST cap, which `star-history.com` also hits).
- **Milestone label stacking is gone as a side-effect of the above.** The v0.2.8 milestone x-gap de-overlap was functioning correctly all along; what the user saw as stacked markers were the *data-point markers* themselves, clustering at a single x because the broken GraphQL sampler returned the same timestamp for many offsets. Genuine sampling distributes markers naturally.

### Removed

- `_fetch_stargazer_history_graphql`, `_cursor_for_offset`, `_CURSOR_OFFSET_QUERY`, `_DEFAULT_SAMPLE_COUNT`, `_GRAPHQL_CONCURRENCY` from `connectors/github.py`. The `fetch_graphql` primitive in `connectors/base.py` remains for future callers.
- `TestStargazerGraphQL` test class. Its mocks encoded the same false cursor-format assumption as the production code, so the suite passed green while shipping broken charts — a textbook "mock agrees with the thing being verified" trap. Replaced by `TestStargazerRESTSampling` which exercises the real REST path and includes a regression gate asserting the broken helpers are not re-introduced.

### Dev

- `scripts/probe_star_history.py` — ad-hoc diagnostic probe that calls `fetch_stargazer_history` against real repos and dumps the shape. Used during this investigation; kept for future parity checks against `star-history.com`.

## [0.2.9] - 2026-04-21

### Fixed

- **Star history charts now render an authentic growth curve for any repo size.** v0.2.8 fetched only the most-recent 2,000 stargazers for any repo with more than ~2,000 stars, which meant both the 361,000-star `openclaw/openclaw` and the 40,000-star `JuliusBrussee/caveman` rendered as flat horizontal lines near their total-star value — the captured window's variation was invisible on the full-range Y-axis. Star history now uses GraphQL cursor-offset sampling to pull 12 real stargazer timestamps evenly distributed across the repository's full lifetime, regardless of whether the repo has 30 stars or 500,000. The resulting curve shows actual adoption shape — slow-early, explosive-middle, tapering-late — rather than either a hockey-stick or a flat line.
- **X-axis date labels adapt to the repository's lifetime.** A viral repo that went from 0 to 40K stars in two weeks was being labeled with a single "2026" at the center of its axis; a mature repo with 10 years of history showed the same year-only format. The axis now selects granularity from the actual temporal span — daily labels ("Apr 05", "Apr 12") when the span is under two weeks, weekly under 90 days, month-plus-year under two years, yearly up to ten years, and every-other-year beyond. Labels maintain a minimum 48-pixel horizontal gap so they never collide — the "202324" pileup is gone.

### Changed

- **Parallel GraphQL dispatch is now bounded.** Cold fetches fan out twelve cursor-offset queries across four concurrent in-flight requests via `asyncio.Semaphore`. This keeps cold-fetch latency under ~1 second while staying well below per-minute abuse-detection thresholds that bursty same-token parallelism could otherwise trip.

## [0.2.8] - 2026-04-20

### Fixed

- **Star history charts now render readably on large repositories.** Previously, repos with more than ~40,000 stars produced a flat-then-vertical "hockey stick" because GitHub's stargazer REST endpoint hard-caps deep pagination, so the only data reachable was a small cluster of early-history stars followed by a single jump to today. Star history now sources from GitHub's GraphQL API and adapts its sampling window to the repo: small repos continue to get full lifetime views, large repos get a detailed recent-growth curve similar to the one star-history.com shows.
- **Star-count milestone labels no longer stack on top of each other.** When sampled points clustered temporally, the milestone labels (`500`, `1K`, `5K`, `10K`, ...) would render in a single illegible pile on top of the crossing point. Milestones now maintain a minimum 40-pixel horizontal gap; any labels that would overlap with an already-placed one are dropped in favor of the first (lowest-threshold) milestone in the cluster.

### Changed

- **All chart rendering now flows through template partials.** The chart engine's remaining rendering paths — axes, gridlines, polyline, area fill, milestones, and the empty-state overlay — joined the marker layer in Jinja. The engine module returns structured Python data; Jinja partials under `templates/components/` produce the final SVG. No visual change; output is byte-identical for the shipped genomes on unchanged inputs.

### Added

- **`fetch_graphql` connector primitive.** New async helper in the connector layer that handles POST with JSON bodies, GitHub bearer-token rotation, circuit-breaker coordination, and SSRF validation — mirroring the existing `fetch_json` contract. This unlocks future migration of the stats card's six REST sub-fetches to a single GraphQL call, and keeps a single canonical place for authenticated-POST plumbing.

### Dev

- GraphQL stargazer pipeline is covered by unit tests for the primary path, REST fallback on failure, no-token skip, mega-repo window cap, small-repo history exhaustion, downsampling correctness, and current-UTC now-point stamping.

## [0.2.7] - 2026-04-20

### Fixed

- **Star history charts now end at the current date.** On very large repositories (40k+ stars), GitHub caps stargazer pagination at roughly the first 40,000 stars, so the latest sample pulled from the API was often years old and the polyline terminated in the past. The chart now always appends a final data point stamped at the current time, while still reporting the real total star count. Small repos are unaffected.
- **Session receipt labels are honest again.** The "N corrections" line previously counted every user turn — any pushback, redirect, or elaboration — and rendered them next to tool-failure marks (`✗N`) on the token treemap, which created the impression that the two numbers should reconcile. They're now split into "N user turns" and "N tool errors", with tool-error counts tinted red to match the cell marks. A new legend — `✗N = failed tool calls` — appears above the token map so the red marks are self-explanatory.
- **Session receipt hero no longer misreports the dominant work phase.** The hero badge previously showed the label of the first detected stage, even when that stage lasted two minutes and a later stage dominated the session. It now uses the stage with the largest share of tool calls, and falls back to `MIXED` when no single stage exceeds 20%.
- **Rhythm bars stop overflowing their track on long sessions.** On sessions with many stages (~30+), the rightmost rhythm bar on the receipt could render hundreds of pixels past the track's right edge. Receipt and rhythm-strip now share a single layout routine with a proper gap budget and a post-hoc rescale, so bars always fit the track regardless of stage count.
- **Rhythm bars encode time, not tool-call share.** When the telemetry contract carries start and end timestamps per stage, bar widths are now proportional to stage duration, so the time-axis labels (`0m · 104m · 209m`) actually correspond to bar positions. Bar heights are now uniform; the previous height scaling was effectively noise because most bars hit the minimum-height floor.
- **Live badges now recognize `building` as a state.** A badge with `value="building"` (or `"rebuilding"` / `"build"`) now renders as the building state instead of falling through to the default `active`. Longer phrases containing the word "build" are not affected — only those three exact tokens.
- **Deploying `HW_GITHUB_TOKENS` no longer crashes the app.** A vestigial `github_tokens` field on the settings schema was trying to parse the environment variable as JSON on startup, so setting the plain comma-separated secret that the token-rotation code actually expects caused a 500. The field has been removed; the connector reads the secret directly, and plain comma-separated deployments now work as documented.

### Added

- **`hw_discover` advertises the `stats`, `chart`, and `timeline` routes.** MCP clients calling `hw_discover(what="url_grammar")` now receive URL patterns, example URLs, and method hints for the three routes that shipped in v0.2.0 but were missing from discovery.

### Changed

- **Chart markers render through template partials.** Marker shapes (rect, circle, diamond, and their endpoint variants) now live as Jinja partials under `templates/components/chart-markers/`, matching how the rest of the rendering pipeline handles SVG. No visual change; output is byte-identical for the shipped genomes.

### Dev

- GitHub token pool rotation is now covered by unit tests (`HW_GITHUB_TOKENS` comma-separated list, `GITHUB_TOKEN` single-token fallback, whitespace tolerance, empty-env behavior).

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
