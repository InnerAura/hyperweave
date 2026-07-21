"""Extras-isolation guard: core import closures never reach an extras package.

The dev venv installs every extra (fastapi, fastmcp, resvg_py, PIL), so absence
is simulated in a subprocess whose ``__import__`` raises ``ModuleNotFoundError``
for those roots. A subprocess is deliberate: in-process ``sys.modules`` surgery
would leak a corrupted view of hyperweave singletons (template env caches,
connector state) into every later test, and a fresh interpreter is the true
reproduction of a lean install's first import.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

_SCRIPT = textwrap.dedent(
    """
    import builtins
    import sys

    BLOCKED = {"fastapi", "fastmcp", "resvg_py", "PIL"}
    real_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in BLOCKED:
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return real_import(name, *args, **kwargs)

    builtins.__import__ = guarded

    import hyperweave.cli

    from hyperweave.connectors.data_tokens import parse_data_tokens

    assert parse_data_tokens("text:hi"), "text token failed to parse"

    from typer.testing import CliRunner

    result = CliRunner().invoke(
        hyperweave.cli.app, ["compose", "badge", "build", "--data", "text:hi"]
    )
    assert result.exit_code == 0, f"--data compose failed: {result.output!r}"

    leaked = BLOCKED & {m.split(".")[0] for m in sys.modules}
    assert not leaked, f"extras leaked into the core import closure: {leaked}"

    try:
        import hyperweave.mcp.server  # noqa: F401
    except ModuleNotFoundError:
        pass  # fastmcp genuinely required there -- proves the block is targeted
    else:
        raise AssertionError("mcp.server imported with fastmcp blocked")

    print("ISOLATION-OK")
    """
)


def test_data_tokens_import_without_serve_extra() -> None:
    """A lean install (no fastapi/fastmcp/raster extras) composes with --data."""
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    assert "ISOLATION-OK" in proc.stdout
