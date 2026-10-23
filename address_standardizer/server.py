"""
Standalone High-Concurrency Microservice Daemon for Address Standardizer.
=========================================================================
Production-grade FastAPI daemon exposing OpenAPI 3.1 endpoints for:
  - Sub-2ms single address standardization (/v1/standardize)
  - High-throughput batch standardization with JSON & streaming NDJSON (/v1/batch)
  - Real-time typeahead autocomplete with proximity biasing (/v1/autocomplete)
  - Service health and diagnostics (/health)
  - Real-time Prometheus and JSON metrics (/metrics)
"""

import dataclasses
import json
import logging
import os
import threading
import time
from typing import Any, Dict, Iterator, List, Optional, Union

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from address_standardizer import __version__
from address_standardizer._native_dispatch import (
    get_capabilities,
    is_native_available,
    is_using_native,
)
from address_standardizer.autocomplete import (
    autocomplete_address,
)
from address_standardizer.cache import get_cache_stats
from address_standardizer.service.middleware import (
    GuardMiddleware,
    ObservabilityMiddleware,
    install_error_handlers,
)
from address_standardizer.service.readiness import run_checks
from address_standardizer.service.runtime import ServiceRuntime
from address_standardizer.service.telemetry import LatencyHistogram, bounded_increment, route_label as _route_label
from address_standardizer.standardizer import standardize_address

logger = logging.getLogger("address_standardizer.server")

SERVER_START_TIME = time.time()


# ============================================================================
# Metrics Collector
# ============================================================================

class MetricsCollector:
    """Thread-safe in-memory metrics collector for server telemetry."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.total_requests = 0
        self.endpoint_counts: Dict[str, int] = {}
        self.status_counts: Dict[int, int] = {}
        self.total_addresses_processed = 0
        self.total_latency_seconds = 0.0
        self.key_counts: Dict[str, int] = {}
        self.latency = LatencyHistogram()

    # Endpoint labels are route templates (or "unmatched"), never raw client paths, so cardinality is bounded.
    MAX_ENDPOINT_LABELS = 64
    MAX_KEY_LABELS = 64  # per-API-key request counters; further key names are folded into "other"

    def record_request(
        self,
        endpoint: str,
        status_code: int,
        duration: float,
        address_count: int = 1,
        key_name: Optional[str] = None,
    ) -> None:
        with self._lock:
            self.total_requests += 1
            self.latency.observe(duration)
            if key_name is not None:
                bounded_increment(self.key_counts, key_name, self.MAX_KEY_LABELS)
            if endpoint not in self.endpoint_counts and len(self.endpoint_counts) >= self.MAX_ENDPOINT_LABELS:
                endpoint = "other"
            self.endpoint_counts[endpoint] = self.endpoint_counts.get(endpoint, 0) + 1
            self.status_counts[status_code] = self.status_counts.get(status_code, 0) + 1
            self.total_addresses_processed += address_count
            self.total_latency_seconds += duration

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> Dict[str, Any]:
        avg_lat_ms = (
            (self.total_latency_seconds / self.total_requests * 1000.0)
            if self.total_requests > 0
            else 0.0
        )
        return {
            "uptime_seconds": round(time.time() - SERVER_START_TIME, 2),
            "total_requests": self.total_requests,
            "total_addresses_processed": self.total_addresses_processed,
            "average_latency_ms": round(avg_lat_ms, 3),
            "requests_by_endpoint": dict(self.endpoint_counts),
            "requests_by_status": dict(self.status_counts),
            "requests_by_key": dict(self.key_counts),
            "latency_seconds": {
                "buckets": [[le, n] for le, n in self.latency.cumulative()],
                "sum": round(self.latency.sum, 6),
                "count": self.latency.count,
            },
        }

    def prometheus_format(self) -> str:
        snap = self.snapshot()
        lines = [
            "# HELP address_standardizer_requests_total Total number of HTTP requests.",
            "# TYPE address_standardizer_requests_total counter",
            f"address_standardizer_requests_total {snap['total_requests']}",
            "# HELP address_standardizer_addresses_processed_total Total addresses parsed/standardized.",
            "# TYPE address_standardizer_addresses_processed_total counter",
            f"address_standardizer_addresses_processed_total {snap['total_addresses_processed']}",
            "# HELP address_standardizer_uptime_seconds Process uptime in seconds.",
            "# TYPE address_standardizer_uptime_seconds gauge",
            f"address_standardizer_uptime_seconds {snap['uptime_seconds']}",
            "# HELP address_standardizer_avg_latency_ms Average request latency in milliseconds.",
            "# TYPE address_standardizer_avg_latency_ms gauge",
            f"address_standardizer_avg_latency_ms {snap['average_latency_ms']}",
        ]
        for ep, cnt in snap["requests_by_endpoint"].items():
            lines.append(f'address_standardizer_endpoint_requests_total{{endpoint="{_escape_label(ep)}"}} {cnt}')
        for st, cnt in snap["requests_by_status"].items():
            lines.append(f'address_standardizer_status_requests_total{{code="{st}"}} {cnt}')
        for name, cnt in snap["requests_by_key"].items():
            lines.append(f'address_standardizer_key_requests_total{{key="{_escape_label(name)}"}} {cnt}')
        lines.append("# HELP address_standardizer_request_duration_seconds Request latency histogram.")
        lines.append("# TYPE address_standardizer_request_duration_seconds histogram")
        for le, cnt in snap["latency_seconds"]["buckets"]:
            lines.append(f'address_standardizer_request_duration_seconds_bucket{{le="{le}"}} {cnt}')
        lines.append(f"address_standardizer_request_duration_seconds_sum {snap['latency_seconds']['sum']}")
        lines.append(f"address_standardizer_request_duration_seconds_count {snap['latency_seconds']['count']}")
        return "\n".join(lines) + "\n"


def _item_error(index: int, exc: Exception) -> Dict[str, Any]:
    """Generic per-record error line for NDJSON output (no internals, no echo of the input)."""
    if isinstance(exc, (ValueError, TypeError)):  # includes JSON decode and pydantic validation errors
        return {"error": "invalid record", "index": index}
    logger.exception("Batch item %d failed", index)
    return {"error": "engine failure", "index": index}


def _escape_label(value: str) -> str:
    """Escape a Prometheus label value (backslash, double quote, newline)."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


