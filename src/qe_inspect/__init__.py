"""Diagnostic reports for Quantum ESPRESSO output files."""

__version__ = "0.1.0"

from .detect import parse_file  # noqa: E402
from .diagnostics import diagnose  # noqa: E402

__all__ = ["__version__", "parse_file", "diagnose"]
