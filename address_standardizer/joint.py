"""Re-export joint Phone + Address entity standardization for address_standardizer."""

from phone_standardizer.joint import (
    CrossHealingAction,
    StandardizedContact,
    StandardizedEntity,
    batch_standardize_contacts,
    batch_standardize_entities,
    standardize_contact,
    standardize_entity,
)

__all__ = [
    "CrossHealingAction",
    "StandardizedContact",
    "StandardizedEntity",
    "batch_standardize_contacts",
    "batch_standardize_entities",
    "standardize_contact",
    "standardize_entity",
]