metrics = MetricsCollector()


class MetricsMiddleware:
    """Records request metrics and adds ``X-Response-Time-Ms`` (pure ASGI; reads the module-level ``metrics``)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        scope.setdefault("state", {})
        request = Request(scope)
        start = time.perf_counter()
        recorded = False

        async def send_with_metrics(message: Message) -> None:
            nonlocal recorded
            if message["type"] == "http.response.start":
                recorded = True
                duration = time.perf_counter() - start
                metrics.record_request(
                    _route_label(request),
                    message["status"],
                    duration,
                    address_count=getattr(request.state, "address_count", 1),
                    key_name=getattr(request.state, "key_name", None),
                )
                MutableHeaders(scope=message)["X-Response-Time-Ms"] = f"{duration * 1000.0:.3f}"
            await send(message)

        try:
            await self.app(scope, receive, send_with_metrics)
        except Exception:
            if not recorded:
                metrics.record_request(_route_label(request), 500, time.perf_counter() - start)
            raise


def _max_batch_size() -> int:
    """Maximum addresses per /v1/batch request (env ADDRESS_STANDARDIZER_MAX_BATCH, default 10,000)."""
    try:
        return max(1, int(os.environ.get("ADDRESS_STANDARDIZER_MAX_BATCH", "10000")))
    except ValueError:
        return 10000


def _max_body_bytes() -> int:
    """Maximum request body size in bytes for /v1/batch (env ADDRESS_STANDARDIZER_MAX_BODY_BYTES, default 16 MiB)."""
    try:
        return max(1024, int(os.environ.get("ADDRESS_STANDARDIZER_MAX_BODY_BYTES", str(16 * 1024 * 1024))))
    except ValueError:
        return 16 * 1024 * 1024


async def _read_body_limited(request: Request) -> bytes:
    """Read the request body, refusing (413) as soon as it exceeds the configured limit."""
    limit = _max_body_bytes()
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(
            status_code=413,
            detail=f"Request body of {declared} bytes exceeds the limit of {limit} bytes.",
        )
    chunks: List[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=f"Request body exceeds the limit of {limit} bytes.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _batch_too_large(count: int, limit: int) -> HTTPException:
    return HTTPException(
        status_code=413,
        detail=f"Batch of {count} addresses exceeds the limit of {limit}; split it or use NDJSON streaming in smaller requests.",
    )


# ============================================================================
# Pydantic Schemas (OpenAPI 3.1)
# ============================================================================

class StandardizeRequest(BaseModel):
    """Input payload for single address standardization."""
    address: Optional[str] = Field(default=None, description="Single-line address string")
    street1: Optional[str] = Field(default=None, description="Primary street line")
    street2: Optional[str] = Field(default=None, description="Secondary unit (Suite, Apt, Floor)")
    city: Optional[str] = Field(default=None, description="City / Locality name")
    state: Optional[str] = Field(default=None, description="State / Province code")
    postal_code: Optional[str] = Field(default=None, description="Postal / ZIP code")
    country: Optional[str] = Field(default=None, description="Country name or ISO-3166 code")
    enable_geocoding: bool = Field(default=True, description="Enable offline rooftop/TIGER geocoding")
    enable_fuzzy: bool = Field(default=True, description="Enable Levenshtein typo correction")
    allow_locality: bool = Field(default=False, description="Allow locality-only / city-level fallback")
    correct_state_from_zip: bool = Field(
        default=False,
        description="Replace a US state that contradicts the ZIP with the ZIP's state (reported as WARN_STATE_CORRECTED_FROM_ZIP). "
        "Off by default: a mismatching state is kept and the address is flagged ERR_ZIP_STATE_MISMATCH / UNDELIVERABLE.",
    )
    include_metadata: bool = Field(default=True, description="Include delivery intelligence and spatial metadata")
    include_explanation: bool = Field(
        default=False,
        description="Add `explanation` (ordered change records) and `field_confidence` (per-field, heuristic) to the response.",
    )
    alternatives: int = Field(
        default=0, ge=0, le=5, description="Add up to N next-best interpretations of an ambiguous input as `alternatives`."
    )

    model_config = {
        "extra": "ignore",
        "json_schema_extra": {
            "example": {
                "address": "1600 Pennsylvania Ave NW, Washington, DC 20500",
                "enable_geocoding": True,
                "enable_fuzzy": True,
            }
        },
    }


class StandardizeResponse(BaseModel):
    """Standardized USPS Pub 28 / ISO address output schema."""
    street1: str
    street2: str
    city: str
    state: str
    postal_code: str
    country: str
    country_iso3: str
    normalized_address_key: Optional[str] = None
    building_key: Optional[str] = None
    phonetic_key: Optional[str] = None
    address_status: str
    is_us: bool
    is_private_residence: bool = False
    is_registered_agent_hub: bool = False
    deliverability: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    precision: Optional[str] = None
    accuracy_radius_meters: Optional[float] = None
    census_tract: Optional[str] = None
    fips_code: Optional[str] = None
    confidence_score: Optional[float] = None
    routing_tier: Optional[str] = None
    rdi: Optional[str] = None
    cmra: Optional[bool] = None
    vacant: Optional[bool] = None
    dpv_footnotes: Optional[List[str]] = None
    corporate_risk_score: Optional[float] = None
    corporate_risk_flags: Optional[List[str]] = None
    rooftop_address: Optional[str] = None
    full_rooftop_address: Optional[str] = None
    care_of: Optional[str] = None  # text of a removed "c/o" / "attn" clause
    explanation: Optional[List[Dict[str, Any]]] = None  # only with include_explanation=true
    field_confidence: Optional[Dict[str, float]] = None  # only with include_explanation=true
    alternatives: Optional[List[Dict[str, Any]]] = None  # only with alternatives >= 1

    model_config = {"extra": "allow"}


class AuditDecisionRequest(BaseModel):
    """A steward's decision on one pending audit record (review UI)."""
    decision: str = Field(default="modify", description="approve | modify | reject")
    steward_id: Optional[str] = Field(default=None, max_length=64, description="Required unless the API key has a name")
    overrides: Dict[str, str] = Field(default_factory=dict, description="Field values to commit (decision=modify)")
    commentary: str = Field(default="", max_length=2000)

    model_config = {"extra": "forbid"}


