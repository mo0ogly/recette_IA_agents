"""Static recette scorer for AgentRail Python code.

Python counterpart of the Rust ``agentrail_recette`` binary and the
``/python-recette`` command. Automates the pattern-based blocs (A/B/C/F),
orchestrates the static-analysis bloc (D: ruff, mypy, bandit, pip-audit), and
emits a scored report plus a CI exit code.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
