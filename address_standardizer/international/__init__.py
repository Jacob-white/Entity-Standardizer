"""Universal International Address Parsing and Normalization Subsystem."""

from address_standardizer.international.base import (
    CountryGrammar,
    CountryGrammarRegistry,
    ParsedAddressComponents,
    UniversalInternationalGrammar,
    split_intl_secondary_unit,
)
from address_standardizer.international.canada import (
    CanadaGrammar,
    is_valid_canadian_postal_code,
)
from address_standardizer.international.diacritics import (
    CYRILLIC_GREEK_MAP,
    LIGATURE_MAP,
    fold_to_ascii_key,
    normalize_to_canonical_unicode,
)
from address_standardizer.international.germanic import (
    GermanicGrammar,
    is_valid_dutch_postcode,
)
from address_standardizer.international.cjk import CJKGrammar
from address_standardizer.international.latin_america import LatinAmericaGrammar
from address_standardizer.international.eastern_europe import EasternEuropeGrammar
from address_standardizer.international.mena_africa import MenaAfricaGrammar
from address_standardizer.international.offshore import OffshoreGrammar
from address_standardizer.international.romance import RomanceGrammar
from address_standardizer.international.countries import (
    CountryInfo,
    CountryRegistry,
)
from address_standardizer.international.uk import (
    UKGrammar,
    is_valid_uk_postcode,
)
from address_standardizer.international.hong_kong import HongKongGrammar
from address_standardizer.international.singapore import SingaporeGrammar
from address_standardizer.international.southeast_asia import SoutheastAsiaGrammar
from address_standardizer.international.eurasia import EurasiaGrammar
from address_standardizer.international.australia import AustraliaGrammar, NewZealandGrammar
from address_standardizer.international.india import IndiaGrammar
from address_standardizer.international.ireland import (
    IrelandGrammar,
    is_valid_eircode,
    format_eircode,
)
from address_standardizer.international.postal import (
    PostalRule,
    PostalValidationResult,
    extract_postal_code,
    validate_postal_code,
)
from address_standardizer.international.upu import (
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