class BatchStandardizeRequest(BaseModel):
    """Batch address standardization request payload."""
    addresses: List[Union[str, StandardizeRequest]] = Field(
        ...,
        description="List of raw address strings or structured requests",
    )
    enable_geocoding: bool = Field(default=True, description="Enable offline geocoding")
    enable_fuzzy: bool = Field(default=True, description="Enable typo correction")
    allow_locality: bool = Field(default=False, description="Allow locality-level fallback")
    correct_state_from_zip: bool = Field(default=False, description="Replace a state that contradicts the ZIP with the ZIP's state")


class AutocompleteRequest(BaseModel):
    """Payload for real-time typeahead address suggestion."""
    query: str = Field(..., min_length=1, description="Partial address input string")
    max_results: int = Field(default=10, ge=1, le=50, description="Max suggestions to return")
    state_filter: Optional[str] = Field(default=None, description="US State postal filter (e.g. CA, NY)")
    latitude: Optional[float] = Field(
        default=None, ge=-90, le=90, allow_inf_nan=False, description="Client latitude for proximity ranking"
    )
    longitude: Optional[float] = Field(
        default=None, ge=-180, le=180, allow_inf_nan=False, description="Client longitude for proximity ranking"
    )
    radius_miles: Optional[float] = Field(
        default=None, gt=0, le=25000, allow_inf_nan=False, description="Proximity radius bounding in miles"
    )


