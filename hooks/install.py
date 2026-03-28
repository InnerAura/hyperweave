"""Install HyperWeave session telemetry hook into Claude Code."""

from __future__ import annotations

import json
from pathlib import Path

SETTINGS_PATH = Path.home() / ".claude" / "settings.json"

HOOK_ENTRY = {
    "hooks": [
        {
            "type": "command",
            "command": "hw session receipt",
            "timeout": 10,
        }
    ]
}


def install() -> bool:
    """Add SessionEnd hook to Claude Code settings. Returns True if installed."""
    settings: dict[str, object] = {}
    if SETTINGS_PATH.exists():
        settings = json.loads(SETTINGS_PATH.read_text())

    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        settings["hooks"] = hooks

    session_end: list[object] = hooks.setdefault("SessionEnd", [])  # type: ignore[assignment]
    if not isinstance(session_end, list):
        session_end = []
        hooks["SessionEnd"] = session_end

    # Check if already installed
    for entry in session_end:
        if not isinstance(entry, dict):
            continue
        for h in entry.get("hooks", []):
            if isinstance(h, dict) and "hw session" in h.get("command", ""):
                return False

    session_end.append(HOOK_ENTRY)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2) + "\n")
    return True


if __name__ == "__main__":
    if install():
        print(f"Installed SessionEnd hook in {SETTINGS_PATH}")
    else:
        print("Already installed.")
