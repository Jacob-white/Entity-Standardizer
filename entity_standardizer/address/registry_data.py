"""
Corporate registry models and the curated registry data (split out of registry.py).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

class RegistryCategory:
    COMMERCIAL_REGISTERED_AGENT = "COMMERCIAL_REGISTERED_AGENT"
    FORMATION_AGENT = "FORMATION_AGENT"
    VIRTUAL_OFFICE = "VIRTUAL_OFFICE"
    MAIL_DROP_CMRA = "MAIL_DROP_CMRA"
    OFFSHORE_SECRECY = "OFFSHORE_SECRECY"
    TRUST_FIDUCIARY_COMPANY = "TRUST_FIDUCIARY_COMPANY"


class CorporateRiskFlag:
    RISK_CRA_CO_LOCATION = "RISK_CRA_CO_LOCATION"
    RISK_VIRTUAL_OFFICE = "RISK_VIRTUAL_OFFICE"
    RISK_CMRA_MAIL_DROP = "RISK_CMRA_MAIL_DROP"
    RISK_OFFSHORE_SECRECY_HUB = "RISK_OFFSHORE_SECRECY_HUB"
    RISK_TRUST_FIDUCIARY = "RISK_TRUST_FIDUCIARY"
    RISK_MISSING_SECONDARY_AT_HUB = "RISK_MISSING_SECONDARY_AT_HUB"
    RISK_DISGUISED_PMB = "RISK_DISGUISED_PMB"
    RISK_RESIDENTIAL_COMMERCIAL = "RISK_RESIDENTIAL_COMMERCIAL"


@dataclass
class CorporateRegistryEntry:
    """Detailed metadata for a curated formation hub, registered agent, or virtual office."""
    provider_name: str
    category: str
    street_patterns: List[str]
    city: str
    state: str
    postal_code: str
    country: str = "USA"
    base_risk_score: float = 0.85
    estimated_entities: int = 10000
    notes: str = ""
    aliases: List[str] = field(default_factory=list)
    requires_secondary_match: bool = False
    mandatory_unit_patterns: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "category": self.category,
            "street_patterns": list(self.street_patterns),
            "city": self.city,
            "state": self.state,
            "postal_code": self.postal_code,
            "country": self.country,
            "base_risk_score": self.base_risk_score,
            "estimated_entities": self.estimated_entities,
            "notes": self.notes,
            "aliases": list(self.aliases),
            "requires_secondary_match": self.requires_secondary_match,
            "mandatory_unit_patterns": list(self.mandatory_unit_patterns),
        }


# ---------------------------------------------------------------------------
# Master Curated Corporate Registry
# ---------------------------------------------------------------------------

CURATED_CORPORATE_REGISTRY: List[CorporateRegistryEntry] = [
    # 1. Corporation Trust Center (CT Corporation / Wolters Kluwer) - Premier DE Hub
    CorporateRegistryEntry(
        provider_name="Corporation Trust Center (CT Corporation)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["1209 N ORANGE", "1209 NORTH ORANGE"],
        city="WILMINGTON",
        state="DE",
        postal_code="19801",
        country="USA",
        base_risk_score=0.95,
        estimated_entities=300000,
        notes="Primary US registered agent corporate secrecy hub.",
        aliases=["CT CORPORATION", "CORPORATION TRUST CO"],
    ),
    # 2. National Registered Agents, Inc. (NRAI / CT Corp) - Dover DE
    CorporateRegistryEntry(
        provider_name="National Registered Agents, Inc. (NRAI)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["160 GREENTREE"],
        city="DOVER",
        state="DE",
        postal_code="19904",
        country="USA",
        base_risk_score=0.85,
        estimated_entities=50000,
        notes="Major Delaware commercial formation hub.",
    ),
    # 3. Corporation Service Company (CSC Global HQ) - Wilmington DE
    CorporateRegistryEntry(
        provider_name="Corporation Service Company (CSC Global HQ)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["251 LITTLE FALLS"],
        city="WILMINGTON",
        state="DE",
        postal_code="19808",
        country="USA",
        base_risk_score=0.90,
        estimated_entities=200000,
        notes="Global headquarters of Corporation Service Company.",
        aliases=["CSC", "CSC GLOBAL"],
    ),
    # 4. Corporation Service Company (CSC Legacy) - Wilmington DE
    CorporateRegistryEntry(
        provider_name="Corporation Service Company (CSC Centerville)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["2711 CENTERVILLE"],
        city="WILMINGTON",
        state="DE",
        postal_code="19808",
        country="USA",
        base_risk_score=0.90,
        estimated_entities=150000,
        notes="CSC Centerville Road corporate office hub.",
        aliases=["CSC"],
    ),
    # 5. Cogency Global (formerly National Corporate Research) - Dover DE
    CorporateRegistryEntry(
        provider_name="Cogency Global",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["850 NEW BURTON"],
        city="DOVER",
        state="DE",
        postal_code="19904",
        country="USA",
        base_risk_score=0.85,
        estimated_entities=40000,
        notes="Major commercial registered agent hub.",
    ),
    # 6. The Corporation Trust Company - West Trenton NJ
    CorporateRegistryEntry(
        provider_name="The Corporation Trust Company (NJ)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["820 BEAR TAVERN"],
        city="TRENTON",
        state="NJ",
        postal_code="08628",
        country="USA",
        base_risk_score=0.80,
        estimated_entities=25000,
        notes="New Jersey corporate filing and registered agent hub.",
    ),
    # 7. Harvard Business Services - Lewes DE
    CorporateRegistryEntry(
        provider_name="Harvard Business Services",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["16192 COASTAL"],
        city="LEWES",
        state="DE",
        postal_code="19958",
        country="USA",
        base_risk_score=0.90,
        estimated_entities=250000,
        notes="High-volume online Delaware incorporation mill and registered agent.",
    ),
    # 8. Registered Agents Inc. - Sheridan WY
    CorporateRegistryEntry(
        provider_name="Registered Agents Inc. (Wyoming Privacy Hub)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["30 N GOULD", "30 NORTH GOULD"],
        city="SHERIDAN",
        state="WY",
        postal_code="82801",
        country="USA",
        base_risk_score=0.95,
        estimated_entities=100000,
        notes="Premier Wyoming privacy formation hub hosting crypto, LLCs, and shells.",
    ),
    # 9. Registered Agents Inc. - Dover DE
    CorporateRegistryEntry(
        provider_name="Registered Agents Inc. (Delaware)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["3500 S DUPONT", "3500 SOUTH DUPONT"],
        city="DOVER",
        state="DE",
        postal_code="19901",
        country="USA",
        base_risk_score=0.85,
        estimated_entities=60000,
        notes="High-volume Delaware registered agent hub.",
    ),
    # 10. Incorp Services - Las Vegas NV
    CorporateRegistryEntry(
        provider_name="Incorp Services",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["3773 HOWARD HUGHES"],
        city="LAS VEGAS",
        state="NV",
        postal_code="89169",
        country="USA",
        base_risk_score=0.85,
        estimated_entities=35000,
        notes="Nevada corporate formation and registered agent center.",
    ),
    # 11. Northwest Registered Agent - Spokane WA
    CorporateRegistryEntry(
        provider_name="Northwest Registered Agent (HQ)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["522 W RIVERSIDE", "522 WEST RIVERSIDE"],
        city="SPOKANE",
        state="WA",
        postal_code="99201",
        country="USA",
        base_risk_score=0.85,
        estimated_entities=75000,
        notes="Northwest Registered Agent national headquarters.",
    ),
    # 12. Northwest Registered Agent - St Petersburg FL
    CorporateRegistryEntry(
        provider_name="Northwest Registered Agent (Florida)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["7901 4TH ST N", "7901 4TH STREET N"],
        city="ST PETERSBURG",
        state="FL",
        postal_code="33702",
        country="USA",
        base_risk_score=0.85,
        estimated_entities=45000,
        notes="Florida high-volume corporate registered agent hub.",
    ),
    # 13. Northwest Registered Agent - Wilmington DE
    CorporateRegistryEntry(
        provider_name="Northwest Registered Agent (Delaware)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["300 DELAWARE"],
        city="WILMINGTON",
        state="DE",
        postal_code="19801",
        country="USA",
        base_risk_score=0.85,
        estimated_entities=40000,
        notes="Delaware corporate office hub.",
    ),
    # 14. CT Corporation - New York NY (Fosun Plaza / 28 Liberty)
    CorporateRegistryEntry(
        provider_name="CT Corporation (New York)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["28 LIBERTY"],
        city="NEW YORK",
        state="NY",
        postal_code="10005",
        country="USA",
        base_risk_score=0.85,
        estimated_entities=60000,
        notes="Major commercial registered agent hub in Manhattan financial district.",
        requires_secondary_match=True,
        mandatory_unit_patterns=["FL 42", "STE 4200", "42ND FL", "42 FL", "FLOOR 42", "SUITE 4200", "#4200"],
    ),
    # 15. CT Corporation - Chicago IL
    CorporateRegistryEntry(
        provider_name="CT Corporation (Illinois)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["208 S LASALLE", "208 SOUTH LASALLE"],
        city="CHICAGO",
        state="IL",
        postal_code="60604",
        country="USA",
        base_risk_score=0.80,
        estimated_entities=40000,
        notes="Illinois commercial registered agent hub.",
    ),
    # 16. CT Corporation - Plantation FL
    CorporateRegistryEntry(
        provider_name="CT Corporation (Florida)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["1200 S PINE ISLAND", "1200 SOUTH PINE ISLAND"],
        city="PLANTATION",
        state="FL",
        postal_code="33324",
        country="USA",
        base_risk_score=0.80,
        estimated_entities=50000,
        notes="Florida commercial registered agent hub.",
    ),
    # 17. CT Corporation - Glendale CA
    CorporateRegistryEntry(
        provider_name="CT Corporation (California)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["330 N BRAND", "330 NORTH BRAND"],
        city="GLENDALE",
        state="CA",
        postal_code="91203",
        country="USA",
        base_risk_score=0.80,
        estimated_entities=45000,
        notes="California commercial registered agent hub.",
    ),
    # 18. CSC Global - Albany NY
    CorporateRegistryEntry(
        provider_name="Corporation Service Company (Albany NY)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["80 STATE"],
        city="ALBANY",
        state="NY",
        postal_code="12207",
        country="USA",
        base_risk_score=0.85,
        estimated_entities=70000,
        notes="CSC New York state capital corporate hub.",
    ),
    # 19. Registered Agents Inc. - Albany NY
    CorporateRegistryEntry(
        provider_name="Registered Agents Inc. (Albany NY)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["90 STATE"],
        city="ALBANY",
        state="NY",
        postal_code="12207",
        country="USA",
        base_risk_score=0.85,
        estimated_entities=50000,
        notes="Registered Agents Inc. New York corporate hub.",
    ),
    # 20. Registered Agents Inc. - Buffalo WY
    CorporateRegistryEntry(
        provider_name="Registered Agents Inc. (Buffalo WY)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["412 N MAIN", "412 NORTH MAIN"],
        city="BUFFALO",
        state="WY",
        postal_code="82834",
        country="USA",
        base_risk_score=0.85,
        estimated_entities=25000,
        notes="Wyoming secondary registered agent and formation hub.",
    ),
    # 21. LegalZoom / Business Filings Inc. - Glendale CA
    CorporateRegistryEntry(
        provider_name="LegalZoom (Corporate Headquarters)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["101 N BRAND", "101 NORTH BRAND"],
        city="GLENDALE",
        state="CA",
        postal_code="91203",
        country="USA",
        base_risk_score=0.85,
        estimated_entities=150000,
        notes="LegalZoom headquarters and registered agent center.",
    ),
    # 22. LegalZoom - Austin TX
    CorporateRegistryEntry(
        provider_name="LegalZoom / Incorp (Austin TX)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["9900 SPECTRUM"],
        city="AUSTIN",
        state="TX",
        postal_code="78717",
        country="USA",
        base_risk_score=0.85,
        estimated_entities=80000,
        notes="Texas corporate formation and registered agent center.",
    ),
    # 23. Cogency Global - New York NY
    CorporateRegistryEntry(
        provider_name="Cogency Global (New York HQ)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["10 E 40TH", "10 EAST 40TH"],
        city="NEW YORK",
        state="NY",
        postal_code="10016",
        country="USA",
        base_risk_score=0.80,
        estimated_entities=30000,
        notes="Manhattan registered agent headquarters.",
    ),
    # 24. NRAI - Columbus OH
    CorporateRegistryEntry(
        provider_name="National Registered Agents (Ohio)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["4400 EASTON COMMONS"],
        city="COLUMBUS",
        state="OH",
        postal_code="43219",
        country="USA",
        base_risk_score=0.80,
        estimated_entities=25000,
        notes="Ohio commercial registered agent center.",
    ),
    # 25. NRAI - Dallas TX
    CorporateRegistryEntry(
        provider_name="National Registered Agents (Texas)",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["1999 BRYAN"],
        city="DALLAS",
        state="TX",
        postal_code="75201",
        country="USA",
        base_risk_score=0.80,
        estimated_entities=35000,
        notes="Texas commercial registered agent hub.",
    ),
    # 26. Regus Virtual Office - 245 Park Ave NY
    CorporateRegistryEntry(
        provider_name="Regus / IWG (245 Park Ave)",
        category=RegistryCategory.VIRTUAL_OFFICE,
        street_patterns=["245 PARK"],
        city="NEW YORK",
        state="NY",
        postal_code="10167",
        country="USA",
        base_risk_score=0.70,
        estimated_entities=15000,
        notes="Commercial virtual office mail drop hosting thousands of shell businesses.",
        requires_secondary_match=True,
        mandatory_unit_patterns=["FL 39", "STE 3900", "39TH FL", "39 FL", "FLOOR 39", "SUITE 3900", "#3900"],
    ),
    # 27. Regus Virtual Office - 100 Park Ave NY
    CorporateRegistryEntry(
        provider_name="Regus / IWG (100 Park Ave)",
        category=RegistryCategory.VIRTUAL_OFFICE,
        street_patterns=["100 PARK"],
        city="NEW YORK",
        state="NY",
        postal_code="10017",
        country="USA",
        base_risk_score=0.70,
        estimated_entities=12000,
        notes="Commercial virtual office and corporate mail drop.",
        requires_secondary_match=True,
        mandatory_unit_patterns=["FL 16", "STE 1600", "16TH FL", "16 FL", "FLOOR 16", "SUITE 1600", "#1600"],
    ),
    # 28. Regus Virtual Office - 100 S Biscayne Blvd Miami FL
    CorporateRegistryEntry(
        provider_name="Regus Virtual Office (Miami Financial District)",
        category=RegistryCategory.VIRTUAL_OFFICE,
        street_patterns=["100 S BISCAYNE", "100 SOUTH BISCAYNE"],
        city="MIAMI",
        state="FL",
        postal_code="33131",
        country="USA",
        base_risk_score=0.75,
        estimated_entities=18000,
        notes="Downtown Miami virtual office hosting offshore and LATAM corporate entities.",
    ),
    # 29. Regus Virtual Office - 101 California St San Francisco CA
    CorporateRegistryEntry(
        provider_name="Regus / IWG (101 California St)",
        category=RegistryCategory.VIRTUAL_OFFICE,
        street_patterns=["101 CALIFORNIA"],
        city="SAN FRANCISCO",
        state="CA",
        postal_code="94111",
        country="USA",
        base_risk_score=0.70,
        estimated_entities=10000,
        notes="Financial district corporate virtual office.",
        requires_secondary_match=True,
        mandatory_unit_patterns=["FL 27", "STE 2700", "27TH FL", "27 FL", "FLOOR 27", "SUITE 2700", "#2700"],
    ),
    # 30. Regus Virtual Office - 200 S Wacker Dr Chicago IL
    CorporateRegistryEntry(
        provider_name="Regus / IWG (200 S Wacker)",
        category=RegistryCategory.VIRTUAL_OFFICE,
        street_patterns=["200 S WACKER", "200 SOUTH WACKER"],
        city="CHICAGO",
        state="IL",
        postal_code="60606",
        country="USA",
        base_risk_score=0.70,
        estimated_entities=12000,
        notes="Chicago financial center virtual office.",
        requires_secondary_match=True,
        mandatory_unit_patterns=["FL 31", "STE 3100", "31ST FL", "31 FL", "FLOOR 31", "SUITE 3100", "#3100"],
    ),
    # 31. WeWork Corporate Mail Drop - 115 W 18th St NY
    CorporateRegistryEntry(
        provider_name="WeWork Corporate Mail Drop (Chelsea)",
        category=RegistryCategory.VIRTUAL_OFFICE,
        street_patterns=["115 W 18TH", "115 WEST 18TH"],
        city="NEW YORK",
        state="NY",
        postal_code="10011",
        country="USA",
        base_risk_score=0.65,
        estimated_entities=8000,
        notes="WeWork corporate business address and mail handling center.",
    ),
    # 32. WeWork Corporate Mail Drop - 500 7th Ave NY
    CorporateRegistryEntry(
        provider_name="WeWork Corporate Mail Drop (Midtown)",
        category=RegistryCategory.VIRTUAL_OFFICE,
        street_patterns=["500 7TH", "500 SEVENTH"],
        city="NEW YORK",
        state="NY",
        postal_code="10018",
        country="USA",
        base_risk_score=0.65,
        estimated_entities=9000,
        notes="Multi-tenant commercial shared workspace and corporate address.",
    ),
    # 33. WeWork Corporate Mail Drop - 600 California St SF
    CorporateRegistryEntry(
        provider_name="WeWork Corporate Mail Drop (San Francisco)",
        category=RegistryCategory.VIRTUAL_OFFICE,
        street_patterns=["600 CALIFORNIA"],
        city="SAN FRANCISCO",
        state="CA",
        postal_code="94108",
        country="USA",
        base_risk_score=0.65,
        estimated_entities=7500,
        notes="San Francisco financial hub mail forwarding facility.",
    ),
    # 34. DaVinci Virtual Office Solutions - 275 Madison Ave NY
    CorporateRegistryEntry(
        provider_name="DaVinci Virtual Offices (275 Madison Ave)",
        category=RegistryCategory.VIRTUAL_OFFICE,
        street_patterns=["275 MADISON"],
        city="NEW YORK",
        state="NY",
        postal_code="10016",
        country="USA",
        base_risk_score=0.75,
        estimated_entities=14000,
        notes="Dedicated virtual office mail drop and telephone answering provider.",
    ),
    # 35. Opus Virtual Offices - 777 Yamato Rd Boca Raton FL
    CorporateRegistryEntry(
        provider_name="Opus Virtual Offices (Headquarters)",
        category=RegistryCategory.VIRTUAL_OFFICE,
        street_patterns=["777 YAMATO"],
        city="BOCA RATON",
        state="FL",
        postal_code="33431",
        country="USA",
        base_risk_score=0.75,
        estimated_entities=16000,
        notes="National virtual office headquarters and corporate mail forwarder.",
    ),
    # 36. Alliance Virtual Offices - 1221 Brickell Ave Miami FL
    CorporateRegistryEntry(
        provider_name="Alliance Virtual Offices (Brickell)",
        category=RegistryCategory.VIRTUAL_OFFICE,
        street_patterns=["1221 BRICKELL"],
        city="MIAMI",
        state="FL",
        postal_code="33131",
        country="USA",
        base_risk_score=0.75,
        estimated_entities=11000,
        notes="International virtual office and business address solution.",
        requires_secondary_match=True,
        mandatory_unit_patterns=["FL 9", "STE 900", "9TH FL", "9 FL", "FLOOR 9", "SUITE 900", "#900"],
    ),
    # 37. Nevada Corporate Headquarters - Las Vegas NV
    CorporateRegistryEntry(
        provider_name="Nevada Corporate Headquarters",
        category=RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        street_patterns=["4730 S FORT APACHE", "4730 SOUTH FORT APACHE"],
        city="LAS VEGAS",
        state="NV",
        postal_code="89147",
        country="USA",
        base_risk_score=0.85,
        estimated_entities=20000,
        notes="Nevada asset protection and incorporation service hub.",
    ),
    # 38. Ugland House - Grand Cayman (World's Most Famous Offshore Secrecy Hub)
    CorporateRegistryEntry(
        provider_name="Ugland House (Maples Group)",
        category=RegistryCategory.OFFSHORE_SECRECY,
        street_patterns=["UGLAND HOUSE", "SOUTH CHURCH ST", "PO BOX 309"],
        city="GEORGE TOWN",
        state="",
        postal_code="KY1-1104",
        country="CYM",
        base_risk_score=0.98,
        estimated_entities=18000,
        notes="Ugland House: Premier Cayman offshore hedge fund and shell company hub.",
        aliases=["MAPLES AND CALDER", "UGLAND", "MAPLES GROUP"],
    ),
    # 39. Clifton House - Grand Cayman
    CorporateRegistryEntry(
        provider_name="Clifton House (Appleby)",
        category=RegistryCategory.OFFSHORE_SECRECY,
        street_patterns=["CLIFTON HOUSE", "75 FORT ST", "PO BOX 190"],
        city="GEORGE TOWN",
        state="",
        postal_code="KY1-1104",
        country="CYM",
        base_risk_score=0.95,
        estimated_entities=12000,
        notes="Appleby global offshore legal and corporate service hub.",
        aliases=["APPLEBY"],
    ),
    # 40. 190 Elgin Ave - Grand Cayman (Walkers)
    CorporateRegistryEntry(
        provider_name="190 Elgin Avenue (Walkers)",
        category=RegistryCategory.OFFSHORE_SECRECY,
        street_patterns=["190 ELGIN", "PO BOX 9001"],
        city="GEORGE TOWN",
        state="",
        postal_code="KY1-9001",
        country="CYM",
        base_risk_score=0.95,
        estimated_entities=15000,
        notes="Walkers law firm offshore fund and corporate secrecy center.",
        aliases=["WALKERS"],
    ),
    # 41. Craigmuir Chambers - British Virgin Islands (Tortola)
    CorporateRegistryEntry(
        provider_name="Craigmuir Chambers (Harneys)",
        category=RegistryCategory.OFFSHORE_SECRECY,
        street_patterns=["CRAIGMUIR CHAMBERS", "PO BOX 71"],
        city="ROAD TOWN",
        state="TORTOLA",
        postal_code="VG1110",
        country="VGB",
        base_risk_score=0.98,
        estimated_entities=25000,
        notes="BVI Harneys offshore formation hub hosting tens of thousands of IBCs.",
        aliases=["HARNEYS"],
    ),
    # 42. Wickhams Cay - British Virgin Islands (Tortola)
    CorporateRegistryEntry(
        provider_name="Wickhams Cay (Trident Chambers)",
        category=RegistryCategory.OFFSHORE_SECRECY,
        street_patterns=["WICKHAMS CAY", "TRIDENT CHAMBERS"],
        city="ROAD TOWN",
        state="",
        postal_code="VG1110",
        country="VGB",
        base_risk_score=0.98,
        estimated_entities=30000,
        notes="Major BVI commercial secrecy and registered agent hub.",
        aliases=["TRIDENT TRUST", "TRIDENT CHAMBERS"],
    ),
    # 43. Clarendon House - Bermuda (Conyers)
    CorporateRegistryEntry(
        provider_name="Clarendon House (Conyers)",
        category=RegistryCategory.OFFSHORE_SECRECY,
        street_patterns=["CLARENDON HOUSE", "2 CHURCH ST", "2 CHURCH STREET"],
        city="HAMILTON",
        state="",
        postal_code="HM 11",
        country="BMU",
        base_risk_score=0.95,
        estimated_entities=14000,
        notes="Bermuda premier offshore legal and formation complex.",
        aliases=["CONYERS", "CONYERS DILL & PEARMAN"],
    ),
    # 44. Calle 50 / Mossack Complex - Panama City, Panama
    CorporateRegistryEntry(
        provider_name="Calle 50 Corporate Financial Center (Panama)",
        category=RegistryCategory.OFFSHORE_SECRECY,
        street_patterns=["CALLE 50", "EDIFICIO ARANGO ORILLAC", "EDIF. ARANGO ORILLAC", "ARANGO ORILLAC"],
        city="PANAMA CITY",
        state="",
        postal_code="",
        country="PAN",
        base_risk_score=0.95,
        estimated_entities=20000,
        notes="Historic Panamanian secrecy and offshore corporate formation district.",
        aliases=["MOSSACK FONSECA", "ARANGO ORILLAC"],
    ),
    # 45. Shelton Street Companies Hub - London, UK (Companies Made Simple)
    CorporateRegistryEntry(
        provider_name="Shelton Street Companies Hub",
        category=RegistryCategory.FORMATION_AGENT,
        street_patterns=["71-75 SHELTON", "71 - 75 SHELTON", "71/75 SHELTON", "71-75 SHELTON ST", "71-75 SHELTON STREET"],
        city="LONDON",
        state="",
        postal_code="WC2H 9JQ",
        country="GBR",
        base_risk_score=0.92,
        estimated_entities=95000,
        notes="London premier company secretarial and formation mill (Companies Made Simple).",
        aliases=["COMPANIES MADE SIMPLE", "MADE SIMPLE GROUP"],
    ),
    # 46. Wenlock Road Registered Hub - London, UK (1st Formations)
    CorporateRegistryEntry(
        provider_name="Wenlock Road Registered Hub",
        category=RegistryCategory.FORMATION_AGENT,
        street_patterns=["20-22 WENLOCK", "20 - 22 WENLOCK", "20/22 WENLOCK", "20-22 WENLOCK RD", "20-22 WENLOCK ROAD"],
        city="LONDON",
        state="",
        postal_code="N1 7GU",
        country="GBR",
        base_risk_score=0.90,
        estimated_entities=65000,
        notes="Major London statutory corporate incorporation hub (1st Formations).",
        aliases=["1ST FORMATIONS", "COMPLETE FORMATIONS"],
    ),
    # 47. Old Gloucester Street Mail Drop - London, UK (British Monomarks)
    CorporateRegistryEntry(
        provider_name="Old Gloucester Street Mail Drop",
        category=RegistryCategory.MAIL_DROP_CMRA,
        street_patterns=["27 OLD GLOUCESTER", "27 OLD GLOUCESTER ST", "27 OLD GLOUCESTER STREET"],
        city="LONDON",
        state="",
        postal_code="WC1N 3AX",
        country="GBR",
        base_risk_score=0.90,
        estimated_entities=45000,
        notes="High-volume London commercial mail receiving agency and accommodation address.",
        aliases=["BRITISH MONOMARKS", "HOLD THE MAIL"],
    ),
    # 48. Keizersgracht Trust District - Amsterdam, Netherlands
    CorporateRegistryEntry(
        provider_name="Keizersgracht Trust District",
        category=RegistryCategory.TRUST_FIDUCIARY_COMPANY,
        street_patterns=["KEIZERSGRACHT 421", "KEIZERSGRACHT 62", "421 KEIZERSGRACHT", "62 KEIZERSGRACHT"],
        city="AMSTERDAM",
        state="",
        postal_code="1016 EK",
        country="NLD",
        base_risk_score=0.88,
        estimated_entities=10000,
        notes="Amsterdam historic canal trust office hub hosting corporate holdings and SPVs.",
        aliases=["AMSTERDAM TRUST HUB"],
    ),
    # 49. Boulevard Royal Financial Hub - Luxembourg
    CorporateRegistryEntry(
        provider_name="Boulevard Royal Financial Hub",
        category=RegistryCategory.TRUST_FIDUCIARY_COMPANY,
        street_patterns=["25A BOULEVARD ROYAL", "25A BLVD ROYAL", "25 A BOULEVARD ROYAL", "25 A BLVD ROYAL", "25A BD ROYAL", "BOULEVARD ROYAL 25A", "BLVD ROYAL 25A"],
        city="LUXEMBOURG",
        state="",
        postal_code="L-2449",
        country="LUX",
        base_risk_score=0.90,
        estimated_entities=8000,
        notes="Luxembourg premier fiduciary financial district and corporate domicile center.",
        aliases=["LUXEMBOURG FIDUCIARY HUB"],
    ),
    # 50. Baarerstrasse "Crypto Valley" - Zug, Switzerland
    CorporateRegistryEntry(
        provider_name='Baarerstrasse "Crypto Valley"',
        category=RegistryCategory.TRUST_FIDUCIARY_COMPANY,
        street_patterns=["BAARERSTRASSE 82", "BAARERSTR. 82", "BAARER STRASSE 82", "BAARERSTR 82"],
        city="ZUG",
        state="",
        postal_code="6300",
        country="CHE",
        base_risk_score=0.92,
        estimated_entities=12000,
        notes="Zug Crypto Valley corporate domicile and trust services cluster.",
        aliases=["CRYPTO VALLEY ZUG", "REGSERVICES"],
    ),
    # 51. International Financial Services - Dublin, Ireland (IFSC)
    CorporateRegistryEntry(
        provider_name="International Financial Services (IFSC)",
        category=RegistryCategory.TRUST_FIDUCIARY_COMPANY,
        street_patterns=["1 IFC", "1 IFSC", "CUSTOM HOUSE DOCK", "ONE IFSC", "ONE IFC", "1 INTERNATIONAL FINANCIAL SERVICES CENTRE"],
        city="DUBLIN",
        state="",
        postal_code="D01",
        country="IRL",
        base_risk_score=0.85,
        estimated_entities=15000,
        notes="Dublin International Financial Services Centre (IFSC) corporate SPV hub.",
        aliases=["IFSC DUBLIN", "CUSTOM HOUSE DOCK"],
    ),
    # 52. Marina Bay / Raffles Virtual Hub - Singapore
    CorporateRegistryEntry(
        provider_name="Marina Bay / Raffles Virtual Hub",
        category=RegistryCategory.VIRTUAL_OFFICE,
        street_patterns=["1 RAFFLES PL", "1 RAFFLES PLACE", "ONE RAFFLES PLACE", "ONE RAFFLES PL", "MARINA BAY FINANCIAL", "MARINA BAY FINANCIAL CENTRE"],
        city="SINGAPORE",
        state="",
        postal_code="048616",
        country="SGP",
        base_risk_score=0.85,
        estimated_entities=20000,
        notes="Singapore financial district premier virtual office and corporate secretarial complex.",
        aliases=["ONE RAFFLES PLACE", "MARINA BAY"],
    ),
    CorporateRegistryEntry(
        provider_name="Earth Class Mail Digital Hub",
        category=RegistryCategory.MAIL_DROP_CMRA,
        street_patterns=["277 4TH AVE"],
        city="BROOKLYN",
        state="NY",
        postal_code="11215",
        base_risk_score=0.75,
        estimated_entities=15000,
        notes="High-volume commercial mail receiving agency and scanning service.",
    ),
    CorporateRegistryEntry(
        provider_name="iPostal1 / Anytime Mailbox Hub",
        category=RegistryCategory.MAIL_DROP_CMRA,
        street_patterns=["1321 UPLAND DR"],
        city="HOUSTON",
        state="TX",
        postal_code="77043",
        base_risk_score=0.75,
        estimated_entities=25000,
        notes="Nationwide virtual mailbox and re-mailing commercial facility.",
    ),
]