class AutocompleteSuggestionItem(BaseModel):
    """Individual autocomplete suggestion."""
    text: str
    street_line: str
    city: str
    state: str
    postal_code: str
    secondary_prompt_required: bool
    suggested_secondary_units: List[str]
    prompt_message: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_meters: Optional[float] = None


class AutocompleteResponse(BaseModel):
    """List of autocomplete suggestions."""
    suggestions: List[AutocompleteSuggestionItem]
    count: int


class ValidatePostalRequest(BaseModel):
    """Input payload for postal code validation."""
    postal_code: str = Field(..., description="Postal code to validate")
    country: Optional[str] = Field(default="US", description="ISO country code or name (default: US)")


class PostalValidationResponse(BaseModel):
    """Validation diagnostics for international postal codes."""
    is_valid: bool
    postal_code: str
    country_iso2: str
    country_iso3: str
    country_name: str
    has_postal_system: bool
    format_pattern: Optional[str] = None
    diagnostics: str


# ============================================================================
# Helpers
# ============================================================================

def _standardize_from_req(req: StandardizeRequest) -> Dict[str, Any]:
    st1 = req.street1
    if not st1 and req.address:
        st1 = req.address

    explain_args: Dict[str, Any] = {}
    if req.include_explanation or req.alternatives:
        from address_standardizer.reference.validation import server_reference_provider

        explain_args = {
            "explain": req.include_explanation, "alternatives": req.alternatives,
            "reference_provider": server_reference_provider(),
        }
    std = standardize_address(
        street1=st1,
        street2=req.street2,
        city=req.city,
        state=req.state,
        postal_code=req.postal_code,
        country=req.country,
        enable_geocoding=req.enable_geocoding,
        enable_fuzzy=req.enable_fuzzy,
        allow_locality=req.allow_locality,
        correct_state_from_zip=req.correct_state_from_zip,
        **explain_args,
    )
    from address_standardizer.reference.validation import attach_server_reference_validation

    # Adds "reference_validation" only when ADDRESS_STANDARDIZER_REFERENCE_DB is configured (docs/reference_data.md).
    return attach_server_reference_validation(
        std,
        std.as_dict(
            include_metadata=req.include_metadata,
            include_rooftop=True,
            include_explanation=bool(req.include_explanation or req.alternatives),
        ),
    )


