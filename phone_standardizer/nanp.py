"""North American Numbering Plan (NANP +1) Jurisdiction, State, Province, and Service Code Resolver.

Maps 3-digit NANP Area Codes (NPA) to their exact ISO-3166-1 country/territory
(across all 25 NANP jurisdictions) and US State / Canadian Province code.
"""

from __future__ import annotations

NANP_TOLL_FREE_NPAS: frozenset[str] = frozenset({
    "800", "833", "844", "855", "866", "877", "888",
})

NANP_PREMIUM_NPAS: frozenset[str] = frozenset({"900"})

NANP_PERSONAL_NPAS: frozenset[str] = frozenset({
    "500", "521", "522", "533", "544", "566", "577", "588",
})

NANP_SHORT_CODES: frozenset[str] = frozenset({
    "211", "311", "411", "511", "611", "711", "811", "911", "988",
    "116111", "116123",
})

NANP_EMERGENCY_CODES: frozenset[str] = frozenset({
    "000", "01", "011", "019", "060", "085",
    "100", "101", "10111", "102", "104", "105",
    "110", "111", "112", "113", "114", "115", "117", "118", "119",
    "122", "128", "13", "130", "131", "14", "1444",
    "15", "16", "17", "18",
    "190", "191", "192", "193", "197", "199",
    "333", "355", "555",
    "90", "91", "911", "919", "92", "93", "988", "990", "991", "993", "996", "999",
})

# Non-US/CA NANP Countries & Territories mapped by 3-digit NPA
NANP_CARIBBEAN_PACIFIC_NPA_TO_ISO2: dict[str, tuple[str, str]] = {
    "242": ("BS", "BS"),  # Bahamas
    "246": ("BB", "BB"),  # Barbados
    "264": ("AI", "AI"),  # Anguilla
    "268": ("AG", "AG"),  # Antigua and Barbuda
    "284": ("VG", "VG"),  # British Virgin Islands
    "340": ("VI", "VI"),  # U.S. Virgin Islands
    "345": ("KY", "KY"),  # Cayman Islands
    "441": ("BM", "BM"),  # Bermuda
    "473": ("GD", "GD"),  # Grenada
    "649": ("TC", "TC"),  # Turks and Caicos Islands
    "658": ("JM", "JM"),  # Jamaica
    "664": ("MS", "MS"),  # Montserrat
    "670": ("MP", "MP"),  # Northern Mariana Islands
    "671": ("GU", "GU"),  # Guam
    "684": ("AS", "AS"),  # American Samoa
    "721": ("SX", "SX"),  # Sint Maarten
    "758": ("LC", "LC"),  # Saint Lucia
    "767": ("DM", "DM"),  # Dominica
    "784": ("VC", "VC"),  # Saint Vincent and the Grenadines
    "787": ("PR", "PR"),  # Puerto Rico
    "809": ("DO", "DO"),  # Dominican Republic
    "829": ("DO", "DO"),  # Dominican Republic
    "849": ("DO", "DO"),  # Dominican Republic
    "868": ("TT", "TT"),  # Trinidad and Tobago
    "869": ("KN", "KN"),  # Saint Kitts and Nevis
    "876": ("JM", "JM"),  # Jamaica
    "939": ("PR", "PR"),  # Puerto Rico
}

NANP_JURISDICTIONS: frozenset[str] = frozenset(
    {"US", "CA", "UM"} | {iso2 for iso2, _ in NANP_CARIBBEAN_PACIFIC_NPA_TO_ISO2.values()}
)

# Canadian Provinces & Territories mapped by 3-digit NPA
NANP_CANADA_NPA_TO_PROVINCE: dict[str, str] = {
    "204": "MB", "431": "MB", "584": "MB",
    "226": "ON", "249": "ON", "273": "ON", "289": "ON", "343": "ON", "365": "ON",
    "382": "ON", "416": "ON", "437": "ON", "519": "ON", "548": "ON",
    "613": "ON", "647": "ON", "683": "ON", "705": "ON", "742": "ON",
    "753": "ON", "807": "ON", "905": "ON", "942": "ON",
    "236": "BC", "250": "BC", "257": "BC", "604": "BC", "672": "BC", "778": "BC",
    "263": "QC", "354": "QC", "367": "QC", "418": "QC", "438": "QC",
    "450": "QC", "468": "QC", "514": "QC", "579": "QC", "581": "QC",
    "819": "QC", "873": "QC",
    "306": "SK", "474": "SK", "639": "SK",
    "368": "AB", "403": "AB", "587": "AB", "780": "AB", "825": "AB",
    "506": "NB", "428": "NB",
    "709": "NL", "879": "NL",
    "782": "NS", "902": "NS",
    "867": "YT",
}

