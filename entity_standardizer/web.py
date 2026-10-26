"""Email, Website URL, and Social Profile Standardization & Domain Attribution."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

from entity_standardizer.company import standardize_company

_DOMAIN_TYPO_MAP: dict[str, str] = {
    "gmial.com": "gmail.com",
    "gamil.com": "gmail.com",
    "gmai.com": "gmail.com",
    "gnail.com": "gmail.com",
    "gmail.con": "gmail.com",
    "gmail.co": "gmail.com",
    "googlemial.com": "googlemail.com",
    "yaho.com": "yahoo.com",
    "yahooo.com": "yahoo.com",
    "yhoo.com": "yahoo.com",
    "yahoo.con": "yahoo.com",
    "outlok.com": "outlook.com",
    "oulook.com": "outlook.com",
    "outlook.con": "outlook.com",
    "hotmial.com": "hotmail.com",
    "homtail.com": "hotmail.com",
    "hotmail.con": "hotmail.com",
    "iclod.com": "icloud.com",
    "icoud.com": "icloud.com",
    "icloud.con": "icloud.com",
}

_FREE_WEBMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "yahoo.co.uk",
        "yahoo.fr",
        "yahoo.de",
        "yahoo.ca",
        "yahoo.co.jp",
        "ymail.com",
        "rocketmail.com",
        "outlook.com",
        "hotmail.com",
        "hotmail.co.uk",
        "live.com",
        "msn.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "aol.com",
        "protonmail.com",
        "proton.me",
        "pm.me",
        "zoho.com",
        "gmx.com",
        "gmx.de",
        "web.de",
        "mail.com",
        "fastmail.com",
        "hey.com",
        "yandex.com",
        "qq.com",
        "163.com",
    }
)

_DISPOSABLE_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "mailinator.com",
        "guerrillamail.com",
        "10minutemail.com",
        "tempmail.com",
        "temp-mail.org",
        "yopmail.com",
        "trashmail.com",
        "sharklasers.com",
        "getnada.com",
        "maildrop.cc",
        "throwawaymail.com",
        "fakeinbox.com",
        "dispostable.com",
    }
)

_SENTINEL_DOMAINS: frozenset[str] = frozenset(
    {
        "example.com",
        "example.org",
        "example.net",
        "example.edu",
        "test.com",
        "invalid.com",
        "none.com",
        "null.com",
        "na.com",
        "n-a.com",
        "tbd.com",
        "unknown.com",
        "localhost.localdomain",
    }
)

_ROLE_ACCOUNT_PREFIXES: frozenset[str] = frozenset(
    {
        "admin",
        "administrator",
        "info",
        "support",
        "help",
        "sales",
        "contact",
        "billing",
        "accounts",
        "accounting",
        "finance",
        "hr",
        "careers",
        "jobs",
        "recruiting",
        "legal",
        "privacy",
        "security",
        "abuse",
        "postmaster",
        "webmaster",
        "hostmaster",
        "noreply",
        "no-reply",
        "donotreply",
        "do-not-reply",
        "office",
        "team",
        "hello",
        "enquiries",
        "inquiries",
        "press",
        "media",
        "marketing",
        "pr",
        "service",
        "customerservice",
        "orders",
        "compliance",
    }
)

_MULTI_PART_PUBLIC_SUFFIXES: frozenset[str] = frozenset(
    {
        "co.uk",
        "org.uk",
        "me.uk",
        "ltd.uk",
        "plc.uk",
        "net.uk",
        "sch.uk",
        "ac.uk",
        "gov.uk",
        "com.au",
        "net.au",
        "org.au",
        "edu.au",
        "gov.au",
        "asn.au",
        "id.au",
        "co.jp",
        "ne.jp",
        "or.jp",
        "ac.jp",
        "ad.jp",
        "ed.jp",
        "go.jp",
        "gr.jp",
        "lg.jp",
        "com.br",
        "net.br",
        "org.br",
        "gov.br",
        "edu.br",
        "co.nz",
        "net.nz",
        "org.nz",
        "govt.nz",
        "ac.nz",
        "co.za",
        "org.za",
        "net.za",
        "gov.za",
        "ac.za",
        "co.in",
        "net.in",
        "org.in",
        "gen.in",
        "firm.in",
        "ind.in",
        "ac.in",
        "gov.in",
        "com.mx",
        "org.mx",
        "net.mx",
        "gob.mx",
        "edu.mx",
        "com.sg",
        "edu.sg",
        "gov.sg",
        "net.sg",
        "org.sg",
        "com.hk",
        "edu.hk",
        "gov.hk",
        "net.hk",
        "org.hk",
        "co.kr",
        "ne.kr",
        "or.kr",
        "re.kr",
        "pe.kr",
        "go.kr",
        "ac.kr",
        "com.cn",
        "net.cn",
        "org.cn",
        "gov.cn",
        "edu.cn",
        "com.tw",
        "org.tw",
        "net.tw",
        "gov.tw",
        "edu.tw",
        "co.il",
        "org.il",
        "net.il",
        "ac.il",
        "gov.il",
        "com.ar",
        "com.co",
        "com.pe",
        "com.tr",
        "com.my",
        "com.ph",
        "com.vn",
        "co.id",
        "co.th",
    }
)

# Unambiguous ccTLD -> ISO2 country mapping (excluding generic/tech ccTLDs like .io, .ai, .co, .me, .tv)
_CCTLD_TO_COUNTRY_ISO2: dict[str, str] = {
    "uk": "GB",
    "gb": "GB",
    "de": "DE",
    "fr": "FR",
    "ca": "CA",
    "jp": "JP",
    "au": "AU",
    "ch": "CH",
    "nl": "NL",
    "it": "IT",
    "es": "ES",
    "br": "BR",
    "in": "IN",
    "mx": "MX",
    "nz": "NZ",
    "za": "ZA",
    "se": "SE",
    "no": "NO",
    "dk": "DK",
    "fi": "FI",
    "at": "AT",
    "be": "BE",
    "ie": "IE",
    "pl": "PL",
    "pt": "PT",
    "sg": "SG",
    "hk": "HK",
    "kr": "KR",
    "cn": "CN",
    "tw": "TW",
    "il": "IL",
    "ar": "AR",
    "pe": "PE",
    "tr": "TR",
    "my": "MY",
    "ph": "PH",
    "vn": "VN",
    "id": "ID",
    "th": "TH",
    "cz": "CZ",
    "hu": "HU",
    "ro": "RO",
    "gr": "GR",
    "ru": "RU",
    "ua": "UA",
    "cl": "CL",
}

_TRACKING_QUERY_PARAMS: frozenset[str] = frozenset(
    {
        "fbclid",
        "gclid",
        "dclid",
        "gbraid",
        "wbraid",
        "mc_cid",
        "mc_eid",
        "msclkid",
        "_ga",
        "_gl",
        "_hsenc",
        "_hsmi",
        "hsctatracking",
        "igshid",
        "twclid",
        "ttclid",
        "li_fat_id",
        "vero_id",
        "mkt_tok",
        "rb_clickid",
        "s_kwcid",
    }
)

_ANGLE_EMAIL_RE = re.compile(r"^\s*(.*?)\s*<\s*([^<>]+)\s*>\s*$")
_LOCAL_PART_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~\-]{1,64}$")
_DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?$")
_ROLE_SEP_RE = re.compile(r"[._\-]")
_SOCIAL_PREFIX_RE = re.compile(r"^([A-Za-z]+)\s*:\s*(.+)$")


@dataclass(slots=True)
class StandardizedEmail:
    """Canonical representation of a standardized email address."""

    raw_input: str
    email: str | None = None
    local_part: str | None = None
    raw_local_part: str | None = None
    subaddress: str | None = None
    domain: str | None = None
    display_name: str | None = None
    email_type: str | None = None
    is_free_provider: bool = False
    is_role_account: bool = False
    is_disposable: bool = False
    inferred_country_iso2: str | None = None
    email_key: str | None = None
    is_valid: bool = False
    confidence: float = 0.0
    healing_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the standardized email record into a JSON-compatible dictionary."""
        return {
            "raw_input": self.raw_input,
            "email": self.email,
            "local_part": self.local_part,
            "raw_local_part": self.raw_local_part,
            "subaddress": self.subaddress,
            "domain": self.domain,
            "display_name": self.display_name,
            "email_type": self.email_type,
            "is_free_provider": self.is_free_provider,
            "is_role_account": self.is_role_account,
            "is_disposable": self.is_disposable,
            "inferred_country_iso2": self.inferred_country_iso2,
            "email_key": self.email_key,
            "is_valid": self.is_valid,
            "confidence": round(self.confidence, 4),
            "healing_actions": list(self.healing_actions),
        }


