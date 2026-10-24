"""Person Name and Job Title Standardization & Root Name Resolution."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
import re
from typing import Any

_SALUTATIONS: dict[str, str] = {
    "DR": "DR",
    "DOCTOR": "DR",
    "MR": "MR",
    "MISTER": "MR",
    "MRS": "MRS",
    "MISSUS": "MRS",
    "MS": "MS",
    "MISS": "MISS",
    "MX": "MX",
    "PROF": "PROF",
    "PROFESSOR": "PROF",
    "REV": "REV",
    "REVEREND": "REV",
    "HON": "HON",
    "HONORABLE": "HON",
    "SIR": "SIR",
    "DAME": "DAME",
    "LORD": "LORD",
    "LADY": "LADY",
    "CAPT": "CAPT",
    "CAPTAIN": "CAPT",
    "COL": "COL",
    "COLONEL": "COL",
    "GEN": "GEN",
    "GENERAL": "GEN",
    "MAJ": "MAJ",
    "MAJOR": "MAJ",
    "LT": "LT",
    "LIEUTENANT": "LT",
    "SGT": "SGT",
    "SERGEANT": "SGT",
    "FR": "FR",
    "FATHER": "FR",
    "RABBI": "RABBI",
}

_GENERATIONAL_SUFFIXES: dict[str, str] = {
    "JR": "JR",
    "JNR": "JR",
    "JUNIOR": "JR",
    "SR": "SR",
    "SNR": "SR",
    "SENIOR": "SR",
    "II": "II",
    "2ND": "II",
    "III": "III",
    "3RD": "III",
    "IV": "IV",
    "4TH": "IV",
    "V": "V",
    "5TH": "V",
}

_CREDENTIALS: dict[str, str] = {
    "PHD": "PHD",
    "DPHIL": "PHD",
    "MD": "MD",
    "DO": "DO",
    "JD": "JD",
    "LLM": "LLM",
    "LLB": "LLB",
    "ESQ": "ESQ",
    "ESQUIRE": "ESQ",
    "MBA": "MBA",
    "CPA": "CPA",
    "CFA": "CFA",
    "CFP": "CFP",
    "PE": "PE",
    "RN": "RN",
    "NP": "NP",
    "APRN": "APRN",
    "BSN": "BSN",
    "MSN": "MSN",
    "DDS": "DDS",
    "DMD": "DMD",
    "DVM": "DVM",
    "PHARMD": "PHARMD",
    "MPH": "MPH",
    "MSC": "MSC",
    "BSC": "BSC",
    "PMP": "PMP",
    "CISSP": "CISSP",
    "FACS": "FACS",
    "FACP": "FACP",
    "CHFC": "CHFC",
    "CLU": "CLU",
    "AIF": "AIF",
    "CIMA": "CIMA",
    "CPWA": "CPWA",
    "RICP": "RICP",
    "CRPC": "CRPC",
    "EA": "EA",
    "PFS": "PFS",
    "CAIA": "CAIA",
    "FRM": "FRM",
}

_SURNAME_PARTICLES: frozenset[str] = frozenset(
    {
        "VAN",
        "VON",
        "DER",
        "DEN",
        "DE",
        "DEL",
        "DELLA",
        "DI",
        "DA",
        "DOS",
        "DAS",
        "DU",
        "LA",
        "LE",
        "LAS",
        "LOS",
        "ST",
        "SAINT",
        "MC",
        "MAC",
        "AL",
        "BIN",
        "IBN",
    }
)

_NICKNAME_TO_ROOT: dict[str, str] = {
    "BOB": "ROBERT",
    "ROB": "ROBERT",
    "BOBBY": "ROBERT",
    "ROBBIE": "ROBERT",
    "BERT": "ROBERT",
    "BILL": "WILLIAM",
    "WILL": "WILLIAM",
    "BILLY": "WILLIAM",
    "WILLY": "WILLIAM",
    "LIAM": "WILLIAM",
    "MIKE": "MICHAEL",
    "MICK": "MICHAEL",
    "MIKEY": "MICHAEL",
    "JIM": "JAMES",
    "JIMMY": "JAMES",
    "JAMIE": "JAMES",
    "DICK": "RICHARD",
    "RICK": "RICHARD",
    "RICKY": "RICHARD",
    "RICH": "RICHARD",
    "RICHIE": "RICHARD",
    "TOM": "THOMAS",
    "TOMMY": "THOMAS",
    "DAVE": "DAVID",
    "DAVY": "DAVID",
    "DAN": "DANIEL",
    "DANNY": "DANIEL",
    "LIZ": "ELIZABETH",
    "BETH": "ELIZABETH",
    "BETTY": "ELIZABETH",
    "LIZZY": "ELIZABETH",
    "ELIZA": "ELIZABETH",
    "BETSY": "ELIZABETH",
    "PEGGY": "MARGARET",
    "MAGGIE": "MARGARET",
    "MEG": "MARGARET",
    "MARGE": "MARGARET",
    "MARGIE": "MARGARET",
    "KATE": "KATHERINE",
    "KATIE": "KATHERINE",
    "KATHY": "KATHERINE",
    "CATHY": "KATHERINE",
    "CATHERINE": "KATHERINE",
    "JEN": "JENNIFER",
    "JENNY": "JENNIFER",
    "JENN": "JENNIFER",
    "CHRIS": "CHRISTOPHER",
    "TOPHER": "CHRISTOPHER",
    "MATT": "MATTHEW",
    "MATTY": "MATTHEW",
    "TONY": "ANTHONY",
    "STEVE": "STEVEN",
    "STEVIE": "STEVEN",
    "STEPHEN": "STEVEN",
    "JOE": "JOSEPH",
    "JOEY": "JOSEPH",
    "SAM": "SAMUEL",
    "SAMMY": "SAMUEL",
    "ALEX": "ALEXANDER",
    "BEN": "BENJAMIN",
    "BENNY": "BENJAMIN",
    "BENJI": "BENJAMIN",
    "JON": "JONATHAN",
    "JONNY": "JONATHAN",
    "NICK": "NICHOLAS",
    "NICKY": "NICHOLAS",
    "ED": "EDWARD",
    "TED": "EDWARD",
    "EDDIE": "EDWARD",
    "TEDDY": "EDWARD",
    "NED": "EDWARD",
    "ANDY": "ANDREW",
    "DREW": "ANDREW",
    "CHUCK": "CHARLES",
    "CHARLIE": "CHARLES",
    "GREG": "GREGORY",
    "JEFF": "JEFFREY",
    "TIM": "TIMOTHY",
    "TIMMY": "TIMOTHY",
    "PAT": "PATRICK",
    "KEN": "KENNETH",
    "KENNY": "KENNETH",
    "RON": "RONALD",
    "RONNIE": "RONALD",
    "DON": "DONALD",
    "DONNIE": "DONALD",
    "LARRY": "LAWRENCE",
    "JERRY": "GERALD",
    "FRANK": "FRANCIS",
    "FRANKIE": "FRANCIS",
    "SUE": "SUSAN",
    "SUSIE": "SUSAN",
    "DEB": "DEBORAH",
    "DEBBIE": "DEBORAH",
    "BECKY": "REBECCA",
    "VICKY": "VICTORIA",
    "MANDY": "AMANDA",
    "STEPH": "STEPHANIE",
    "ZACK": "ZACHARY",
    "ZACH": "ZACHARY",
    "JOSH": "JOSHUA",
    "NATE": "NATHAN",
    "NAT": "NATHAN",
    "DOUG": "DOUGLAS",
    "WALT": "WALTER",
    "WALLY": "WALTER",
    "PHIL": "PHILIP",
    "GENE": "EUGENE",
    "RAY": "RAYMOND",
    "HARRY": "HAROLD",
    "HAL": "HAROLD",
    "HANK": "HENRY",
    "JACK": "JOHN",
    "JOHNNY": "JOHN",
    "MARTY": "MARTIN",
    "ART": "ARTHUR",
    "ARTIE": "ARTHUR",
    "BERNIE": "BERNARD",
}

_PAREN_OR_QUOTE_NICK_RE = re.compile(
    r'\(\s*([A-Za-z][A-Za-z.\s\-]{0,24})\s*\)|"([A-Za-z][A-Za-z.\s\-]{0,24})"|(?<=[\s,])\'([A-Za-z][A-Za-z.\s\-]{0,24})\'(?=[\s,]|$)'
)

# Job Title expansion & classification tables
_TITLE_MULTI_EXPANSIONS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("ASST", "VP"), "ASSISTANT VICE PRESIDENT"),
    (("ASSISTANT", "VP"), "ASSISTANT VICE PRESIDENT"),
    (("ASSOC", "VP"), "ASSOCIATE VICE PRESIDENT"),
    (("ASSOCIATE", "VP"), "ASSOCIATE VICE PRESIDENT"),
    (("SR", "VP"), "SENIOR VICE PRESIDENT"),
    (("SENIOR", "VP"), "SENIOR VICE PRESIDENT"),
    (("EXEC", "VP"), "EXECUTIVE VICE PRESIDENT"),
    (("EXECUTIVE", "VP"), "EXECUTIVE VICE PRESIDENT"),
    (("CO", "FOUNDER"), "CO-FOUNDER"),
    (("VICE", "PRES"), "VICE PRESIDENT"),
    (("GEN", "MGR"), "GENERAL MANAGER"),
    (("MANAGING", "DIR"), "MANAGING DIRECTOR"),
    (("BIZ", "DEV"), "BUSINESS DEVELOPMENT"),
    (("BUSINESS", "DEV"), "BUSINESS DEVELOPMENT"),
)

_TITLE_TOKEN_EXPANSIONS: dict[str, str] = {
    "CEO": "CHIEF EXECUTIVE OFFICER",
    "CFO": "CHIEF FINANCIAL OFFICER",
    "CTO": "CHIEF TECHNOLOGY OFFICER",
    "COO": "CHIEF OPERATING OFFICER",
    "CMO": "CHIEF MARKETING OFFICER",
    "CIO": "CHIEF INFORMATION OFFICER",
    "CISO": "CHIEF INFORMATION SECURITY OFFICER",
    "CRO": "CHIEF REVENUE OFFICER",
    "CPO": "CHIEF PRODUCT OFFICER",
    "CHRO": "CHIEF HUMAN RESOURCES OFFICER",
    "CLO": "CHIEF LEGAL OFFICER",
    "CCO": "CHIEF COMPLIANCE OFFICER",
    "CAO": "CHIEF ACCOUNTING OFFICER",
    "CSO": "CHIEF STRATEGY OFFICER",
    "VP": "VICE PRESIDENT",
    "SVP": "SENIOR VICE PRESIDENT",
    "EVP": "EXECUTIVE VICE PRESIDENT",
    "AVP": "ASSISTANT VICE PRESIDENT",
    "MD": "MANAGING DIRECTOR",
    "GM": "GENERAL MANAGER",
    "DIR": "DIRECTOR",
    "MGR": "MANAGER",
    "SR": "SENIOR",
    "JR": "JUNIOR",
    "ENG": "ENGINEER",
    "ENGR": "ENGINEER",
    "DEV": "DEVELOPER",
    "ASSOC": "ASSOCIATE",
    "ASST": "ASSISTANT",
    "ADMIN": "ADMINISTRATOR",
    "REP": "REPRESENTATIVE",
    "EXEC": "EXECUTIVE",
    "OPS": "OPERATIONS",
    "MKT": "MARKETING",
    "MKTG": "MARKETING",
    "FIN": "FINANCE",
    "ACCT": "ACCOUNTANT",
    "SWE": "SOFTWARE ENGINEER",
    "GC": "GENERAL COUNSEL",
    "PRES": "PRESIDENT",
}


@dataclass(slots=True)
class StandardizedPerson:
    """Canonical representation of a standardized person name."""

    raw_input: str
    salutation: str | None = None
    first_name: str | None = None
    root_first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    nickname: str | None = None
    generational_suffix: str | None = None
    credentials: list[str] = field(default_factory=list)
    full_name: str | None = None
    person_key: str | None = None
    person_root_key: str | None = None
    phonetic_key: str | None = None
    is_valid: bool = False
    confidence: float = 0.0
    healing_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the standardized person record into a JSON-compatible dictionary."""
        return {
            "raw_input": self.raw_input,
            "salutation": self.salutation,
            "first_name": self.first_name,
            "root_first_name": self.root_first_name,
            "middle_name": self.middle_name,
            "last_name": self.last_name,
            "nickname": self.nickname,
            "generational_suffix": self.generational_suffix,
            "credentials": list(self.credentials),
            "full_name": self.full_name,
            "person_key": self.person_key,
            "person_root_key": self.person_root_key,
            "phonetic_key": self.phonetic_key,
            "is_valid": self.is_valid,
            "confidence": round(self.confidence, 4),
            "healing_actions": list(self.healing_actions),
        }


