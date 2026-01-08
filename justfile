# HyperWeave Development Commands
# Usage: just <command>

# Default recipe - show available commands
default:
    @just --list

# ─────────────────────────────────────────────────────────────
# Installation & Setup
# ─────────────────────────────────────────────────────────────

# Install dependencies with uv
install:
    uv sync

# Install development dependencies
install-dev:
    uv sync --all-extras

# Setup pre-commit hooks
setup-hooks:
    uv run pre-commit install

# Complete development setup
setup: install-dev setup-hooks
    @echo "✓ Development environment ready"

# ─────────────────────────────────────────────────────────────
# Code Quality
# ─────────────────────────────────────────────────────────────

# Format code with ruff
fmt:
    uv run ruff format src/ tests/
    uv run ruff check --fix src/ tests/

# Check code quality without making changes
check:
    uv run ruff check src/ tests/
    uv run ruff format --check src/ tests/

# Run type checking with mypy
typecheck:
    uv run mypy src/

# Run all quality checks
qa: check typecheck
    @echo "✓ Code quality checks passed"

# ─────────────────────────────────────────────────────────────
# Testing
# ─────────────────────────────────────────────────────────────

# Run all tests
test:
    uv run pytest

# Run tests with coverage report
test-cov:
    uv run pytest --cov --cov-report=term-missing --cov-report=html

# Run tests in watch mode
test-watch:
    uv run pytest-watch

# Run specific test file
test-file FILE:
    uv run pytest {{FILE}}

# ─────────────────────────────────────────────────────────────
# Development Servers
# ─────────────────────────────────────────────────────────────

# Start FastAPI HTTP server (development mode)
serve:
    uv run uvicorn hyperweave.api.server:app --reload --host 0.0.0.0 --port 8000

# Start FastAPI HTTP server (production mode)
serve-prod:
    uv run uvicorn hyperweave.api.server:app --host 0.0.0.0 --port 8000 --workers 4

# Start MCP server
mcp:
    uv run python -m hyperweave.mcp.server

# Start MCP Inspector
mcp-inspector:
    npx @modelcontextprotocol/inspector uv run ./src/hyperweave/mcp/server.py 

# ─────────────────────────────────────────────────────────────
# CLI Commands
# ─────────────────────────────────────────────────────────────

# Show ontology summary
ontology:
    uv run hyperweave ontology

# List available specimens
specimens:
    uv run hyperweave ontology specimens

# Generate badge from specimen (example)
example-badge:
    uv run hyperweave specimen titanium-forge status operational \
        --intent "Example status badge" \
        --approach "Using titanium specimen for industrial aesthetic" \
        --tradeoffs "Chose titanium over chrome for cooler tone" \
        --output example-badge.svg
    @echo "✓ Generated example-badge.svg"

# Validate a badge SVG
validate FILE:
    uv run hyperweave validate {{FILE}}

# ─────────────────────────────────────────────────────────────
# Documentation
# ─────────────────────────────────────────────────────────────

# Generate API documentation
docs:
    @echo "API Documentation available at:"
    @echo "  FastAPI: http://localhost:8000/docs"
    @echo "  ReDoc:   http://localhost:8000/redoc"
    @echo "\nStart server with: just serve"

# ─────────────────────────────────────────────────────────────
# Building & Distribution
# ─────────────────────────────────────────────────────────────

# Build package
build:
    uv build

# Clean build artifacts
clean:
    rm -rf build/ dist/ *.egg-info .pytest_cache/ .coverage htmlcov/ .mypy_cache/ .ruff_cache/
    find . -type d -name __pycache__ -exec rm -rf {} +
    @echo "✓ Cleaned build artifacts"

# Clean and rebuild
rebuild: clean build

# ─────────────────────────────────────────────────────────────
# Deployment
# ─────────────────────────────────────────────────────────────

# Deploy to Cloudflare Workers (requires wrangler)
deploy:
    @echo "Cloudflare Workers deployment not yet configured"
    @echo "TODO: Add wrangler configuration"

