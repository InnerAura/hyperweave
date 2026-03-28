"""Entry point: python -m hyperweave.mcp."""

from hyperweave.mcp.server import mcp

mcp.run(transport="stdio")
