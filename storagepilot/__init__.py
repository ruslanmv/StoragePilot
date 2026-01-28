"""
StoragePilot - AI-Powered Storage Lifecycle Manager
====================================================

A multi-agent AI system that autonomously analyzes, organizes,
and optimizes storage on developer workstations.

Example usage:
    from storagepilot import StoragePilot

    pilot = StoragePilot()
    pilot.scan()
    pilot.analyze()
"""

__version__ = "0.1.0"
__author__ = "ruslanmv"

from storagepilot.core import StoragePilot

__all__ = ["StoragePilot", "__version__"]
