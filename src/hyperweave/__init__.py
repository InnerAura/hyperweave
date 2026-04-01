"""HyperWeave -- Compositor API for self-contained SVG artifacts."""

try:
    from hyperweave._version import __version__
except ModuleNotFoundError:  # editable install without build
    __version__ = "0.0.0-dev"
