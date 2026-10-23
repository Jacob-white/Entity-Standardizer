"""Model Context Protocol (MCP) server for Address-Standardizer.

Allows AI agents and LLM clients (Claude Desktop, Cursor, Gemini CLI)
to parse, validate, geocode, and explain addresses via standardized MCP protocol.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, List, Optional

from address_standardizer.mcp.tools import (
    autocomplete_address_tool,
    batch_standardize_tool,
    explain_parse_tool,
    standardize_address_tool,
    validate_postal_tool,
)


def _get_mcp_server_cls() -> Any:
    """Resolve MCPServer class supporting MCP v2 and v1."""
    try:
        from mcp.server.mcpserver import MCPServer

        return MCPServer
    except ImportError:
        pass

    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[no-redef]

        return FastMCP
    except ImportError:
        return None


_MCPServer = _get_mcp_server_cls()


def create_mcp_server() -> Any:
    """Create and configure the Address-Standardizer MCP server with all tools registered."""
    if _MCPServer is None:
        raise ImportError(
            "The MCP server requires the 'mcp' extra. Install it with: pip install 'address-standardizer[mcp]'"
        )

    server = _MCPServer("address-standardizer")

    @server.tool(
        name="standardize_address",
        description=(
            "Standardize, validate, and optionally geocode a single postal address across 249 ISO countries. "
            "Returns standardized USPS Pub 28 / UPU S42 components, deliverability, confidence routing tier, "
            "and building keys."
        ),
    )
    def standardize_address(
        address: Optional[str] = None,
        street1: Optional[str] = None,
        street2: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        postal_code: Optional[str] = None,
        country: Optional[str] = None,
        enable_geocoding: bool = False,
        include_metadata: bool = False,
        explain: bool = False,
        correct_state_from_zip: bool = False,
    ) -> dict:
        return standardize_address_tool(
            address=address,
            street1=street1,
            street2=street2,
            city=city,
            state=state,
            postal_code=postal_code,
            country=country,
            enable_geocoding=enable_geocoding,
            include_metadata=include_metadata,
            explain=explain,
            correct_state_from_zip=correct_state_from_zip,
        )

    @server.tool(
        name="batch_standardize",
        description=(
            "High-throughput batch standardization of multiple postal addresses (up to 500 records). "
            "Ideal for data cleaning pipelines and bulk verification."
        ),
    )
    def batch_standardize(
        addresses: list,
        enable_geocoding: bool = False,
        correct_state_from_zip: bool = False,
    ) -> dict:
        return batch_standardize_tool(
            addresses=addresses,
            enable_geocoding=enable_geocoding,
            correct_state_from_zip=correct_state_from_zip,
        )

    @server.tool(
        name="validate_postal",
        description=(
            "Validate a postal code format against official national standards across 249 ISO countries. "
            "Identifies non-postal nations and extracts structural components."
        ),
    )
    def validate_postal(
        postal_code: str,
        country: str = "US",
    ) -> dict:
        return validate_postal_tool(
            postal_code=postal_code,
            country=country,
        )

    @server.tool(
        name="autocomplete_address",
        description=(
            "Real-time address autocomplete and typeahead suggestion engine with fuzzy typo tolerance "
            "and geographic proximity biasing."
        ),
    )
    def autocomplete_address(
        query: str,
        limit: int = 5,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        country: str = "USA",
    ) -> list:
        return autocomplete_address_tool(
            query=query,
            limit=limit,
            latitude=latitude,
            longitude=longitude,
            country=country,
        )

    @server.tool(
        name="explain_parse",
        description=(
            "Detailed explanation and audit trace of how an address was parsed and standardized, "
            "including 44 stable rule IDs, token rewrites, and alternative interpretations."
        ),
    )
    def explain_parse(
        address: str,
        country: Optional[str] = None,
        alternatives: int = 3,
    ) -> dict:
        return explain_parse_tool(
            address=address,
            country=country,
            alternatives=alternatives,
        )

    return server


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for running the Address-Standardizer MCP server."""
    parser = argparse.ArgumentParser(
        prog="address-standardizer-mcp",
        description="Run Address-Standardizer Model Context Protocol (MCP) server",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host for SSE / HTTP transport (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Bind port for SSE / HTTP transport (default: 8000)",
    )

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    server = create_mcp_server()
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        if hasattr(server, "settings"):
            server.settings.host = args.host
            server.settings.port = args.port
        server.run(transport=args.transport)

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
