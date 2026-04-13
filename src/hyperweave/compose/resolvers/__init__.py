"""Frame-specific resolvers (Session 2A+2B).

New resolvers live in per-frame modules under this package to honour
Invariant 10 (no file >400 lines). The existing ``compose/resolver.py``
is grandfathered at ~1600 lines; splitting it is deferred to a separate
cleanup session.

Each resolver is a function ``resolve_<frame>(spec, genome, profile, **kw)``
that returns a dict with keys ``width``, ``height``, ``template``, ``context``.
The top-level ``compose/resolver.py:resolve()`` dispatcher imports each
resolver module directly — this package init stays empty to avoid import
order issues while Session 2A+2B phases roll in.
"""
