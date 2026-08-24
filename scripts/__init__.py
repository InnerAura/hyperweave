"""Repo tooling. A package so `scripts.examples` imports unambiguously.

Not shipped in the wheel — `pyproject.toml` packages only `src/hyperweave`.
Before this file existed the generators reached each other through
`sys.path.insert(0, ".../scripts")` plus a bare `import generate_proofset`,
which made a 7k-line script an import target and put a very generic module
name on the global path.
"""