@dataclass(slots=True)
class StandardizedJobTitle:
    """Canonical representation of a standardized job title, seniority level, and department."""

    raw_input: str
    normalized_title: str | None = None
    seniority_level: str | None = None
    department: str | None = None
    is_valid: bool = False
    confidence: float = 0.0
    healing_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the standardized job title record into a JSON-compatible dictionary."""
        return {
            "raw_input": self.raw_input,
            "normalized_title": self.normalized_title,
            "seniority_level": self.seniority_level,
            "department": self.department,
            "is_valid": self.is_valid,
            "confidence": round(self.confidence, 4),
            "healing_actions": list(self.healing_actions),
        }


_SPACED_DOTTED_CRED_RE = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]{1,2}\.\s*){2,}")


def _collapse_dotted_cred(match: re.Match[str]) -> str:
    collapsed = re.sub(r"[^A-Za-z0-9]", "", match.group(0)).upper()
    if collapsed in _CREDENTIALS:
        return f" {collapsed} "
    return match.group(0)


def _clean_token(tok: str) -> str:
    """Strip punctuation periods from a single word token and uppercase it."""
    cleaned = re.sub(r"[^A-Za-z0-9'\-]", "", tok).upper().strip("'-")
    if cleaned and cleaned not in _GENERATIONAL_SUFFIXES and any(c.isdigit() for c in cleaned):
        return ""
    return cleaned


def _tokenize_segment(segment: str) -> list[str]:
    """Tokenize a name segment into cleaned uppercase tokens."""
    norm_seg = _SPACED_DOTTED_CRED_RE.sub(_collapse_dotted_cred, segment)
    out: list[str] = []
    for raw_tok in norm_seg.split():
        cleaned = _clean_token(raw_tok)
        if cleaned:
            out.append(cleaned)
    return out


def standardize_person(raw_input: str | None) -> StandardizedPerson:
    """Parse and standardize a person's full name into structured fields and entity keys."""
    if raw_input is None:
        return StandardizedPerson(raw_input="")

    cleaned_raw = str(raw_input).strip()
    if not cleaned_raw or re.match(r"^\d+\s+", cleaned_raw):
        return StandardizedPerson(raw_input=str(raw_input))

    actions: list[str] = []
    working = re.sub(r"\s+", " ", cleaned_raw)

    salutation: str | None = None
    nickname: str | None = None
    generational_suffix: str | None = None
    credentials: list[str] = []

    # 1. Extract parenthetical or quoted nickname (or parenthetical credential/suffix)
    def _replace_nick(match: re.Match[str]) -> str:
        nonlocal nickname, generational_suffix
        inner = (match.group(1) or match.group(2) or match.group(3) or "").strip()
        tok = _clean_token(inner)
        if tok in _CREDENTIALS:
            credentials.append(_CREDENTIALS[tok])
            actions.append("CREDENTIALS_EXTRACTED")
            return " "
        if tok in _GENERATIONAL_SUFFIXES:
            generational_suffix = _GENERATIONAL_SUFFIXES[tok]
            actions.append("GENERATIONAL_SUFFIX_EXTRACTED")
            return " "
        if nickname is None:
            nickname = tok
            actions.append("NICKNAME_EXTRACTED")
        return " "

    working = _PAREN_OR_QUOTE_NICK_RE.sub(_replace_nick, working)

    # 2. Split by comma and inspect segments for suffixes, credentials, and Last, First inversion
    raw_segments = [s.strip() for s in working.split(",") if s.strip()]
    if not raw_segments:
        return StandardizedPerson(raw_input=str(raw_input))

    core_segments: list[list[str]] = []
    for idx, seg in enumerate(raw_segments):
        toks = _tokenize_segment(seg)
        if not toks:
            continue
        if idx > 0 and all(
            t in _GENERATIONAL_SUFFIXES or t in _CREDENTIALS for t in toks
        ):
            for t in toks:
                if t in _GENERATIONAL_SUFFIXES:
                    generational_suffix = _GENERATIONAL_SUFFIXES[t]
                    actions.append("GENERATIONAL_SUFFIX_EXTRACTED")
                else:
                    credentials.append(_CREDENTIALS[t])
                    actions.append("CREDENTIALS_EXTRACTED")
        else:
            core_segments.append(toks)

    if not core_segments:
        return StandardizedPerson(raw_input=str(raw_input))

    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None

    if len(core_segments) >= 2:
        # "Last, First [Middle]" (or "Smith, Jr., Robert J." or "Smith Jr., Robert J.") inversion
        last_toks = list(core_segments[0])
        given_toks: list[str] = []
        for seg_toks in core_segments[1:]:
            given_toks.extend(seg_toks)

        if last_toks[0] in _SALUTATIONS and len(last_toks) > 1:
            salutation = _SALUTATIONS[last_toks.pop(0)]
            actions.append("SALUTATION_EXTRACTED")

        while len(last_toks) > 1 and last_toks[-1] in _GENERATIONAL_SUFFIXES:
            generational_suffix = _GENERATIONAL_SUFFIXES[last_toks.pop()]
            actions.append("GENERATIONAL_SUFFIX_EXTRACTED")

        while given_toks[0] in _SALUTATIONS and len(given_toks) > 1:
            salutation = _SALUTATIONS[given_toks.pop(0)]
            actions.append("SALUTATION_EXTRACTED")

        given_trailing_creds: list[str] = []
        while len(given_toks) > 1 and (
            given_toks[-1] in _CREDENTIALS or given_toks[-1] in _GENERATIONAL_SUFFIXES
        ):
            tail = given_toks.pop()
            if tail in _CREDENTIALS:
                given_trailing_creds.insert(0, _CREDENTIALS[tail])
            else:
                generational_suffix = _GENERATIONAL_SUFFIXES[tail]
                actions.append("GENERATIONAL_SUFFIX_EXTRACTED")
        if given_trailing_creds:
            credentials.extend(given_trailing_creds)
            actions.append("CREDENTIALS_EXTRACTED")

        last_name = " ".join(last_toks)
        first_name = given_toks[0]
        if len(given_toks) > 1:
            middle_name = " ".join(given_toks[1:])
        actions.append("LAST_FIRST_UNINVERTED")
    else:
        toks = list(core_segments[0])
        while len(toks) > 1 and toks[0] in _SALUTATIONS:
            salutation = _SALUTATIONS[toks.pop(0)]
            actions.append("SALUTATION_EXTRACTED")

        # Extract trailing credentials and generational suffixes (when >= 2 tokens precede)
        trailing_creds: list[str] = []
        while len(toks) > 2 and (
            toks[-1] in _CREDENTIALS or toks[-1] in _GENERATIONAL_SUFFIXES
        ):
            tail = toks.pop()
            if tail in _CREDENTIALS:
                trailing_creds.insert(0, _CREDENTIALS[tail])
            else:
                generational_suffix = _GENERATIONAL_SUFFIXES[tail]
                actions.append("GENERATIONAL_SUFFIX_EXTRACTED")
        if trailing_creds:
            credentials.extend(trailing_creds)
            actions.append("CREDENTIALS_EXTRACTED")

        if len(toks) == 1:
            first_name = toks[0]
        elif len(toks) == 2:
            first_name, last_name = toks[0], toks[1]
        else:
            first_name = toks[0]
            # Check for compound surname particles preceding the last token (e.g. "VAN DER BEEK")
            surname_start = len(toks) - 1
            while surname_start > 1 and toks[surname_start - 1] in _SURNAME_PARTICLES:
                surname_start -= 1
            last_name = " ".join(toks[surname_start:])
            mid_slice = toks[1:surname_start]
            middle_name = " ".join(mid_slice) if mid_slice else None

    # 3. Resolve root_first_name from diminutive/nickname table
    root_first_name: str | None = first_name
    if first_name and first_name in _NICKNAME_TO_ROOT:
        root_first_name = _NICKNAME_TO_ROOT[first_name]
        actions.append("NICKNAME_RESOLVED_TO_ROOT")
    elif (
        nickname
        and nickname in _NICKNAME_TO_ROOT
        and first_name
        and len(first_name) == 1
        and _NICKNAME_TO_ROOT[nickname].startswith(first_name)
    ):
        root_first_name = _NICKNAME_TO_ROOT[nickname]
        actions.append("NICKNAME_RESOLVED_TO_ROOT")

    full_parts = [
        p for p in (first_name, middle_name, last_name, generational_suffix) if p
    ]
    full_name = " ".join(full_parts)

    person_key = (
        f"{last_name or ''}|{first_name or ''}|{middle_name or ''}|{generational_suffix or ''}"
    )
    person_root_key = f"{last_name or ''}|{root_first_name or ''}"

    from address_standardizer.phonetics import compute_soundex

    last_snd = compute_soundex(last_name.split()[-1]) if last_name else ""
    first_snd = compute_soundex(root_first_name or first_name or "")
    phonetic_key = f"{last_snd}|{first_snd}".strip("|") or None

    confidence = 0.98 if (first_name and last_name) else 0.78

    return StandardizedPerson(
        raw_input=str(raw_input),
        salutation=salutation,
        first_name=first_name,
        root_first_name=root_first_name,
        middle_name=middle_name,
        last_name=last_name,
        nickname=nickname,
        generational_suffix=generational_suffix,
        credentials=list(dict.fromkeys(credentials)),
        full_name=full_name,
        person_key=person_key,
        person_root_key=person_root_key,
        phonetic_key=phonetic_key,
        is_valid=True,
        confidence=confidence,
        healing_actions=list(dict.fromkeys(actions)),
    )


