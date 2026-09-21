"""
Platform Adapter Factory.
Detects current operating system and returns appropriate PlatformAdapter instance.
"""

import sys
from platform_adapters.base import PlatformAdapter


def get_platform_adapter() -> PlatformAdapter:
    """Returns an instance of the adapter matching the host OS."""
    if sys.platform == "darwin":
        from platform_adapters.macos import MacOSAdapter
        return MacOSAdapter()
    elif sys.platform == "win32":
        from platform_adapters.windows import WindowsAdapter
        return WindowsAdapter()
    else:
        # Default fallback (Linux or Unix)
        from platform_adapters.macos import MacOSAdapter
        return MacOSAdapter()
