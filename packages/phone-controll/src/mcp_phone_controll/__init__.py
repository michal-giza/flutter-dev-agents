"""mcp-phone-controll: MCP server for Flutter on-device build, deploy, and test.

Single source of truth for the package version. Read from
pyproject.toml at runtime via importlib.metadata so the version
stays in sync without a manual __version__ edit on every release.
Falls back to "0.0.0+unknown" if dist-info isn't available
(e.g. fresh editable checkout pre-install).
"""

from __future__ import annotations

try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("mcp-phone-controll")
except Exception:
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