def _classify_seniority(norm_title: str, tokens: set[str]) -> str:
    """Classify canonical job title into seniority_level."""
    if (
        re.search(r"\bCHIEF\s+[A-Z\s]+OFFICER\b", norm_title)
        or "GENERAL COUNSEL" in norm_title
    ):
        return "C_SUITE"
    if any(
        w in tokens
        for w in ("OWNER", "FOUNDER", "PARTNER", "CHAIRMAN", "CHAIRPERSON", "CHAIRWOMAN")
    ) or "CO-FOUNDER" in norm_title or (
        "PRESIDENT" in tokens and "VICE" not in tokens
    ):
        return "OWNER_PARTNER"
    if "VICE PRESIDENT" in norm_title:
        return "VP"
    if "DIRECTOR" in tokens or "HEAD OF" in norm_title:
        return "DIRECTOR"
    if "MANAGER" in tokens or "SUPERVISOR" in tokens:
        return "MANAGER"
    if any(w in tokens for w in ("SENIOR", "STAFF", "PRINCIPAL", "ARCHITECT", "FELLOW", "LEAD")):
        return "SENIOR"
    if any(
        w in tokens
        for w in ("JUNIOR", "INTERN", "TRAINEE", "APPRENTICE", "ASSISTANT", "ASSOCIATE", "ENTRY")
    ):
        return "ENTRY"
    return "INDIVIDUAL_CONTRIBUTOR"