# Major US States & DC mapped by 3-digit NPA
NANP_US_NPA_TO_STATE: dict[str, str] = {
    "201": "NJ", "551": "NJ", "609": "NJ", "640": "NJ", "732": "NJ", "848": "NJ", "856": "NJ", "862": "NJ", "908": "NJ", "973": "NJ",
    "202": "DC", "771": "DC",
    "203": "CT", "475": "CT", "860": "CT", "959": "CT",
    "205": "AL", "251": "AL", "256": "AL", "334": "AL", "659": "AL", "938": "AL",
    "206": "WA", "253": "WA", "360": "WA", "425": "WA", "509": "WA", "564": "WA",
    "207": "ME",
    "208": "ID", "986": "ID",
    "209": "CA", "213": "CA", "279": "CA", "310": "CA", "323": "CA", "341": "CA", "350": "CA", "369": "CA", "408": "CA", "415": "CA", "424": "CA",
    "442": "CA", "510": "CA", "526": "CA", "530": "CA", "559": "CA", "562": "CA", "619": "CA", "626": "CA", "628": "CA", "650": "CA",
    "657": "CA", "661": "CA", "669": "CA", "707": "CA", "714": "CA", "738": "CA", "747": "CA", "760": "CA", "805": "CA", "818": "CA",
    "820": "CA", "831": "CA", "840": "CA", "858": "CA", "909": "CA", "916": "CA", "925": "CA", "949": "CA", "951": "CA",
    "210": "TX", "214": "TX", "254": "TX", "281": "TX", "325": "TX", "346": "TX", "361": "TX", "409": "TX", "430": "TX",
    "432": "TX", "469": "TX", "512": "TX", "682": "TX", "713": "TX", "726": "TX", "737": "TX", "806": "TX", "817": "TX",
    "830": "TX", "832": "TX", "903": "TX", "915": "TX", "936": "TX", "940": "TX", "945": "TX", "956": "TX", "972": "TX", "979": "TX",
    "212": "NY", "315": "NY", "329": "NY", "332": "NY", "347": "NY", "363": "NY", "516": "NY", "518": "NY", "585": "NY", "607": "NY",
    "624": "NY", "631": "NY", "646": "NY", "680": "NY", "716": "NY", "718": "NY", "838": "NY", "845": "NY", "914": "NY", "917": "NY", "929": "NY", "934": "NY",
    "215": "PA", "223": "PA", "267": "PA", "272": "PA", "412": "PA", "445": "PA", "484": "PA", "570": "PA", "582": "PA",
    "610": "PA", "717": "PA", "724": "PA", "814": "PA", "835": "PA", "878": "PA",
    "216": "OH", "220": "OH", "234": "OH", "283": "OH", "326": "OH", "330": "OH", "380": "OH", "419": "OH", "436": "OH", "440": "OH",
    "513": "OH", "567": "OH", "614": "OH", "740": "OH", "937": "OH",
    "217": "IL", "224": "IL", "309": "IL", "312": "IL", "331": "IL", "447": "IL", "464": "IL", "618": "IL", "630": "IL",
    "708": "IL", "730": "IL", "773": "IL", "779": "IL", "815": "IL", "847": "IL", "861": "IL", "872": "IL",
    "218": "MN", "320": "MN", "507": "MN", "612": "MN", "651": "MN", "763": "MN", "924": "MN", "952": "MN",
    "219": "IN", "260": "IN", "317": "IN", "463": "IN", "574": "IN", "765": "IN", "812": "IN", "930": "IN",
    "225": "LA", "318": "LA", "337": "LA", "504": "LA", "985": "LA",
    "228": "MS", "601": "MS", "662": "MS", "769": "MS",
    "229": "GA", "404": "GA", "470": "GA", "478": "GA", "678": "GA", "706": "GA", "762": "GA", "770": "GA", "912": "GA", "943": "GA",
    "231": "MI", "248": "MI", "269": "MI", "313": "MI", "517": "MI", "586": "MI", "616": "MI", "679": "MI", "734": "MI", "810": "MI", "906": "MI", "947": "MI", "989": "MI",
    "239": "FL", "305": "FL", "321": "FL", "324": "FL", "352": "FL", "386": "FL", "407": "FL", "448": "FL", "561": "FL", "645": "FL",
    "656": "FL", "689": "FL", "727": "FL", "728": "FL", "754": "FL", "772": "FL", "786": "FL", "813": "FL", "850": "FL", "863": "FL", "904": "FL", "941": "FL", "954": "FL",
    "227": "MD", "240": "MD", "301": "MD", "410": "MD", "443": "MD", "667": "MD",
    "252": "NC", "336": "NC", "472": "NC", "704": "NC", "743": "NC", "828": "NC", "910": "NC", "919": "NC", "980": "NC", "984": "NC",
    "262": "WI", "274": "WI", "353": "WI", "414": "WI", "534": "WI", "608": "WI", "715": "WI", "920": "WI",
    "270": "KY", "364": "KY", "502": "KY", "606": "KY", "859": "KY",
    "276": "VA", "434": "VA", "540": "VA", "571": "VA", "686": "VA", "703": "VA", "757": "VA", "804": "VA", "826": "VA", "948": "VA",
    "302": "DE",
    "303": "CO", "719": "CO", "720": "CO", "748": "CO", "970": "CO", "983": "CO",
    "304": "WV", "681": "WV",
    "307": "WY",
    "308": "NE", "402": "NE", "531": "NE",
    "235": "MO", "314": "MO", "417": "MO", "557": "MO", "573": "MO", "636": "MO", "660": "MO", "816": "MO", "975": "MO",
    "316": "KS", "620": "KS", "785": "KS", "913": "KS",
    "319": "IA", "515": "IA", "563": "IA", "641": "IA", "712": "IA",
    "339": "MA", "351": "MA", "413": "MA", "508": "MA", "617": "MA", "774": "MA", "781": "MA", "857": "MA", "978": "MA",
    "385": "UT", "435": "UT", "801": "UT",
    "401": "RI",
    "405": "OK", "539": "OK", "572": "OK", "580": "OK", "918": "OK",
    "406": "MT",
    "423": "TN", "615": "TN", "629": "TN", "731": "TN", "865": "TN", "901": "TN", "931": "TN",
    "480": "AZ", "520": "AZ", "602": "AZ", "623": "AZ", "928": "AZ",
    "327": "AR", "479": "AR", "501": "AR", "870": "AR",
    "503": "OR", "458": "OR", "541": "OR", "971": "OR",
    "505": "NM", "575": "NM",
    "603": "NH",
    "605": "SD",
    "701": "ND",
    "702": "NV", "725": "NV", "775": "NV",
    "802": "VT",
    "803": "SC", "821": "SC", "839": "SC", "843": "SC", "854": "SC", "864": "SC",
    "808": "HI",
    "907": "AK",
}


