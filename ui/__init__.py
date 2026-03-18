"""
UI package for Blast (CustomTkinter).

This package is intentionally thin: it wires user input to core orchestrator/services
and renders results. Business logic stays in `core/`.
"""

from ui.app import ModernJiraApp

__all__ = ["ModernJiraApp"]