def _classify_department(norm_title: str, tokens: set[str]) -> str:
    """Classify canonical job title into functional department."""
    if (
        tokens
        & {
            "TECHNOLOGY",
            "TECHNICAL",
            "SOFTWARE",
            "HARDWARE",
            "ENGINEER",
            "ENGINEERING",
            "DEVELOPER",
            "DATA",
            "INFORMATION",
            "SECURITY",
            "IT",
            "DEVOPS",
            "CLOUD",
            "SYSTEMS",
            "ARCHITECT",
            "QA",
        }
    ):
        return "ENGINEERING"
    if (
        tokens
        & {
            "FINANCIAL",
            "FINANCE",
            "ACCOUNTING",
            "ACCOUNTANT",
            "TREASURY",
            "TREASURER",
            "CONTROLLER",
            "COMPTROLLER",
            "TAX",
            "AUDIT",
            "BILLING",
            "PAYROLL",
        }
    ):
        return "FINANCE"
    if (
        tokens
        & {
            "MARKETING",
            "BRAND",
            "GROWTH",
            "COMMUNICATIONS",
            "CONTENT",
            "ADVERTISING",
            "CREATIVE",
            "PR",
        }
        or "PUBLIC RELATIONS" in norm_title
    ):
        return "MARKETING"
    if (
        tokens
        & {
            "SALES",
            "REVENUE",
            "COMMERCIAL",
            "PARTNERSHIPS",
        }
        or "BUSINESS DEVELOPMENT" in norm_title
        or "ACCOUNT EXECUTIVE" in norm_title
        or "CUSTOMER SUCCESS" in norm_title
    ):
        return "SALES"
    if (
        tokens
        & {
            "OPERATING",
            "OPERATIONS",
            "LOGISTICS",
            "PROCUREMENT",
            "FULFILLMENT",
            "FACILITIES",
            "MANUFACTURING",
            "PLANT",
            "QUALITY",
        }
        or "SUPPLY CHAIN" in norm_title
    ):
        return "OPERATIONS"
    if (
        tokens
        & {
            "LEGAL",
            "COUNSEL",
            "ATTORNEY",
            "COMPLIANCE",
            "REGULATORY",
            "PARALEGAL",
            "PRIVACY",
        }
    ):
        return "LEGAL"
    if (
        tokens
        & {
            "HR",
            "PEOPLE",
            "TALENT",
            "RECRUITING",
            "RECRUITER",
            "BENEFITS",
            "COMPENSATION",
        }
        or "HUMAN RESOURCES" in norm_title
    ):
        return "HR"
    if (
        tokens
        & {
            "EXECUTIVE",
            "PRESIDENT",
            "FOUNDER",
            "OWNER",
            "PARTNER",
            "CHAIRMAN",
            "CHAIRPERSON",
        }
        or "CO-FOUNDER" in norm_title
        or "MANAGING DIRECTOR" in norm_title
        or "GENERAL MANAGER" in norm_title
    ):
        return "EXECUTIVE"
    return "GENERAL"