# ─────────────────────────────────────────────────────────────
# Utility Commands
# ─────────────────────────────────────────────────────────────

# Show project information
info:
    @echo "HyperWeave Living Artifact Protocol v3.3.0"
    @echo "├── API: FastAPI v3.3"
    @echo "├── MCP: Model Context Protocol v3.3"
    @echo "├── CLI: Typer-based"
    @echo "└── Ontology: Badge Ontology v2.0.0"
    @echo ""
    @echo "Commands:"
    @echo "  just install    - Install dependencies"
    @echo "  just test       - Run tests"
    @echo "  just serve      - Start API server"
    @echo "  just mcp        - Start MCP server"
    @echo "  just ontology   - Browse ontology"

# Watch for changes and run tests
watch:
    uv run ptw

# All checks before commit
pre-commit: qa test
    @echo "✓ Ready to commit"

# Release checklist
release: qa test-cov build
    @echo "✓ Release checks passed"
    @echo ""
    @echo "Next steps:"
    @echo "1. Update version in pyproject.toml"
    @echo "2. Update CHANGELOG.md"
    @echo "3. git tag v<version>"
    @echo "4. git push --tags"

# ─────────────────────────────────────────────────────────────
# Batch SVG Generation (Testing)
# ─────────────────────────────────────────────────────────────

# Create test output directories
test-dirs:
    mkdir -p svg-primitives/test_v0.1/cli/specimens
    mkdir -p svg-primitives/test_v0.1/cli/themes
    mkdir -p svg-primitives/test_v0.1/api/specimens
    mkdir -p svg-primitives/test_v0.1/api/grammar
    mkdir -p svg-primitives/test_v0.1/mcp/specimens
    @echo "✓ Created test output directories"

# Generate CLI specimens (5 industrial-tier themes with full reasoning)
test-cli-specimens: test-dirs
    @echo "Generating CLI specimens (industrial tier with XAI metadata)..."
    uv run hyperweave specimen chrome status passing \
        --intent "CI status indicator for main branch" \
        --approach "Chrome for professional high-polish aesthetic" \
        --tradeoffs "Chose chrome over neon for corporate compatibility" \
        -o svg-primitives/test_v0.1/cli/specimens/chrome.svg
    uv run hyperweave specimen obsidian version 2.0.0 \
        --intent "Version display for dark-themed interfaces" \
        --approach "Obsidian for deep contrast and neon accent" \
        --tradeoffs "Chose obsidian over void for more visual interest" \
        -o svg-primitives/test_v0.1/cli/specimens/obsidian.svg
    uv run hyperweave specimen titanium build operational \
        --intent "System health monitoring badge" \
        --approach "Titanium for aerospace-grade industrial feel" \
        --tradeoffs "Chose titanium over chrome for cooler, harder tone" \
        -o svg-primitives/test_v0.1/cli/specimens/titanium.svg
    uv run hyperweave specimen brutalist alert warning \
        --state warning \
        --intent "Warning indicator for system alerts" \
        --approach "Brutalist for raw immediate visual impact" \
        --tradeoffs "Chose brutalist over brutalist-clean for signal bar visibility" \
        -o svg-primitives/test_v0.1/cli/specimens/brutalist.svg
    uv run hyperweave specimen brutalist-clean docs stable \
        --intent "Documentation status for minimal interfaces" \
        --approach "Pure architectural black/white for clean docs" \
        --tradeoffs "Chose brutalist-clean over brutalist for quieter aesthetic" \
        -o svg-primitives/test_v0.1/cli/specimens/brutalist-clean.svg
    @echo "✓ Generated 5 CLI specimens"