@dataclass(slots=True)
class StandardizedUrl:
    """Canonical representation of a standardized website URL and registrable domain."""

    raw_input: str
    url: str | None = None
    scheme: str | None = None
    host: str | None = None
    domain: str | None = None
    subdomain: str | None = None
    public_suffix: str | None = None
    brand_stem: str | None = None
    path: str | None = None
    inferred_country_iso2: str | None = None
    url_key: str | None = None
    is_valid: bool = False
    confidence: float = 0.0
    healing_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the standardized URL record into a JSON-compatible dictionary."""
        return {
            "raw_input": self.raw_input,
            "url": self.url,
            "scheme": self.scheme,
            "host": self.host,
            "domain": self.domain,
            "subdomain": self.subdomain,
            "public_suffix": self.public_suffix,
            "brand_stem": self.brand_stem,
            "path": self.path,
            "inferred_country_iso2": self.inferred_country_iso2,
            "url_key": self.url_key,
            "is_valid": self.is_valid,
            "confidence": round(self.confidence, 4),
            "healing_actions": list(self.healing_actions),
        }


StandardizedWebsite = StandardizedUrl


@dataclass(slots=True)
class StandardizedSocial:
    """Canonical representation of a standardized social media profile."""

    raw_input: str
    platform: str | None = None
    profile_type: str | None = None
    handle: str | None = None
    url: str | None = None
    social_key: str | None = None
    is_valid: bool = False
    confidence: float = 0.0
    healing_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the standardized social record into a JSON-compatible dictionary."""
        return {
            "raw_input": self.raw_input,
            "platform": self.platform,
            "profile_type": self.profile_type,
            "handle": self.handle,
            "url": self.url,
            "social_key": self.social_key,
            "is_valid": self.is_valid,
            "confidence": round(self.confidence, 4),
            "healing_actions": list(self.healing_actions),
        }


