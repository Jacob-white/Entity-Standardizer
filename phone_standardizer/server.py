"""FastAPI HTTP Microservice for Phone Standardizer."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from address_standardizer.standardizer import standardize_address
from phone_standardizer.audit import explain_phone
from phone_standardizer.batch import batch_standardize_phones
from phone_standardizer.dedup import compare_phones, deduplicate_phones
from phone_standardizer.joint import standardize_contact
from phone_standardizer.registry import CountryDialRegistry, get_dial_plan
from phone_standardizer.standardizer import standardize_phone


class PhoneStandardizeRequest(BaseModel):
    """Request payload for /v1/standardize."""

    phone: str = Field(..., description="Raw phone number string.")
    country: str | None = Field(default=None, description="Optional ISO country hint.")
    default_country: str = Field(default="US", description="Fallback ISO country code.")


class PhoneBatchRequest(BaseModel):
    """Request payload for /v1/batch."""

    phones: list[str] = Field(..., max_length=1000, description="List of raw phone strings.")
    default_country: str = Field(default="US", description="Fallback ISO country code.")


class PhoneCompareRequest(BaseModel):
    """Request payload for /v1/compare."""

    phone_a: str = Field(..., description="First phone number string.")
    phone_b: str = Field(..., description="Second phone number string.")
    country: str | None = Field(default=None, description="Optional ISO country hint.")
    fuzzy_threshold: float = Field(default=0.88, description="Fuzzy similarity threshold (0.0-1.0).")


class PhoneDeduplicateRequest(BaseModel):
    """Request payload for /v1/deduplicate."""

    phones: list[str] = Field(..., max_length=1000, description="List of raw phone strings to cluster.")
    country: str | None = Field(default=None, description="Optional ISO country hint.")
    fuzzy_threshold: float = Field(default=0.88, description="Fuzzy similarity threshold (0.0-1.0).")


class AddressStandardizeRequest(BaseModel):
    """Request payload for /v1/address."""

    street1: str | None = Field(default=None, description="Primary street line.")
    street2: str | None = Field(default=None, description="Secondary unit line.")
    city: str | None = Field(default=None, description="City or locality.")
    state: str | None = Field(default=None, description="State, province, or region.")
    postal_code: str | None = Field(default=None, description="ZIP or postal code.")
    country: str = Field(default="US", description="ISO country code or name.")


class ContactStandardizeRequest(BaseModel):
    """Request payload for /v1/contact (joint Phone + Address cross-healing)."""

    street1: str | None = Field(default=None, description="Primary street line.")
    street2: str | None = Field(default=None, description="Secondary unit line.")
    city: str | None = Field(default=None, description="City or locality.")
    state: str | None = Field(default=None, description="State, province, or region.")
    postal_code: str | None = Field(default=None, description="ZIP or postal code.")
    country: str | None = Field(default=None, description="Optional ISO country hint.")
    phone: str | None = Field(default=None, description="Raw phone number.")
    fax: str | None = Field(default=None, description="Optional raw fax number.")
    default_country: str = Field(default="US", description="Fallback ISO country code.")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="Phone Standardizer API",
        version="1.4.0",
        description="Universal multi-national phone standardization, ITU-T E.164/E.123 formatting, and NANP attribution service.",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "1.4.0"}

    @app.post("/v1/standardize")
    def standardize_endpoint(req: PhoneStandardizeRequest) -> dict[str, Any]:
        res = standardize_phone(
            req.phone,
            country=req.country,
            default_country=req.default_country,
        )
        return res.to_dict()

    @app.post("/v1/explain")
    def explain_endpoint(req: PhoneStandardizeRequest) -> dict[str, Any]:
        return explain_phone(
            req.phone,
            country=req.country,
            default_country=req.default_country,
        )

    @app.post("/v1/compare")
    def compare_endpoint(req: PhoneCompareRequest) -> dict[str, Any]:
        res = compare_phones(
            req.phone_a,
            req.phone_b,
            country=req.country,
            fuzzy_threshold=req.fuzzy_threshold,
        )
        return res.to_dict()

    @app.post("/v1/deduplicate")
    def deduplicate_endpoint(req: PhoneDeduplicateRequest) -> dict[str, Any]:
        clusters = deduplicate_phones(
            req.phones,
            country=req.country,
            fuzzy_threshold=req.fuzzy_threshold,
        )
        return {
            "cluster_count": len(clusters),
            "clusters": [c.to_dict() for c in clusters],
        }

    @app.post("/v1/batch")
    def batch_endpoint(req: PhoneBatchRequest) -> dict[str, Any]:
        results = batch_standardize_phones(req.phones, default_country=req.default_country)
        return {
            "count": len(results),
            "results": [r.to_dict() for r in results],
        }

    @app.get("/v1/countries/{identifier}")
    def country_endpoint(identifier: str) -> dict[str, Any]:
        plan = get_dial_plan(identifier)
        if plan is None:
            raise HTTPException(status_code=404, detail=f"Country '{identifier}' not found")
        return plan.to_dict()

    @app.get("/v1/countries")
    def list_countries_endpoint() -> dict[str, Any]:
        plans = CountryDialRegistry.all_plans()
        return {
            "count": len(plans),
            "countries": [p.to_dict() for p in plans],
        }

    @app.post("/v1/address")
    def address_endpoint(req: AddressStandardizeRequest) -> dict[str, Any]:
        res = standardize_address(
            street1=req.street1,
            street2=req.street2,
            city=req.city,
            state=req.state,
            postal_code=req.postal_code,
            country=req.country,
            allow_locality=True,
        )
        return res.as_dict()

    @app.post("/v1/contact")
    def contact_endpoint(req: ContactStandardizeRequest) -> dict[str, Any]:
        res = standardize_contact(
            street1=req.street1,
            street2=req.street2,
            city=req.city,
            state=req.state,
            postal_code=req.postal_code,
            country=req.country,
            phone=req.phone,
            fax=req.fax,
            default_country=req.default_country,
        )
        return res.to_dict()

    return app


app = create_app()
