#!/usr/bin/env bash
# HyperWeave SessionEnd hook -- generates receipt SVG from transcript.
# Reads hook JSON from stdin (Claude Code hook protocol).
# Install: Add to ~/.claude/settings.json hooks.SessionEnd
set -euo pipefail
exec hw session receipt 2>/dev/null
