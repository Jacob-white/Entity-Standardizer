"""JSON-RPC 2.0 Model Context Protocol (MCP) stdio handler for Entity & Phone Standardizer."""

from __future__ import annotations

import json
import sys
from typing import Any

from entity_standardizer.address.standardizer import standardize_address
from entity_standardizer.company import compare_companies, standardize_company
from entity_standardizer.person import (
    compare_persons,
    standardize_job_title,
    standardize_person,
)
from entity_standardizer.web import standardize_email, standardize_social, standardize_url
from entity_standardizer.audit import explain_phone
from entity_standardizer.dedup import compare_phones, deduplicate_phones
from entity_standardizer.joint import compare_contacts, standardize_contact
from entity_standardizer.registry import get_dial_plan
from entity_standardizer.standardizer import mask_phone, standardize_phone

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
        "description": "Mask a phone number using partial (+1******2671), partial_phone, last4, redact, null, hash, sha256, or md5 strategies.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "strategy": {
                    "type": "string",
                    "enum": ["partial", "partial_phone", "last4", "redact", "null", "hash", "sha256", "md5"],
                    "default": "partial",
                },
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
    {
        "name": "compare_phones",
        "description": "Compare two telephone numbers using E.164 equivalence, extension awareness, and keypad/transposition edit distance.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "phone_a": {"type": "string"},
                "phone_b": {"type": "string"},
                "country": {"type": "string"},
                "fuzzy_threshold": {"type": "number", "default": 0.88},
            },
            "required": ["phone_a", "phone_b"],
        },
    },
    {
        "name": "deduplicate_phones",
        "description": "Cluster and deduplicate a list of telephone numbers into Golden Phone Records.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "phones": {"type": "array", "items": {"type": "string"}},
                "country": {"type": "string"},
                "fuzzy_threshold": {"type": "number", "default": 0.88},
            },
            "required": ["phones"],
        },
    },
    {
        "name": "standardize_address",
        "description": "Parse, normalize, validate, and format a US or international physical/mailing address.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "street1": {"type": "string"},
                "street2": {"type": "string"},
                "city": {"type": "string"},
                "state": {"type": "string"},
                "postal_code": {"type": "string"},
                "country": {"type": "string", "default": "US"},
            },
        },
    },
    {
        "name": "standardize_company",
        "description": "Standardize an organization or company name (ISO 20275 legal suffixes, DBA/FKA, branch unit, and keys).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "country": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "standardize_person",
        "description": "Parse and standardize a person full name (salutation, nickname, Last-First un-inversion, root name, credentials).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "standardize_job_title",
        "description": "Normalize a job title, expanding abbreviations and classifying seniority_level, department, and is_executive.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "compare_companies",
        "description": "Compare two company names across exact company_key, base_name, DBA/FKA aliases, brand_stem, and phonetic keys.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "company_a": {"type": "string"},
                "company_b": {"type": "string"},
            },
            "required": ["company_a", "company_b"],
        },
    },
    {
        "name": "compare_persons",
        "description": "Compare two person names across exact person_key, nickname root_first_name, first initial, and phonetic keys.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "person_a": {"type": "string"},
                "person_b": {"type": "string"},
            },
            "required": ["person_a", "person_b"],
        },
    },
    {
        "name": "standardize_email",
        "description": "Standardize an email address (RFC 5321/5322, IDNA, subaddress, Gmail dot canonicalization, domain typo healing).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "email": {"type": "string"},
            },
            "required": ["email"],
        },
    },
    {
        "name": "standardize_url",
        "description": "Standardize a website URL (HTTPS upgrade, www/tracking parameter removal, eTLD+1 registrable domain).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "standardize_social",
        "description": "Standardize a social profile URL or @handle (LinkedIn, X/Twitter, GitHub, Instagram, Facebook, YouTube).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "platform": {"type": "string"},
            },
            "required": ["profile"],
        },
    },
    {
        "name": "standardize_contact",
        "description": "Jointly standardize an entity's address, phone, organization, person, title, and web pillars with cross-healing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "street1": {"type": "string"},
                "street2": {"type": "string"},
                "city": {"type": "string"},
                "state": {"type": "string"},
                "postal_code": {"type": "string"},
                "country": {"type": "string"},
                "phone": {"type": "string"},
                "fax": {"type": "string"},
                "organization": {"type": "string"},
                "person_name": {"type": "string"},
                "job_title": {"type": "string"},
                "email": {"type": "string"},
                "website": {"type": "string"},
                "social": {"type": "string"},
                "default_country": {"type": "string", "default": "US"},
            },
        },
    },
    {
        "name": "compare_contacts",
        "description": "Compare two multi-pillar contact/entity records across organization, person, phone, email, website, and address.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contact_a": {"type": "object"},
                "contact_b": {"type": "object"},
                "default_country": {"type": "string", "default": "US"},
            },
            "required": ["contact_a", "contact_b"],
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
                "serverInfo": {"name": "phone-standardizer-mcp", "version": "2.1.0"},
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
        if tool_name == "compare_phones":
            cmp_res = compare_phones(
                args.get("phone_a", ""),
                args.get("phone_b", ""),
                country=args.get("country"),
                fuzzy_threshold=float(args.get("fuzzy_threshold", 0.88)),
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(cmp_res.to_dict())}]},
            }
        if tool_name == "deduplicate_phones":
            clusters = deduplicate_phones(
                args.get("phones") or [],
                country=args.get("country"),
                fuzzy_threshold=float(args.get("fuzzy_threshold", 0.88)),
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps([c.to_dict() for c in clusters]),
                        }
                    ]
                },
            }
        if tool_name == "standardize_address":
            addr_res = standardize_address(
                street1=args.get("street1"),
                street2=args.get("street2"),
                city=args.get("city"),
                state=args.get("state"),
                postal_code=args.get("postal_code"),
                country=args.get("country", "US"),
                allow_locality=True,
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(addr_res.as_dict())}]},
            }
        if tool_name == "standardize_company":
            comp_res = standardize_company(args.get("name"), country=args.get("country"))
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(comp_res.to_dict())}]},
            }
        if tool_name == "standardize_person":
            per_res = standardize_person(args.get("name"))
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(per_res.to_dict())}]},
            }
        if tool_name == "standardize_job_title":
            jt_res = standardize_job_title(args.get("title"))
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(jt_res.to_dict())}]},
            }
        if tool_name == "compare_companies":
            cc_res = compare_companies(args.get("company_a"), args.get("company_b"))
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(cc_res.to_dict())}]},
            }
        if tool_name == "compare_persons":
            cp_res = compare_persons(args.get("person_a"), args.get("person_b"))
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(cp_res.to_dict())}]},
            }
        if tool_name == "standardize_email":
            email_res = standardize_email(args.get("email"))
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(email_res.to_dict())}]},
            }
        if tool_name == "standardize_url":
            url_res = standardize_url(args.get("url"))
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(url_res.to_dict())}]},
            }
        if tool_name == "standardize_social":
            soc_res = standardize_social(args.get("profile"), platform=args.get("platform"))
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(soc_res.to_dict())}]},
            }
        if tool_name == "standardize_contact":
            contact_res = standardize_contact(
                street1=args.get("street1"),
                street2=args.get("street2"),
                city=args.get("city"),
                state=args.get("state"),
                postal_code=args.get("postal_code"),
                country=args.get("country"),
                phone=args.get("phone"),
                fax=args.get("fax"),
                organization=args.get("organization"),
                person_name=args.get("person_name"),
                job_title=args.get("job_title"),
                email=args.get("email"),
                website=args.get("website"),
                social=args.get("social"),
                default_country=args.get("default_country", "US"),
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(contact_res.to_dict())}]
                },
            }
        if tool_name == "compare_contacts":
            cmp_contact_res = compare_contacts(
                args.get("contact_a") or {},
                args.get("contact_b") or {},
                default_country=args.get("default_country", "US"),
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(cmp_contact_res.to_dict())}]
                },
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
