"""FastAPI HTTP Microservice for Entity & Phone Standardizer."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from address_standardizer.standardizer import standardize_address
from entity_standardizer.company import compare_companies, standardize_company
from entity_standardizer.person import (
    compare_persons,
    standardize_job_title,
    standardize_person,
)
from entity_standardizer.web import standardize_email, standardize_social, standardize_url
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


class CompanyStandardizeRequest(BaseModel):
    """Request payload for /v1/company."""

    name: str = Field(..., description="Raw organization or company name.")
    country: str | None = Field(default=None, description="Optional ISO country hint.")


class PersonStandardizeRequest(BaseModel):
    """Request payload for /v1/person."""

    name: str = Field(..., description="Raw person full name.")


class JobTitleStandardizeRequest(BaseModel):
    """Request payload for /v1/job-title."""

    title: str = Field(..., description="Raw job title string.")


class CompanyCompareRequest(BaseModel):
    """Request payload for /v1/company/compare."""

    company_a: str = Field(..., description="First organization or company name.")
    company_b: str = Field(..., description="Second organization or company name.")


class PersonCompareRequest(BaseModel):
    """Request payload for /v1/person/compare."""

    person_a: str = Field(..., description="First person full name.")
    person_b: str = Field(..., description="Second person full name.")


class EmailStandardizeRequest(BaseModel):
    """Request payload for /v1/email."""

    email: str = Field(..., description="Raw email address string.")


class UrlStandardizeRequest(BaseModel):
    """Request payload for /v1/url."""

    url: str = Field(..., description="Raw website URL string.")


class SocialStandardizeRequest(BaseModel):
    """Request payload for /v1/social."""

    profile: str = Field(..., description="Raw social URL or @handle string.")
    platform: str | None = Field(default=None, description="Optional social platform hint.")


class ContactStandardizeRequest(BaseModel):
    """Request payload for /v1/contact (joint multi-pillar entity cross-healing)."""

    street1: str | None = Field(default=None, description="Primary street line.")
    street2: str | None = Field(default=None, description="Secondary unit line.")
    city: str | None = Field(default=None, description="City or locality.")
    state: str | None = Field(default=None, description="State, province, or region.")
    postal_code: str | None = Field(default=None, description="ZIP or postal code.")
    country: str | None = Field(default=None, description="Optional ISO country hint.")
    phone: str | None = Field(default=None, description="Raw phone number.")
    fax: str | None = Field(default=None, description="Optional raw fax number.")
    organization: str | None = Field(default=None, description="Optional raw company or organization name.")
    person_name: str | None = Field(default=None, description="Optional raw contact person full name.")
    job_title: str | None = Field(default=None, description="Optional raw contact job title.")
    email: str | None = Field(default=None, description="Optional raw contact email address.")
    website: str | None = Field(default=None, description="Optional raw contact website URL.")
    social: str | None = Field(default=None, description="Optional raw contact social URL or @handle.")
    default_country: str = Field(default="US", description="Fallback ISO country code.")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="Phone Standardizer API",
        version="2.0.0",
        description="Universal multi-national entity, address, phone, company, person, and web standardization service.",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "2.0.0"}

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

    @app.post("/v1/company")
    def company_endpoint(req: CompanyStandardizeRequest) -> dict[str, Any]:
        return standardize_company(req.name, country=req.country).to_dict()

    @app.post("/v1/company/compare")
    def company_compare_endpoint(req: CompanyCompareRequest) -> dict[str, Any]:
        return compare_companies(req.company_a, req.company_b).to_dict()

    @app.post("/v1/person")
    def person_endpoint(req: PersonStandardizeRequest) -> dict[str, Any]:
        return standardize_person(req.name).to_dict()

    @app.post("/v1/person/compare")
    def person_compare_endpoint(req: PersonCompareRequest) -> dict[str, Any]:
        return compare_persons(req.person_a, req.person_b).to_dict()

    @app.post("/v1/job-title")
    def job_title_endpoint(req: JobTitleStandardizeRequest) -> dict[str, Any]:
        return standardize_job_title(req.title).to_dict()

    @app.post("/v1/email")
    def email_endpoint(req: EmailStandardizeRequest) -> dict[str, Any]:
        return standardize_email(req.email).to_dict()

    @app.post("/v1/url")
    def url_endpoint(req: UrlStandardizeRequest) -> dict[str, Any]:
        return standardize_url(req.url).to_dict()

    @app.post("/v1/social")
    def social_endpoint(req: SocialStandardizeRequest) -> dict[str, Any]:
        return standardize_social(req.profile, platform=req.platform).to_dict()

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
            organization=req.organization,
            person_name=req.person_name,
            job_title=req.job_title,
            email=req.email,
            website=req.website,
            social=req.social,
            default_country=req.default_country,
        )
        return res.to_dict()

    return app


app = create_app()
