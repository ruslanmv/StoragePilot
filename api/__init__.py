"""
StoragePilot API Package
========================

Contains API routers for:
- copilot: AI assistant with tool-calling capabilities
"""

from .copilot import router as copilot_router

__all__ = ["copilot_router"]