def resolve_nanp_npa(npa: str, fallback_iso2: str = "US") -> tuple[str, str | None, bool]:
    """Resolve a 3-digit NANP area code (NPA) to (country_iso2, region_code, is_recognized_npa).

    Checks Caribbean/Pacific NANP nations, Canadian provinces, US states, and non-geographic
    service NPAs (Toll-Free, Premium, Personal).
    """
    if npa in NANP_CARIBBEAN_PACIFIC_NPA_TO_ISO2:
        iso2, region = NANP_CARIBBEAN_PACIFIC_NPA_TO_ISO2[npa]
        return iso2, region, True

    if npa in NANP_CANADA_NPA_TO_PROVINCE:
        return "CA", NANP_CANADA_NPA_TO_PROVINCE[npa], True

    if npa in NANP_US_NPA_TO_STATE:
        return "US", NANP_US_NPA_TO_STATE[npa], True

    if npa in NANP_TOLL_FREE_NPAS or npa in NANP_PREMIUM_NPAS or npa in NANP_PERSONAL_NPAS:
        country = fallback_iso2 if fallback_iso2 in NANP_JURISDICTIONS else "US"
        return country, None, True

    # Structurally valid NANP NPA: [2-9][0-9]{2}, not N11
    if len(npa) == 3 and npa[0] in "23456789" and npa[1:].isdigit() and npa[1:] != "11":
        country = fallback_iso2 if fallback_iso2 in NANP_JURISDICTIONS else "US"
        return country, None, False

    return fallback_iso2, None, False