# Generate all CLI themes (25 themes from ontology)
test-cli-themes: test-dirs
    @echo "Generating CLI themes (25 total)..."
    # Minimal tier
    uv run hyperweave specimen void status active -o svg-primitives/test_v0.1/cli/themes/void.svg
    # Flagship tier
    uv run hyperweave specimen neon status live -o svg-primitives/test_v0.1/cli/themes/neon.svg
    uv run hyperweave specimen glass version 1.0.0 -o svg-primitives/test_v0.1/cli/themes/glass.svg
    uv run hyperweave specimen holo status online -o svg-primitives/test_v0.1/cli/themes/holo.svg
    uv run hyperweave specimen clarity build passing -o svg-primitives/test_v0.1/cli/themes/clarity.svg
    # Industrial tier
    uv run hyperweave specimen chrome build passing -o svg-primitives/test_v0.1/cli/themes/chrome.svg
    uv run hyperweave specimen obsidian version 2.0.0 -o svg-primitives/test_v0.1/cli/themes/obsidian.svg
    uv run hyperweave specimen titanium status operational -o svg-primitives/test_v0.1/cli/themes/titanium.svg
    # Premium tier
    uv run hyperweave specimen depth coverage 95% -o svg-primitives/test_v0.1/cli/themes/depth.svg
    uv run hyperweave specimen glossy license MIT -o svg-primitives/test_v0.1/cli/themes/glossy.svg
    # Scholarly tier
    uv run hyperweave specimen codex docs complete -o svg-primitives/test_v0.1/cli/themes/codex.svg
    uv run hyperweave specimen theorem proof verified -o svg-primitives/test_v0.1/cli/themes/theorem.svg
    uv run hyperweave specimen archive records indexed -o svg-primitives/test_v0.1/cli/themes/archive.svg
    uv run hyperweave specimen symposium paper published -o svg-primitives/test_v0.1/cli/themes/symposium.svg
    uv run hyperweave specimen cipher encryption AES-256 -o svg-primitives/test_v0.1/cli/themes/cipher.svg
    # Brutalist tier
    uv run hyperweave specimen brutalist raw exposed -o svg-primitives/test_v0.1/cli/themes/brutalist.svg
    uv run hyperweave specimen brutalist-clean minimal pure -o svg-primitives/test_v0.1/cli/themes/brutalist-clean.svg
    # Cosmology tier
    uv run hyperweave specimen sakura bloom spring -o svg-primitives/test_v0.1/cli/themes/sakura.svg
    uv run hyperweave specimen aurora light northern -o svg-primitives/test_v0.1/cli/themes/aurora.svg
    uv run hyperweave specimen singularity event horizon -o svg-primitives/test_v0.1/cli/themes/singularity.svg
    # Arcade tier
    uv run hyperweave specimen arcade-snes score 999999 -o svg-primitives/test_v0.1/cli/themes/arcade-snes.svg
    uv run hyperweave specimen arcade-gameboy level 99 -o svg-primitives/test_v0.1/cli/themes/arcade-gameboy.svg
    uv run hyperweave specimen arcade-gold coins 1000 -o svg-primitives/test_v0.1/cli/themes/arcade-gold.svg
    uv run hyperweave specimen arcade-purple magic infinite -o svg-primitives/test_v0.1/cli/themes/arcade-purple.svg
    uv run hyperweave specimen arcade-nes lives 3 -o svg-primitives/test_v0.1/cli/themes/arcade-nes.svg
    @echo "✓ Generated 25 CLI themes"

