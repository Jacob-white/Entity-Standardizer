"""Address-Standardizer Model Context Protocol (MCP) server package."""

from address_standardizer.mcp.server import create_mcp_server, main
from address_standardizer.mcp.tools import (
    autocomplete_address_tool,
    batch_standardize_tool,
    explain_parse_tool,
    standardize_address_tool,
    validate_postal_tool,
)

__all__ = [
    "create_mcp_server",
    "main",
    "standardize_address_tool",
    "batch_standardize_tool",
    "validate_postal_tool",
    "autocomplete_address_tool",
    "explain_parse_tool",
]
