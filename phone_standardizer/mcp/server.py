"""JSON-RPC 2.0 Model Context Protocol (MCP) stdio handler for Phone Standardizer."""

from __future__ import annotations

import json
import sys
from typing import Any

from phone_standardizer.audit import explain_phone
from phone_standardizer.registry import get_dial_plan
from phone_standardizer.standardizer import mask_phone, standardize_phone

MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "standardize_phone",
        "description": "Parse, normalize, validate, and format a telephone number into E.164, National, International, and RFC 3966.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "country": {"type": "string"},
                "default_country": {"type": "string", "default": "US"},
            },
            "required": ["phone"],
        },
    },
    {
        "name": "lookup_country_dial_plan",
        "description": "Retrieve ITU-T E.164 calling code, trunk prefix, and NSN lengths for any of the 249 ISO-3166-1 countries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "identifier": {"type": "string"},
            },
            "required": ["identifier"],
        },
    },
    {
        "name": "mask_phone",
        "description": "Mask a phone number using partial (+1******2671), redact, or hash strategies.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "strategy": {"type": "string", "enum": ["partial", "redact", "hash"], "default": "partial"},
                "country": {"type": "string"},
            },
            "required": ["phone"],
        },
    },
    {
        "name": "explain_phone",
        "description": "Return a diagnostic and geographic intelligence report (locality, timezones, carrier MNO, TCPA calling window) for a phone number.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "country": {"type": "string"},
                "default_country": {"type": "string", "default": "US"},
            },
            "required": ["phone"],
        },
    },
]


def handle_mcp_request(request: dict[str, Any]) -> dict[str, Any]:
    """Process a single JSON-RPC 2.0 MCP request and return the response dictionary."""
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "phone-standardizer-mcp", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": MCP_TOOLS},
        }

    if method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments") or {}
        if tool_name == "standardize_phone":
            res = standardize_phone(
                args.get("phone"),
                country=args.get("country"),
                default_country=args.get("default_country", "US"),
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(res.to_dict())}]},
            }
        if tool_name == "lookup_country_dial_plan":
            plan = get_dial_plan(args.get("identifier"))
            payload = plan.to_dict() if plan else {"error": "Country not found"}
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(payload)}]},
            }
        if tool_name == "mask_phone":
            masked = mask_phone(
                args.get("phone"),
                strategy=args.get("strategy", "partial"),
                country=args.get("country"),
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps({"masked": masked})}]},
            }
        if tool_name == "explain_phone":
            report = explain_phone(
                args.get("phone"),
                country=args.get("country"),
                default_country=args.get("default_country", "US"),
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(report)}]},
            }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> int:  # pragma: no cover
    """Run the stdio JSON-RPC MCP server loop."""
    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        req = json.loads(stripped)
        resp = handle_mcp_request(req)
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()
    return 0