def standardize_job_title(raw_input: str | None) -> StandardizedJobTitle:
    """Normalize a job title, expanding abbreviations and classifying seniority and department."""
    if raw_input is None:
        return StandardizedJobTitle(raw_input="")

    cleaned_raw = str(raw_input).strip()
    if not cleaned_raw:
        return StandardizedJobTitle(raw_input=str(raw_input))

    from entity_standardizer.company import _DOTTED_INITIALISM_RE

    actions: list[str] = []
    working = re.sub(r"&", " AND ", cleaned_raw)
    working = _DOTTED_INITIALISM_RE.sub(
        lambda m: f" {re.sub(r'[^A-Za-z]', '', m.group(0)).upper()} ", working
    )
    working = re.sub(r"[^\w\s\-]", " ", working)
    raw_tokens = [t.upper().strip("-") for t in working.split() if t.strip("-")]
    if not raw_tokens:
        return StandardizedJobTitle(raw_input=str(raw_input))

    # Multi-token expansions first
    expanded_tokens: list[str] = []
    i = 0
    n = len(raw_tokens)
    while i < n:
        matched_multi = False
        for pat, replacement in _TITLE_MULTI_EXPANSIONS:
            plen = len(pat)
            if i + plen <= n and tuple(raw_tokens[i : i + plen]) == pat:
                expanded_tokens.extend(replacement.split())
                actions.append("TITLE_ABBREVIATION_EXPANDED")
                i += plen
                matched_multi = True
                break
        if matched_multi:
            continue

        tok = raw_tokens[i]
        if tok in _TITLE_TOKEN_EXPANSIONS:
            expanded_tokens.extend(_TITLE_TOKEN_EXPANSIONS[tok].split())
            actions.append("TITLE_ABBREVIATION_EXPANDED")
        else:
            expanded_tokens.append(tok)
        i += 1

    normalized_title = " ".join(expanded_tokens)
    token_set = set(expanded_tokens)
    seniority_level = _classify_seniority(normalized_title, token_set)
    department = _classify_department(normalized_title, token_set)

    return StandardizedJobTitle(
        raw_input=str(raw_input),
        normalized_title=normalized_title,
        seniority_level=seniority_level,
        department=department,
        is_valid=True,
        confidence=0.96,
        healing_actions=list(dict.fromkeys(actions)),
    )


def batch_standardize_persons(inputs: Sequence[str | None]) -> list[StandardizedPerson]:
    """Batch-standardize a sequence of person full names."""
    return [standardize_person(item) for item in inputs]


def batch_standardize_job_titles(inputs: Sequence[str | None]) -> list[StandardizedJobTitle]:
    """Batch-standardize a sequence of job titles."""
    return [standardize_job_title(item) for item in inputs]