def _process_item_to_dict(
    item: Union[str, StandardizeRequest, Dict[str, Any]],
    default_geocoding: bool = True,
    default_fuzzy: bool = True,
    default_allow_locality: bool = False,
    default_correct_state_from_zip: bool = False,
) -> Dict[str, Any]:
    if isinstance(item, str):
        req = StandardizeRequest(
            address=item,
            enable_geocoding=default_geocoding,
            enable_fuzzy=default_fuzzy,
            allow_locality=default_allow_locality,
            correct_state_from_zip=default_correct_state_from_zip,
        )
    elif isinstance(item, dict):
        req = StandardizeRequest(
            address=item.get("address"),
            street1=item.get("street1"),
            street2=item.get("street2"),
            city=item.get("city"),
            state=item.get("state"),
            postal_code=item.get("postal_code"),
            country=item.get("country"),
            enable_geocoding=item.get("enable_geocoding", default_geocoding),
            enable_fuzzy=item.get("enable_fuzzy", default_fuzzy),
            allow_locality=item.get("allow_locality", default_allow_locality),
            correct_state_from_zip=item.get("correct_state_from_zip", default_correct_state_from_zip),
            include_metadata=item.get("include_metadata", True),
            include_explanation=item.get("include_explanation", False),
            alternatives=item.get("alternatives", 0),
        )
    elif isinstance(item, StandardizeRequest):
        req = item
    else:
        # Arrays, numbers, null...: reject rather than stringify into a garbage address.
        raise TypeError(f"batch item must be a string or an object, got {type(item).__name__}")

    return _standardize_from_req(req)


# ============================================================================
# Application Factory
# ============================================================================

