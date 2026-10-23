"""Pydantic v2 schemas and validation models for Address-Standardizer.

Enables seamless integration with FastAPI, LangChain, and modern typed Python stacks.
"""

from __future__ import annotations

from typing import Any, List, Optional

try:
    from pydantic import BaseModel, ConfigDict, Field
except ImportError:
    raise ImportError(
        "Pydantic v2 is required to use address_standardizer.schemas. "
        "Install it with: pip install 'address-standardizer[server]'"
    )


class AddressInputSchema(BaseModel):
    """Structured or unstructured address input payload."""

    model_config = ConfigDict(extra="ignore")

    address: Optional[str] = Field(None, description="Unstructured single-line address string")
    street1: Optional[str] = Field(None, description="Primary street line or PO box")
    street2: Optional[str] = Field(None, description="Secondary unit, apt, suite, or building")
    city: Optional[str] = Field(None, description="City, municipality, or locality")
    state: Optional[str] = Field(None, description="State, province, or administrative region")
    postal_code: Optional[str] = Field(None, description="Postal or ZIP code")
    country: Optional[str] = Field("USA", description="ISO country code or name")
    enable_geocoding: bool = Field(False, description="Resolve spatial coordinates")
    enable_reference_validation: bool = Field(False, description="Validate against reference data")
    correct_state_from_zip: bool = Field(False, description="Auto-correct state from postal code")


AddressSchema = AddressInputSchema


class StandardizedAddressPydantic(BaseModel):
    """Pydantic v2 model representing a standardized postal address."""

    model_config = ConfigDict(extra="ignore")

    street1: str
    street2: str = ""
    city: str
    state: str
    postal_code: str
    country: str
    normalized_address_key: Optional[str] = None
    building_key: Optional[str] = None
    address_status: str
    routing_tier: str
    confidence_score: float
    deliverability: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    precision: Optional[str] = None
    accuracy_radius_m: Optional[float] = None
    h3_index_res10: Optional[str] = None
    dpv_footnotes: List[str] = Field(default_factory=list)
    delivery_point_type: Optional[str] = None
    is_vacant: bool = False
    is_registered_agent_hub: bool = False
    is_private_residence: bool = False
    failure_reason_codes: List[str] = Field(default_factory=list)
    suggested_secondary_units: List[str] = Field(default_factory=list)
    secondary_prompt_required: bool = False

    @classmethod
    def from_standardized(cls, std: Any) -> StandardizedAddressPydantic:
        """Create a Pydantic model instance from a StandardizedAddress dataclass."""
        return cls(
            street1=std.street1,
            street2=std.street2,
            city=std.city,
            state=std.state,
            postal_code=std.postal_code,
            country=std.country,
            normalized_address_key=std.normalized_address_key,
            building_key=std.building_key,
            address_status=str(std.address_status.value if hasattr(std.address_status, "value") else std.address_status),
            routing_tier=str(std.routing_tier.value if hasattr(std.routing_tier, "value") else std.routing_tier),
            confidence_score=round(float(std.confidence_score), 4),
            deliverability=str(std.deliverability.value if hasattr(std.deliverability, "value") else std.deliverability),
            latitude=getattr(std, "latitude", None),
            longitude=getattr(std, "longitude", None),
            precision=getattr(std, "precision", None),
            accuracy_radius_m=getattr(std, "accuracy_radius_m", None),
            h3_index_res10=getattr(std, "h3_index_res10", None),
            dpv_footnotes=list(getattr(std, "dpv_footnotes", []) or []),
            delivery_point_type=getattr(std, "delivery_point_type", None),
            is_vacant=getattr(std, "is_vacant", False),
            is_registered_agent_hub=getattr(std, "is_registered_agent_hub", False),
            is_private_residence=getattr(std, "is_private_residence", False),
            failure_reason_codes=list(getattr(std, "failure_reason_codes", []) or []),
            suggested_secondary_units=list(getattr(std, "suggested_secondary_units", []) or []),
            secondary_prompt_required=getattr(std, "secondary_prompt_required", False),
        )


class ValidationResultSchema(BaseModel):
    """Pydantic model representing an address validation outcome."""

    model_config = ConfigDict(extra="ignore")

    is_valid: bool
    deliverability: str
    rejection_reason: Optional[str] = None
    failure_reason_codes: List[str] = Field(default_factory=list)
    confidence_score: float
    routing_tier: str
    standardized_address: Optional[StandardizedAddressPydantic] = None

    @classmethod
    def from_validation_result(cls, res: Any) -> ValidationResultSchema:
        """Create from AddressValidationResult dataclass."""
        std_pydantic = None
        if getattr(res, "standardized_address", None) is not None:
            std_pydantic = StandardizedAddressPydantic.from_standardized(res.standardized_address)

        return cls(
            is_valid=res.is_valid,
            deliverability=res.deliverability,
            rejection_reason=res.rejection_reason,
            failure_reason_codes=list(res.failure_reason_codes),
            confidence_score=res.confidence_score,
            routing_tier=res.routing_tier,
            standardized_address=std_pydantic,
        )