def _normalize_idna_host(raw_host: str, actions: list[str]) -> str | None:
    """Fold a domain/host to lowercase ASCII IDNA/Punycode and validate its labels."""
    host = raw_host.strip().rstrip(".").lower()
    if not host or "." not in host:
        return None
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    if ascii_host != host:
        actions.append("IDNA_PUNYCODE_NORMALIZED")

    labels = ascii_host.split(".")
    for lbl in labels:
        if not _DOMAIN_LABEL_RE.match(lbl):
            return None
    if labels[-1].isdigit():
        return None
    return ascii_host


def _heal_domain_typos(domain: str, actions: list[str]) -> str:
    """Heal high-confidence webmail and TLD typos."""
    if domain in _DOMAIN_TYPO_MAP:
        actions.append("DOMAIN_TYPO_HEALED")
        return _DOMAIN_TYPO_MAP[domain]
    if domain.endswith(".con"):
        actions.append("DOMAIN_TYPO_HEALED")
        return domain[:-4] + ".com"
    if domain.endswith(".cmo") or domain.endswith(".ocm"):
        actions.append("DOMAIN_TYPO_HEALED")
        return domain[:-4] + ".com"
    return domain


def extract_registrable_domain(
    host: str,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Split a normalized host into (registrable_domain, subdomain, public_suffix, brand_stem)."""
    labels = host.split(".")
    if len(labels) < 2:
        return None, None, None, None

    last_two = f"{labels[-2]}.{labels[-1]}"
    if last_two in _MULTI_PART_PUBLIC_SUFFIXES:
        if len(labels) < 3:
            return None, None, last_two, None
        public_suffix = last_two
        reg_label = labels[-3]
        domain = f"{reg_label}.{public_suffix}"
        sub_labels = labels[:-3]
    else:
        public_suffix = labels[-1]
        reg_label = labels[-2]
        domain = f"{reg_label}.{public_suffix}"
        sub_labels = labels[:-2]

    subdomain = ".".join(sub_labels) if sub_labels else None
    comp = standardize_company(reg_label.replace("-", " "))
    brand_stem = comp.brand_stem or reg_label.upper()
    return domain, subdomain, public_suffix, brand_stem


def infer_country_from_domain(domain: str) -> str | None:
    """Infer unambiguous ISO-3166-1 alpha-2 country code from a domain's ccTLD."""
    if not domain or "." not in domain:
        return None
    labels = domain.lower().split(".")
    if f"{labels[-2]}.{labels[-1]}" == "com.co":
        return "CO"
    tld = labels[-1]
    return _CCTLD_TO_COUNTRY_ISO2.get(tld)


def standardize_email(raw_input: str | None) -> StandardizedEmail:
    """Standardize an email address per RFC 5321/5322 with subaddress, Gmail dot, and typo healing."""
    if raw_input is None:
        return StandardizedEmail(raw_input="")

    cleaned_raw = str(raw_input).strip()
    if not cleaned_raw:
        return StandardizedEmail(raw_input=str(raw_input))

    actions: list[str] = []
    working = cleaned_raw
    display_name: str | None = None

    # 1. Angle-bracket display name extraction: "Jane Doe <jane@acme.com>"
    m_angle = _ANGLE_EMAIL_RE.match(working)
    if m_angle:
        disp_cand = m_angle.group(1).strip().strip("\"'").strip()
        working = m_angle.group(2).strip()
        if disp_cand:
            display_name = " ".join(disp_cand.split())
            actions.append("DISPLAY_NAME_EXTRACTED")

    # 2. Strip mailto: scheme and any mailto query string
    if working.lower().startswith("mailto:"):
        working = working[7:].strip()
        if "?" in working:
            working = working.split("?", 1)[0].strip()
        actions.append("MAILTO_PREFIX_STRIPPED")

    if working.count("@") != 1:
        return StandardizedEmail(raw_input=str(raw_input), display_name=display_name)

    local_raw, domain_raw = working.split("@", 1)
    local_clean = local_raw.strip()
    if (
        not _LOCAL_PART_RE.match(local_clean)
        or local_clean.startswith(".")
        or local_clean.endswith(".")
        or ".." in local_clean
    ):
        return StandardizedEmail(raw_input=str(raw_input), display_name=display_name)

    norm_domain = _normalize_idna_host(domain_raw, actions)
    if norm_domain is None:
        return StandardizedEmail(raw_input=str(raw_input), display_name=display_name)

    norm_domain = _heal_domain_typos(norm_domain, actions)
    if norm_domain == "googlemail.com":
        norm_domain = "gmail.com"
        actions.append("GMAIL_DOMAIN_CANONICALIZED")

    raw_local_part = local_clean.lower()
    base_local = raw_local_part
    subaddress: str | None = None
    if "+" in base_local:
        base_local, sub_part = base_local.split("+", 1)
        if not base_local:
            return StandardizedEmail(raw_input=str(raw_input), display_name=display_name)
        subaddress = sub_part or None
        actions.append("SUBADDRESS_EXTRACTED")

    if norm_domain == "gmail.com" and "." in base_local:
        base_local = base_local.replace(".", "")
        actions.append("GMAIL_DOTS_CANONICALIZED")

    canonical_email = f"{base_local}@{norm_domain}"
    reg_domain, _, _, _ = extract_registrable_domain(norm_domain)
    effective_domain = reg_domain or norm_domain
    if effective_domain in _SENTINEL_DOMAINS:
        return StandardizedEmail(
            raw_input=str(raw_input),
            display_name=display_name,
            healing_actions=["SENTINEL_DOMAIN_REJECTED"],
        )

    is_disposable = effective_domain in _DISPOSABLE_EMAIL_DOMAINS or norm_domain in _DISPOSABLE_EMAIL_DOMAINS
    is_free_provider = effective_domain in _FREE_WEBMAIL_DOMAINS or norm_domain in _FREE_WEBMAIL_DOMAINS
    role_candidate = _ROLE_SEP_RE.sub("", base_local)
    is_role_account = base_local in _ROLE_ACCOUNT_PREFIXES or role_candidate in _ROLE_ACCOUNT_PREFIXES

    if is_disposable:
        email_type = "DISPOSABLE"
    elif is_role_account:
        email_type = "ROLE_ACCOUNT"
    elif is_free_provider:
        email_type = "FREE_WEBMAIL"
    else:
        email_type = "CORPORATE"

    inferred_country_iso2 = infer_country_from_domain(norm_domain)
    confidence = 0.92 if "DOMAIN_TYPO_HEALED" in actions else 0.99

    return StandardizedEmail(
        raw_input=str(raw_input),
        email=canonical_email,
        local_part=base_local,
        raw_local_part=raw_local_part,
        subaddress=subaddress,
        domain=norm_domain,
        display_name=display_name,
        email_type=email_type,
        is_free_provider=is_free_provider,
        is_role_account=is_role_account,
        is_disposable=is_disposable,
        inferred_country_iso2=inferred_country_iso2,
        email_key=canonical_email,
        is_valid=True,
        confidence=confidence,
        healing_actions=actions,
    )


def standardize_url(raw_input: str | None) -> StandardizedUrl:
    """Standardize a website URL, stripping tracking parameters and extracting eTLD+1 and brand_stem."""
    if raw_input is None:
        return StandardizedUrl(raw_input="")

    cleaned_raw = str(raw_input).strip()
    if not cleaned_raw or " " in cleaned_raw or "@" in cleaned_raw:
        return StandardizedUrl(raw_input=str(raw_input))

    actions: list[str] = []
    working = cleaned_raw

    if "://" not in working:
        if working.lower().startswith(("mailto:", "javascript:", "data:", "tel:")):
            return StandardizedUrl(raw_input=str(raw_input))
        working = "https://" + working
        actions.append("SCHEME_ADDED")

    parts = urlsplit(working)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        return StandardizedUrl(raw_input=str(raw_input))
    if scheme == "http":
        scheme = "https"
        actions.append("SCHEME_UPGRADED_HTTPS")

    raw_host = parts.hostname or ""
    norm_host = _normalize_idna_host(raw_host, actions)
    if norm_host is None:
        return StandardizedUrl(raw_input=str(raw_input))

    norm_host = _heal_domain_typos(norm_host, actions)
    if norm_host.startswith("www.") and len(norm_host) > 4:
        norm_host = norm_host[4:]
        actions.append("WWW_STRIPPED")

    domain, subdomain, public_suffix, brand_stem = extract_registrable_domain(norm_host)
    if domain is None:
        return StandardizedUrl(raw_input=str(raw_input))
    if domain in _SENTINEL_DOMAINS:
        return StandardizedUrl(
            raw_input=str(raw_input),
            healing_actions=["SENTINEL_DOMAIN_REJECTED"],
        )

    # Strip tracking query parameters
    kept_params: list[tuple[str, str]] = []
    stripped_tracking = False
    if parts.query:
        for k, v in parse_qsl(parts.query, keep_blank_values=True):
            kl = k.lower()
            if kl.startswith("utm_") or kl in _TRACKING_QUERY_PARAMS:
                stripped_tracking = True
            else:
                kept_params.append((k, v))
    if stripped_tracking:
        actions.append("TRACKING_PARAMS_STRIPPED")

    raw_path = parts.path or ""
    if raw_path == "/":
        norm_path = ""
    elif len(raw_path) > 1 and raw_path.endswith("/"):
        norm_path = raw_path.rstrip("/")
    else:
        norm_path = raw_path

    query_str = f"?{urlencode(kept_params)}" if kept_params else ""
    canonical_url = f"https://{norm_host}{norm_path}{query_str}"
    url_key = f"{domain}{norm_path.lower()}"
    inferred_country_iso2 = infer_country_from_domain(domain)

    return StandardizedUrl(
        raw_input=str(raw_input),
        url=canonical_url,
        scheme="https",
        host=norm_host,
        domain=domain,
        subdomain=subdomain,
        public_suffix=public_suffix,
        brand_stem=brand_stem,
        path=norm_path or "/",
        inferred_country_iso2=inferred_country_iso2,
        url_key=url_key,
        is_valid=True,
        confidence=0.98,
        healing_actions=actions,
    )


standardize_website = standardize_url

_PLATFORM_ALIASES: dict[str, str] = {
    "LINKEDIN": "LINKEDIN",
    "LI": "LINKEDIN",
    "X": "X",
    "TWITTER": "X",
    "GITHUB": "GITHUB",
    "GH": "GITHUB",
    "INSTAGRAM": "INSTAGRAM",
    "IG": "INSTAGRAM",
    "FACEBOOK": "FACEBOOK",
    "FB": "FACEBOOK",
    "YOUTUBE": "YOUTUBE",
    "YT": "YOUTUBE",
}

_HANDLE_RE = re.compile(r"^[A-Za-z0-9._\-]{1,100}$")


def standardize_social(
    raw_input: str | None,
    *,
    platform: str | None = None,
) -> StandardizedSocial:
    """Standardize a LinkedIn, X/Twitter, GitHub, Instagram, Facebook, or YouTube URL or @handle."""
    if raw_input is None:
        return StandardizedSocial(raw_input="")

    cleaned_raw = str(raw_input).strip()
    if not cleaned_raw:
        return StandardizedSocial(raw_input=str(raw_input))

    actions: list[str] = []
    working = cleaned_raw

    explicit_plat = (
        _PLATFORM_ALIASES.get(platform.strip().upper())
        if platform and platform.strip()
        else None
    )

    # Check prefix syntax like "twitter: @jack" or "linkedin: in/jane-doe"
    m_prefix = _SOCIAL_PREFIX_RE.match(working)
    if m_prefix and m_prefix.group(1).upper() in _PLATFORM_ALIASES:
        explicit_plat = _PLATFORM_ALIASES[m_prefix.group(1).upper()]
        working = m_prefix.group(2).strip()

    # Check if working is a URL or domain/path
    looks_like_url = (
        "://" in working
        or working.lower().startswith(
            (
                "www.",
                "linkedin.com/",
                "x.com/",
                "twitter.com/",
                "github.com/",
                "instagram.com/",
                "facebook.com/",
                "fb.com/",
                "youtube.com/",
                "youtu.be/",
            )
        )
        or (
            "/" in working
            and "." in working.split("/", 1)[0]
        )
    )

    if looks_like_url:
        url_work = working if "://" in working else f"https://{working}"
        parts = urlsplit(url_work)
        host = (parts.hostname or "").lower().rstrip(".")
        if host.startswith("www."):
            host = host[4:]
            actions.append("WWW_STRIPPED")
        elif host.startswith("mobile."):
            host = host[7:]
            actions.append("WWW_STRIPPED")

        path_segs = [s for s in (parts.path or "").split("/") if s]
        if not path_segs:
            return StandardizedSocial(raw_input=str(raw_input))

        if host.endswith("linkedin.com"):
            plat = "LINKEDIN"
            if path_segs[0].lower() in ("in", "pub") and len(path_segs) >= 2:
                prof_type = "PERSON"
                handle = path_segs[1].lstrip("@")
                canon_url = f"https://linkedin.com/in/{handle}"
            elif path_segs[0].lower() in ("company", "school", "showcase") and len(path_segs) >= 2:
                prof_type = "COMPANY"
                handle = path_segs[1].lstrip("@")
                canon_url = f"https://linkedin.com/company/{handle}"
            else:
                prof_type = "PERSON"
                handle = path_segs[0].lstrip("@")
                canon_url = f"https://linkedin.com/in/{handle}"
        elif host in ("x.com", "twitter.com"):
            plat = "X"
            if host == "twitter.com":
                actions.append("TWITTER_CANONICALIZED_TO_X")
            prof_type = "USER"
            handle = path_segs[0].lstrip("@")
            canon_url = f"https://x.com/{handle}"
        elif host == "github.com":
            plat = "GITHUB"
            prof_type = "USER"
            handle = path_segs[0].lstrip("@")
            canon_url = f"https://github.com/{handle}"
        elif host == "instagram.com":
            plat = "INSTAGRAM"
            prof_type = "USER"
            handle = path_segs[0].lstrip("@")
            canon_url = f"https://instagram.com/{handle}"
        elif host in ("facebook.com", "fb.com"):
            plat = "FACEBOOK"
            prof_type = "USER"
            handle = path_segs[0].lstrip("@")
            canon_url = f"https://facebook.com/{handle}"
        elif host in ("youtube.com", "youtu.be"):
            plat = "YOUTUBE"
            prof_type = "CHANNEL"
            first_seg = path_segs[0]
            if first_seg.startswith("@"):
                handle = first_seg[1:]
                canon_url = f"https://youtube.com/@{handle}"
            elif first_seg.lower() in ("c", "user") and len(path_segs) >= 2:
                handle = path_segs[1].lstrip("@")
                canon_url = f"https://youtube.com/@{handle}"
            elif first_seg.lower() == "channel" and len(path_segs) >= 2:
                handle = path_segs[1]
                canon_url = f"https://youtube.com/channel/{handle}"
            else:
                handle = first_seg.lstrip("@")
                canon_url = f"https://youtube.com/@{handle}"
        else:
            return StandardizedSocial(raw_input=str(raw_input))

        if not _HANDLE_RE.match(handle):
            return StandardizedSocial(raw_input=str(raw_input))

        return StandardizedSocial(
            raw_input=str(raw_input),
            platform=plat,
            profile_type=prof_type,
            handle=handle,
            url=canon_url,
            social_key=f"{plat}|{handle.lower()}",
            is_valid=True,
            confidence=0.98,
            healing_actions=actions,
        )

    # Handle bare @handle or platform-qualified handle (e.g. "@openai" or "in/jane-doe")
    if working.lower().startswith("in/") or working.lower().startswith("company/"):
        seg_type, handle_part = working.split("/", 1)
        handle = handle_part.strip("/").lstrip("@")
        if not _HANDLE_RE.match(handle):
            return StandardizedSocial(raw_input=str(raw_input))
        prof_type = "COMPANY" if seg_type.lower() == "company" else "PERSON"
        subpath = "company" if prof_type == "COMPANY" else "in"
        actions.append("HANDLE_EXPANDED_TO_URL")
        return StandardizedSocial(
            raw_input=str(raw_input),
            platform="LINKEDIN",
            profile_type=prof_type,
            handle=handle,
            url=f"https://linkedin.com/{subpath}/{handle}",
            social_key=f"LINKEDIN|{handle.lower()}",
            is_valid=True,
            confidence=0.95,
            healing_actions=actions,
        )

    if working.startswith("@") or explicit_plat is not None:
        handle = working.lstrip("@").strip("/")
        if not _HANDLE_RE.match(handle):
            return StandardizedSocial(raw_input=str(raw_input))
        plat = explicit_plat or "X"
        actions.append("HANDLE_EXPANDED_TO_URL")
        if plat == "LINKEDIN":
            prof_type = "PERSON"
            canon_url = f"https://linkedin.com/in/{handle}"
        elif plat == "GITHUB":
            prof_type = "USER"
            canon_url = f"https://github.com/{handle}"
        elif plat == "INSTAGRAM":
            prof_type = "USER"
            canon_url = f"https://instagram.com/{handle}"
        elif plat == "FACEBOOK":
            prof_type = "USER"
            canon_url = f"https://facebook.com/{handle}"
        elif plat == "YOUTUBE":
            prof_type = "CHANNEL"
            canon_url = f"https://youtube.com/@{handle}"
        else:
            prof_type = "USER"
            canon_url = f"https://x.com/{handle}"

        return StandardizedSocial(
            raw_input=str(raw_input),
            platform=plat,
            profile_type=prof_type,
            handle=handle,
            url=canon_url,
            social_key=f"{plat}|{handle.lower()}",
            is_valid=True,
            confidence=0.92 if explicit_plat else 0.88,
            healing_actions=actions,
        )

    return StandardizedSocial(raw_input=str(raw_input))


def batch_standardize_emails(inputs: Sequence[str | None]) -> list[StandardizedEmail]:
    """Batch-standardize a sequence of email addresses."""
    return [standardize_email(item) for item in inputs]


def batch_standardize_urls(inputs: Sequence[str | None]) -> list[StandardizedUrl]:
    """Batch-standardize a sequence of website URLs."""
    return [standardize_url(item) for item in inputs]


batch_standardize_websites = batch_standardize_urls


def batch_standardize_socials(
    inputs: Sequence[str | None],
    *,
    platform: str | None = None,
) -> list[StandardizedSocial]:
    """Batch-standardize a sequence of social media profiles or handles."""
    return [standardize_social(item, platform=platform) for item in inputs]


@dataclass(slots=True)
class EmailComparisonResult:
    """Result of comparing two email records for entity resolution."""

    is_match: bool
    score: float
    match_type: str
    email_a: StandardizedEmail
    email_b: StandardizedEmail

    def to_dict(self) -> dict[str, Any]:
        """Serialize the email comparison result into a JSON-compatible dictionary."""
        return {
            "is_match": self.is_match,
            "score": round(self.score, 4),
            "match_type": self.match_type,
            "email_a": self.email_a.to_dict(),
            "email_b": self.email_b.to_dict(),
        }


def compare_emails(
    email_a: str | StandardizedEmail | None,
    email_b: str | StandardizedEmail | None,
) -> EmailComparisonResult:
    """Compare two email addresses across canonical email_key, subaddress/Gmail-dot equivalence, and corporate local-part."""
    ea = email_a if isinstance(email_a, StandardizedEmail) else standardize_email(email_a)
    eb = email_b if isinstance(email_b, StandardizedEmail) else standardize_email(email_b)

    if not ea.is_valid or not eb.is_valid or not ea.email_key or not eb.email_key:
        return EmailComparisonResult(
            is_match=False,
            score=0.0,
            match_type="INVALID_INPUT",
            email_a=ea,
            email_b=eb,
        )

    if ea.email_key == eb.email_key:
        return EmailComparisonResult(
            is_match=True,
            score=1.0,
            match_type="EXACT_EMAIL_KEY",
            email_a=ea,
            email_b=eb,
        )

    if (
        ea.local_part == eb.local_part
        and not ea.is_free_provider
        and not eb.is_free_provider
        and not ea.is_disposable
        and not eb.is_disposable
        and ea.domain
        and eb.domain
    ):
        reg_a, _, _, stem_a = extract_registrable_domain(ea.domain)
        reg_b, _, _, stem_b = extract_registrable_domain(eb.domain)
        if reg_a == reg_b or (stem_a and stem_a == stem_b and len(stem_a) >= 3):
            return EmailComparisonResult(
                is_match=True,
                score=0.92,
                match_type="CORPORATE_BRAND_LOCAL_MATCH",
                email_a=ea,
                email_b=eb,
            )

    return EmailComparisonResult(
        is_match=False,
        score=0.0,
        match_type="NO_MATCH",
        email_a=ea,
        email_b=eb,
    )


@dataclass(slots=True)
class UrlComparisonResult:
    """Result of comparing two website URL records for entity resolution."""

    is_match: bool
    score: float
    match_type: str
    url_a: StandardizedUrl
    url_b: StandardizedUrl

    def to_dict(self) -> dict[str, Any]:
        """Serialize the URL comparison result into a JSON-compatible dictionary."""
        return {
            "is_match": self.is_match,
            "score": round(self.score, 4),
            "match_type": self.match_type,
            "url_a": self.url_a.to_dict(),
            "url_b": self.url_b.to_dict(),
        }


def compare_urls(
    url_a: str | StandardizedUrl | None,
    url_b: str | StandardizedUrl | None,
) -> UrlComparisonResult:
    """Compare two website URLs across canonical url_key, registrable domain, and brand_stem."""
    ua = url_a if isinstance(url_a, StandardizedUrl) else standardize_url(url_a)
    ub = url_b if isinstance(url_b, StandardizedUrl) else standardize_url(url_b)

    if not ua.is_valid or not ub.is_valid or not ua.domain or not ub.domain:
        return UrlComparisonResult(
            is_match=False,
            score=0.0,
            match_type="INVALID_INPUT",
            url_a=ua,
            url_b=ub,
        )

    if ua.url_key == ub.url_key:
        return UrlComparisonResult(
            is_match=True,
            score=1.0,
            match_type="EXACT_URL_KEY",
            url_a=ua,
            url_b=ub,
        )

    if ua.domain == ub.domain:
        return UrlComparisonResult(
            is_match=True,
            score=0.95,
            match_type="SAME_REGISTRABLE_DOMAIN",
            url_a=ua,
            url_b=ub,
        )

    if ua.brand_stem and ua.brand_stem == ub.brand_stem and len(ua.brand_stem) >= 3:
        return UrlComparisonResult(
            is_match=True,
            score=0.88,
            match_type="SAME_BRAND_STEM",
            url_a=ua,
            url_b=ub,
        )

    return UrlComparisonResult(
        is_match=False,
        score=0.0,
        match_type="NO_MATCH",
        url_a=ua,
        url_b=ub,
    )


compare_websites = compare_urls


