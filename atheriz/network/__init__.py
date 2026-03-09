"""
Network package for Atheriz.
Contains abstract base classes and implementations for distinct network protocols.
"""

from .manager import ConnectionManager

# Global connection manager instance
connection_manager = ConnectionManager()