# Generate API specimens (requires server running on :8000)
test-api-specimens: test-dirs
    @echo "Generating API specimens (server must be running on :8000)..."
    curl -s -X POST "http://localhost:8000/v3/specimens/chrome-protocol/generate" \
        -H "Content-Type: application/json" \
        -d '{"content":{"label":"api","value":"chrome"},"reasoning":{"intent":"API test badge for chrome specimen","approach":"Chrome finish via HTTP POST","tradeoffs":"Testing API generation over CLI for automation"},"format":"svg"}' \
        > svg-primitives/test_v0.1/api/specimens/chrome-protocol.svg
    curl -s -X POST "http://localhost:8000/v3/specimens/obsidian-mirror/generate" \
        -H "Content-Type: application/json" \
        -d '{"content":{"label":"api","value":"obsidian"},"reasoning":{"intent":"API test badge for obsidian specimen","approach":"Obsidian finish via HTTP POST","tradeoffs":"Testing API generation over CLI for automation"},"format":"svg"}' \
        > svg-primitives/test_v0.1/api/specimens/obsidian-mirror.svg
    curl -s -X POST "http://localhost:8000/v3/specimens/titanium-forge/generate" \
        -H "Content-Type: application/json" \
        -d '{"content":{"label":"api","value":"titanium"},"reasoning":{"intent":"API test badge for titanium specimen","approach":"Titanium finish via HTTP POST","tradeoffs":"Testing API generation over CLI for automation"},"format":"svg"}' \
        > svg-primitives/test_v0.1/api/specimens/titanium-forge.svg
    curl -s -X POST "http://localhost:8000/v3/specimens/brutalist-signal/generate" \
        -H "Content-Type: application/json" \
        -d '{"content":{"label":"api","value":"brutalist"},"reasoning":{"intent":"API test badge for brutalist specimen","approach":"Brutalist finish via HTTP POST","tradeoffs":"Testing API generation over CLI for automation"},"format":"svg"}' \
        > svg-primitives/test_v0.1/api/specimens/brutalist-signal.svg
    curl -s -X POST "http://localhost:8000/v3/specimens/brutalist-minimal/generate" \
        -H "Content-Type: application/json" \
        -d '{"content":{"label":"api","value":"minimal"},"reasoning":{"intent":"API test badge for minimal specimen","approach":"Minimal finish via HTTP POST","tradeoffs":"Testing API generation over CLI for automation"},"format":"svg"}' \
        > svg-primitives/test_v0.1/api/specimens/brutalist-minimal.svg
    @echo "✓ Generated 5 API specimens"

# Generate API grammar examples (requires server running on :8000)
test-api-grammar: test-dirs
    @echo "Generating API grammar examples (server must be running on :8000)..."
    curl -s "http://localhost:8000/static.passing/chrome.sweep.svg" > svg-primitives/test_v0.1/api/grammar/static-passing-chrome.svg
    curl -s "http://localhost:8000/static.failing/neon.pulse.svg" > svg-primitives/test_v0.1/api/grammar/static-failing-neon.svg
    curl -s "http://localhost:8000/static.warning/obsidian.breathe.svg" > svg-primitives/test_v0.1/api/grammar/static-warning-obsidian.svg
    curl -s "http://localhost:8000/static.active/titanium.svg" > svg-primitives/test_v0.1/api/grammar/static-active-titanium.svg
    curl -s "http://localhost:8000/static.neutral/glass.svg" > svg-primitives/test_v0.1/api/grammar/static-neutral-glass.svg
    @echo "✓ Generated 5 API grammar examples"

# Generate all CLI artifacts (no server required)
test-cli: test-cli-specimens test-cli-themes
    @echo "✓ All CLI artifacts generated (30 SVGs)"

# Generate all API artifacts (requires server running)
test-api: test-api-specimens test-api-grammar
    @echo "✓ All API artifacts generated (10 SVGs)"

# Generate CLI artifacts only (no server required)
test-generate: test-cli
    @echo "✓ All test artifacts generated (CLI)"
    @echo "Run 'just serve' then 'just test-api' for API artifacts"

# Generate everything (requires server running on :8000)
test-all: test-cli test-api
    @echo "✓ All test artifacts generated (CLI + API = 40 SVGs)"
    @echo ""
    @echo "Output structure:"
    @ls -la svg-primitives/test_v0.1/cli/specimens/ | tail -n +2
    @echo "---"
    @ls -la svg-primitives/test_v0.1/cli/themes/ | tail -n +2
    @echo "---"
    @ls -la svg-primitives/test_v0.1/api/specimens/ | tail -n +2
    @echo "---"
    @ls -la svg-primitives/test_v0.1/api/grammar/ | tail -n +2