def _register_review_routes(app: FastAPI, runtime: ServiceRuntime) -> None:
    """Steward review UI (GET /review) and its audit endpoints. Registered only when authentication is configured or
    ADDRESS_STANDARDIZER_ENABLE_REVIEW_UI=1; otherwise none of these paths exist (404)."""
    from address_standardizer.audit import ReviewStatus, get_audit_ledger
    from address_standardizer.service import review

    if not review.review_enabled(runtime.keystore is not None, os.environ):
        return
    # The page is static and carries no data; the browser cannot send an API key when navigating to it, so it is
    # exempt from the key check (the audit endpoints below are not).
    runtime.config = dataclasses.replace(runtime.config, open_paths=runtime.config.open_paths | {review.PAGE_PATH})

    @app.get(review.PAGE_PATH, include_in_schema=False)
    def review_page():
        html, headers = review.render_page()
        return HTMLResponse(html, headers=headers)

    @app.get("/v1/audit", summary="List audit-ledger records for review", tags=["Stewardship"])
    def audit_list(
        status: str = Query("PENDING", description="PENDING, APPROVED, MODIFIED or REJECTED"),
        limit: int = Query(50, ge=1, le=review.MAX_LIST),
    ):
        """Records with the given review status, newest first, each with a re-computed explanation trace."""
        valid = (ReviewStatus.PENDING, ReviewStatus.APPROVED, ReviewStatus.MODIFIED, ReviewStatus.REJECTED)
        if status not in valid:
            raise HTTPException(status_code=422, detail=f"status must be one of {list(valid)}")
        records = review.list_records(get_audit_ledger(), status, limit)
        return JSONResponse({"records": records, "count": len(records)})

    @app.post("/v1/audit/{audit_id}/override", summary="Approve, modify or reject a record", tags=["Stewardship"])
    def audit_override(audit_id: str, body: AuditDecisionRequest, request: Request):
        """Applies the decision through ``StewardshipAuditLedger.apply_manual_override`` (signed with the key name)."""
        steward = getattr(request.state, "key_name", None) or body.steward_id
        if not steward:
            raise HTTPException(status_code=422, detail="steward_id is required when the API key has no name")
        try:
            updated = review.apply_decision(
                get_audit_ledger(), audit_id, steward, body.decision, body.overrides, body.commentary
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Audit record not found")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return JSONResponse(updated)


def create_app(runtime: Optional[ServiceRuntime] = None) -> FastAPI:
    """Create and configure the FastAPI application daemon.

    Production features (auth, rate limits, tenancy, tracing, ...) are configured from the environment at creation
    time (see docs/operations.md) or by passing a prebuilt ``ServiceRuntime``.
    """
    runtime = runtime or ServiceRuntime.from_env()
    docs_enabled = os.environ.get("ADDRESS_STANDARDIZER_DISABLE_DOCS", "").strip().lower() not in ("1", "true", "yes")
    app = FastAPI(
        title="Address Standardizer Microservice API",
        version=__version__,
        description=(
            "High-performance universal address standardization, pure offline rooftop geocoding, "
            "CASS Cycle N deliverability verification, and real-time typeahead autocomplete daemon."
        ),
        openapi_url="/openapi.json" if docs_enabled else None,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
    )

    app.state.service = runtime
    install_error_handlers(app)
    app.add_middleware(GuardMiddleware, runtime=runtime)  # innermost: CORS wraps it so 401/403/429 carry CORS headers

    # Origins come from configuration. The default is open (no cookies/auth are used), but credentialed
    # cross-origin requests are only allowed for an explicit allow-list.
    configured = [o.strip() for o in os.environ.get("ADDRESS_STANDARDIZER_CORS_ORIGINS", "").split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=configured or ["*"],
        allow_credentials=bool(configured),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(MetricsMiddleware)

    app.add_middleware(ObservabilityMiddleware, runtime=runtime)  # outermost: request ID, tracing, access log

    # ------------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------------

    @app.get("/health", summary="Health and readiness probe", tags=["Diagnostics"])
    async def health():
        """Returns microservice health, engine capability matrix, and cache telemetry."""
        return {
            "status": "healthy",
            "version": __version__,
            "engine": {
                "native_acceleration": is_native_available(),
                "using_native": is_using_native(),
                "capabilities": get_capabilities(),
                "cache": get_cache_stats(),
            },
            "uptime_seconds": round(time.time() - SERVER_START_TIME, 2),
        }

    @app.get("/ready", summary="Readiness probe", tags=["Diagnostics"])
    def ready():
        """Readiness: 200 when the cache, audit ledger and reference database are usable, else 503 (names only)."""
        ok, checks = run_checks()
        return JSONResponse(
            {"status": "ready" if ok else "not_ready", "checks": checks}, status_code=200 if ok else 503
        )

    @app.get("/metrics", summary="Service telemetry and metrics", tags=["Diagnostics"])
    async def get_metrics(
        format: Optional[str] = Query(None, description="Metric format: 'json' or 'prometheus'"),
        request: Request = None,
    ):
        """Returns runtime throughput, request counts, and execution latencies."""
        accept_hdr = request.headers.get("accept", "") if request else ""
        if format == "prometheus" or "text/plain" in accept_hdr:
            return PlainTextResponse(metrics.prometheus_format(), media_type="text/plain; version=0.0.4")
        return JSONResponse(metrics.snapshot())

    @app.post(
        "/v1/standardize",
        response_model=StandardizeResponse,
        summary="Standardize single address",
        tags=["Standardization"],
    )
    def standardize_single(request: StandardizeRequest):
        """Standardize a single address string or structured address fields with sub-2ms latency.

        Declared as a plain function so FastAPI runs the CPU-bound work in its threadpool instead of
        blocking the event loop (and every other request, including /health).
        """
        try:
            result = _standardize_from_req(request)
            return JSONResponse(result)
        except Exception:
            logger.exception("Standardization failed")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Standardization engine failure",
            )

    @app.post(
        "/v1/batch",
        summary="High-throughput batch standardization",
        tags=["Standardization"],
    )
    async def batch_standardize(
        request: Request,
        format: Optional[str] = Query(None, description="Optional format: 'json' or 'ndjson'"),
    ):
        """Batch standardize a collection of addresses with support for JSON arrays and streaming NDJSON."""
        deadline = request.app.state.service.new_deadline()
        content_type = request.headers.get("content-type", "")
        accept_header = request.headers.get("accept", "")

        is_ndjson_req = "application/x-ndjson" in content_type or "application/jsonlines" in content_type
        is_ndjson_resp = (
            format == "ndjson"
            or "application/x-ndjson" in accept_header
            or "application/jsonlines" in accept_header
            or is_ndjson_req
        )

        if is_ndjson_req:
            # Handle incoming NDJSON stream
            body_bytes = await _read_body_limited(request)
            body_text = body_bytes.decode("utf-8", errors="replace")
            # JSON allows U+2028/U+0085 etc. inside strings; only "\n" separates NDJSON records.
            ndjson_lines = [ln.strip() for ln in body_text.split("\n") if ln.strip()]
            if len(ndjson_lines) > _max_batch_size():
                raise _batch_too_large(len(ndjson_lines), _max_batch_size())
            request.state.address_count = len(ndjson_lines)

            def ndjson_generator() -> Iterator[str]:
                for index, line in enumerate(ndjson_lines):
                    if deadline.expired():
                        yield json.dumps({"error": "timeout", "index": index}) + "\n"
                        return
                    try:
                        item = json.loads(line)
                        res = _process_item_to_dict(item)
                        yield json.dumps(res) + "\n"
                    except Exception as exc:
                        yield json.dumps(_item_error(index, exc)) + "\n"

            return StreamingResponse(ndjson_generator(), media_type="application/x-ndjson")

        # Standard JSON body handling
        raw_body = await _read_body_limited(request)
        try:
            body = json.loads(raw_body)
        except (ValueError, RecursionError):
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        addresses_list = []
        default_geo = True
        default_fuzzy = True
        default_allow_loc = False
        default_zip_state = False

        if isinstance(body, list):
            addresses_list = body
        elif isinstance(body, dict):
            addresses_list = body.get("addresses", [])
            default_geo = body.get("enable_geocoding", True)
            default_fuzzy = body.get("enable_fuzzy", True)
            default_allow_loc = body.get("allow_locality", False)
            default_zip_state = body.get("correct_state_from_zip", False)
            for flag_name, flag_value in (
                ("enable_geocoding", default_geo),
                ("enable_fuzzy", default_fuzzy),
                ("allow_locality", default_allow_loc),
                ("correct_state_from_zip", default_zip_state),
            ):
                if not isinstance(flag_value, bool):
                    raise HTTPException(status_code=400, detail=f"'{flag_name}' must be a boolean")
        else:
            raise HTTPException(status_code=400, detail="Request body must be an array or object with 'addresses'")

        if not isinstance(addresses_list, list):
            raise HTTPException(status_code=400, detail="'addresses' must be an array")
        if len(addresses_list) > _max_batch_size():
            raise _batch_too_large(len(addresses_list), _max_batch_size())
        request.state.address_count = len(addresses_list)
        for index, item in enumerate(addresses_list):
            if not isinstance(item, (str, dict)):
                raise HTTPException(
                    status_code=400,
                    detail=f"addresses[{index}] must be a string or an object, got {type(item).__name__}",
                )

        if is_ndjson_resp:
            def stream_array_as_ndjson() -> Iterator[str]:
                for index, item in enumerate(addresses_list):
                    if deadline.expired():
                        yield json.dumps({"error": "timeout", "index": index}) + "\n"
                        return
                    try:
                        res = _process_item_to_dict(
                            item,
                            default_geocoding=default_geo,
                            default_fuzzy=default_fuzzy,
                            default_allow_locality=default_allow_loc,
                            default_correct_state_from_zip=default_zip_state,
                        )
                        yield json.dumps(res) + "\n"
                    except Exception as exc:
                        yield json.dumps(_item_error(index, exc)) + "\n"

            return StreamingResponse(stream_array_as_ndjson(), media_type="application/x-ndjson")

        # Standard JSON array response
        def _process_all() -> List[Dict[str, Any]]:
            out: List[Dict[str, Any]] = []
            for index, item in enumerate(addresses_list):
                if deadline.expired():
                    raise HTTPException(status_code=504, detail="Batch processing exceeded the time limit")
                try:
                    out.append(
                        _process_item_to_dict(
                            item,
                            default_geocoding=default_geo,
                            default_fuzzy=default_fuzzy,
                            default_allow_locality=default_allow_loc,
                            default_correct_state_from_zip=default_zip_state,
                        )
                    )
                except ValidationError as exc:
                    raise HTTPException(
                        status_code=400, detail=f"addresses[{index}] has invalid fields: {exc.errors()[0]['loc']}"
                    )
                except Exception:
                    logger.exception("Batch item %d failed", index)
                    raise HTTPException(status_code=500, detail="Standardization engine failure")
            return out

        # CPU-bound: keep it off the event loop so /health and other requests stay responsive.
        results = await run_in_threadpool(_process_all)
        return JSONResponse(results)

    @app.post(
        "/v1/autocomplete",
        response_model=AutocompleteResponse,
        summary="Typeahead address autocomplete",
        tags=["Autocomplete"],
    )
    def autocomplete_post(request: AutocompleteRequest):
        """Real-time typeahead address suggestion with secondary unit prompting and proximity biasing."""
        suggestions = autocomplete_address(
            query=request.query,
            max_results=request.max_results,
            state_filter=request.state_filter,
            latitude=request.latitude,
            longitude=request.longitude,
            radius_miles=request.radius_miles,
        )
        items = [
            AutocompleteSuggestionItem(
                text=s.text,
                street_line=s.street_line,
                city=s.city,
                state=s.state,
                postal_code=s.postal_code,
                secondary_prompt_required=s.secondary_prompt_required,
                suggested_secondary_units=s.suggested_secondary_units,
                prompt_message=s.prompt_message,
                latitude=s.latitude,
                longitude=s.longitude,
                distance_meters=s.distance_meters,
            )
            for s in suggestions
        ]
        return AutocompleteResponse(suggestions=items, count=len(items))

    @app.get(
        "/v1/autocomplete",
        response_model=AutocompleteResponse,
        summary="Typeahead address autocomplete (GET)",
        tags=["Autocomplete"],
    )
    def autocomplete_get(
        q: str = Query(..., min_length=1, description="Partial address query"),
        limit: int = Query(10, ge=1, le=50, description="Max results"),
        state: Optional[str] = Query(None, description="Optional state filter"),
        lat: Optional[float] = Query(None, ge=-90, le=90, allow_inf_nan=False, description="Optional user latitude"),
        lon: Optional[float] = Query(None, ge=-180, le=180, allow_inf_nan=False, description="Optional user longitude"),
        radius_miles: Optional[float] = Query(None, gt=0, le=25000, allow_inf_nan=False, description="Optional radius in miles"),
    ):
        """GET endpoint for interactive typeahead address search."""
        req = AutocompleteRequest(
            query=q,
            max_results=limit,
            state_filter=state,
            latitude=lat,
            longitude=lon,
            radius_miles=radius_miles,
        )
        return autocomplete_post(req)

    @app.post(
        "/v1/validate-postal",
        response_model=PostalValidationResponse,
        summary="Validate international postal code",
        tags=["Postal"],
    )
    def validate_postal_post(request: ValidatePostalRequest):
        """Validate a postal code format against official national standards across 249 countries."""
        from address_standardizer.international.countries import CountryRegistry
        from address_standardizer.international.postal import POSTAL_RULES, validate_postal_code, PostalValidationResult

        country_str = request.country or "US"
        c_info = CountryRegistry.get(country_str)
        res = validate_postal_code(request.postal_code, country_code=country_str, return_details=True)
        rule = POSTAL_RULES.get(c_info.alpha3) if c_info else None
        pattern_str = None
        if rule:
            pattern_str = getattr(getattr(rule, "pattern", None), "pattern", getattr(rule, "regex", None))

        is_valid = res.is_valid if isinstance(res, PostalValidationResult) else bool(res)
        raw_pc = res.postal_code if isinstance(res, PostalValidationResult) else str(request.postal_code)
        diagnostics = res.reason if isinstance(res, PostalValidationResult) else ("Valid" if res else "Invalid format")

        return PostalValidationResponse(
            is_valid=is_valid,
            postal_code=raw_pc,
            country_iso2=c_info.alpha2 if c_info else (country_str[:2].upper() if country_str else "US"),
            country_iso3=c_info.alpha3 if c_info else (country_str[:3].upper() if country_str else "USA"),
            country_name=c_info.name if c_info else country_str,
            has_postal_system=c_info.has_postal_codes if c_info else True,
            format_pattern=pattern_str,
            diagnostics=diagnostics,
        )

    @app.get(
        "/v1/validate-postal",
        response_model=PostalValidationResponse,
        summary="Validate international postal code (GET)",
        tags=["Postal"],
    )
    def validate_postal_get(
        postal_code: Optional[str] = Query(None, description="Postal code to validate"),
        code: Optional[str] = Query(None, description="Postal code alias"),
        country: Optional[str] = Query("US", description="ISO country code or name (default: US)"),
    ):
        """GET endpoint for postal code validation."""
        pc = postal_code or code
        if not pc:
            raise HTTPException(status_code=422, detail="Query parameter 'postal_code' or 'code' is required")
        req = ValidatePostalRequest(postal_code=pc, country=country)
        return validate_postal_post(req)

    _register_review_routes(app, runtime)
    return app


app = create_app()
