"""Universal International Address Parsing and Normalization Subsystem."""

from entity_standardizer.address.international.base import (
    CountryGrammar,
    CountryGrammarRegistry,
    ParsedAddressComponents,
    UniversalInternationalGrammar,
    split_intl_secondary_unit,
)
from entity_standardizer.address.international.canada import (
    CanadaGrammar,
    is_valid_canadian_postal_code,
)
from entity_standardizer.address.international.diacritics import (
    CYRILLIC_GREEK_MAP,
    LIGATURE_MAP,
    fold_to_ascii_key,
    normalize_to_canonical_unicode,
)
from entity_standardizer.address.international.germanic import (
    GermanicGrammar,
    is_valid_dutch_postcode,
)
from entity_standardizer.address.international.cjk import CJKGrammar
from entity_standardizer.address.international.latin_america import LatinAmericaGrammar
from entity_standardizer.address.international.eastern_europe import EasternEuropeGrammar
from entity_standardizer.address.international.mena_africa import MenaAfricaGrammar
from entity_standardizer.address.international.offshore import OffshoreGrammar
from entity_standardizer.address.international.romance import RomanceGrammar
from entity_standardizer.address.international.countries import (
    CountryInfo,
    CountryRegistry,
)
from entity_standardizer.address.international.uk import (
    UKGrammar,
    is_valid_uk_postcode,
)
from entity_standardizer.address.international.hong_kong import HongKongGrammar
from entity_standardizer.address.international.singapore import SingaporeGrammar
from entity_standardizer.address.international.southeast_asia import SoutheastAsiaGrammar
from entity_standardizer.address.international.eurasia import EurasiaGrammar
from entity_standardizer.address.international.australia import AustraliaGrammar, NewZealandGrammar
from entity_standardizer.address.international.india import IndiaGrammar
from entity_standardizer.address.international.ireland import (
    IrelandGrammar,
    is_valid_eircode,
    format_eircode,
)
from entity_standardizer.address.international.postal import (
    PostalRule,
    PostalValidationResult,
    extract_postal_code,
    validate_postal_code,
)
from entity_standardizer.address.international.upu import (
    format_upu_address,
)


def register_default_grammars() -> None:
    """Register all standard international localized grammars into CountryGrammarRegistry."""
    CountryGrammarRegistry.register(UKGrammar())
    CountryGrammarRegistry.register(CanadaGrammar())
    CountryGrammarRegistry.register(GermanicGrammar())
    CountryGrammarRegistry.register(RomanceGrammar())
    CountryGrammarRegistry.register(OffshoreGrammar())
    CountryGrammarRegistry.register(CJKGrammar())
    CountryGrammarRegistry.register(LatinAmericaGrammar())
    CountryGrammarRegistry.register(EasternEuropeGrammar())
    CountryGrammarRegistry.register(MenaAfricaGrammar())
    CountryGrammarRegistry.register(HongKongGrammar())
    CountryGrammarRegistry.register(SingaporeGrammar())
    CountryGrammarRegistry.register(SoutheastAsiaGrammar())
    CountryGrammarRegistry.register(EurasiaGrammar())
    CountryGrammarRegistry.register(AustraliaGrammar())
    CountryGrammarRegistry.register(NewZealandGrammar())
    CountryGrammarRegistry.register(IndiaGrammar())
    CountryGrammarRegistry.register(IrelandGrammar())


# Initialize default registry upon module import
register_default_grammars()

__all__ = [
    "CountryGrammar",
    "CountryGrammarRegistry",
    "ParsedAddressComponents",
    "UniversalInternationalGrammar",
    "split_intl_secondary_unit",
    "UKGrammar",
    "is_valid_uk_postcode",
    "CanadaGrammar",
    "is_valid_canadian_postal_code",
    "GermanicGrammar",
    "is_valid_dutch_postcode",
    "RomanceGrammar",
    "OffshoreGrammar",
    "CJKGrammar",
    "LatinAmericaGrammar",
    "EasternEuropeGrammar",
    "MenaAfricaGrammar",
    "HongKongGrammar",
    "SingaporeGrammar",
    "SoutheastAsiaGrammar",
    "EurasiaGrammar",
    "AustraliaGrammar",
    "NewZealandGrammar",
    "IndiaGrammar",
    "IrelandGrammar",
    "is_valid_eircode",
    "format_eircode",
    "LIGATURE_MAP",
    "CYRILLIC_GREEK_MAP",
    "fold_to_ascii_key",
    "normalize_to_canonical_unicode",
    "CountryInfo",
    "CountryRegistry",
    "PostalValidationResult",
    "PostalRule",
    "validate_postal_code",
    "extract_postal_code",
    "format_upu_address",
    "register_default_grammars",
]

