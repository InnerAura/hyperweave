"""FastAPI serving layer -- /g/, /a/, /d/ namespaces.

Import the app as ``from hyperweave.serve.app import app`` (submodule-qualified,
matching the uvicorn factory string) -- this package eagerly imports nothing, so
``hyperweave.serve.*`` submodules stay importable without the ``[serve]`` extra.
"""
