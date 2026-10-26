"""Script-based country detection and single-line splitting for non-Latin addresses.

Used only when the caller supplied no country. Detection is deliberately conservative: Latin-script text is never
labelled, and text only counts as non-Latin when non-Latin letters make up a meaningful share of all letters.
"""

import re
from typing import Optional, Tuple

_SCRIPT_FAMILIES = (
    frozenset({"JPN", "KOR", "CHN", "TWN", "HKG", "MAC", "PRK"}),
    frozenset({"RUS", "BGR", "UKR", "SRB", "BLR", "KAZ", "MKD", "MNE", "MDA", "KGZ", "TJK", "MNG", "BIH"}),
    frozenset({"GRC", "CYP"}),
    frozenset({"ISR"}),
    frozenset({"GEO"}),
    frozenset({"ARM"}),
    frozenset({"BGD", "IND"}),
    frozenset({"LKA"}),
    frozenset({"MMR"}),
    frozenset({"KHM"}),
    frozenset({"LAO"}),
    frozenset({"ETH", "ERI"}),
    frozenset({"THA"}),
)


def country_matches_script(iso: str, script_iso: str) -> bool:
    """True when ``iso`` is a country that already uses the writing system implied by ``script_iso``."""
    return any(iso in fam and script_iso in fam for fam in _SCRIPT_FAMILIES)


_RE_HAN = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_RE_KANA = re.compile(r"[぀-ヿㇰ-ㇿｦ-ﾟ]")
_RE_HANGUL = re.compile(r"[가-힯ᄀ-ᇿ㄰-㆏]")
_RE_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
_RE_GREEK = re.compile(r"[Ͱ-Ͽἀ-῿]")
_RE_HEBREW = re.compile(r"[\u0590-\u05FF]")
_RE_GEORGIAN = re.compile(r"[\u10A0-\u10FF\u1C90-\u1CBF]")
_RE_ARMENIAN = re.compile(r"[\u0530-\u058F]")
_RE_BENGALI = re.compile(r"[\u0980-\u09FF]")
_RE_SINHALA = re.compile(r"[\u0D80-\u0DFF]")
_RE_MYANMAR = re.compile(r"[\u1000-\u109F]")
_RE_KHMER = re.compile(r"[\u1780-\u17FF]")
_RE_LAO = re.compile(r"[\u0E80-\u0EFF]")
_RE_ETHIOPIC = re.compile(r"[\u1200-\u137F]")
_RE_THAI = re.compile(r"[\u0E00-\u0E7F]")
_RE_LATIN_LETTER = re.compile(r"[A-Za-zÀ-ɏ]")

_RE_JP_PREF = re.compile(r"(?:^|[\s,〒\d-])(?:北海道|[一-鿿]{2,3}[都府県])")
_RE_CN_MARK = re.compile(r"[省市区县縣區号號路街镇乡村]")
_RE_UA_LETTERS = re.compile(r"[іїєґІЇЄҐ]")
_RE_SR_LETTERS = re.compile(r"[ђћџљњЂЋЏЉЊ]")
_RE_BG_MARKERS = re.compile(
    r"(?:^|[\s,])(?:бул\.?|гр\.|ж\.к\.|кв\.\s*\D|област|община|софия|пловдив|варна|бургас)(?=$|[\s,.])", re.IGNORECASE
)

_MIN_SCRIPT_SHARE = 0.3

_ZERO_WIDTH = re.compile("[​⁠﻿‌‍]")
_ZERO_WIDTH_NO_JOINERS = re.compile("[​⁠﻿]")
_RE_INDIC_PERSIAN = re.compile("[؀-ۿऀ-෿]")


def strip_zero_width(text: str) -> str:
    """Remove zero-width junk (ZWSP, WJ, BOM, ZWNJ, ZWJ).

    ZWNJ/ZWJ are kept only inside Arabic-script and Indic-script text, where they are orthographically meaningful.
    """
    if not text or not _ZERO_WIDTH.search(text):
        return text
    if _RE_INDIC_PERSIAN.search(text):
        return _ZERO_WIDTH_NO_JOINERS.sub("", text)
    return _ZERO_WIDTH.sub("", text)


def _share(rx: "re.Pattern[str]", text: str) -> float:
    script = len(rx.findall(text))
    if not script:
        return 0.0
    latin = len(_RE_LATIN_LETTER.findall(text))
    return script / (script + latin)


def detect_script_country(text: Optional[str]) -> Optional[str]:
    """ISO-3166 alpha-3 guess from the writing system, or None for Latin/ambiguous text."""
    if not text:
        return None
    if _share(_RE_HANGUL, text) >= _MIN_SCRIPT_SHARE:
        return "KOR"
    han_kana_letters = len(_RE_HAN.findall(text)) + len(_RE_KANA.findall(text))
    if han_kana_letters:
        latin = len(_RE_LATIN_LETTER.findall(text))
        if han_kana_letters / (han_kana_letters + latin) >= _MIN_SCRIPT_SHARE:
            if _RE_KANA.search(text) or _RE_JP_PREF.search(text):
                return "JPN"
            if _RE_CN_MARK.search(text):
                return "CHN"
        return None
    if _share(_RE_GREEK, text) >= _MIN_SCRIPT_SHARE:
        return "GRC"
    if _share(_RE_HEBREW, text) >= _MIN_SCRIPT_SHARE:
        return "ISR"
    if _share(_RE_GEORGIAN, text) >= _MIN_SCRIPT_SHARE:
        return "GEO"
    if _share(_RE_ARMENIAN, text) >= _MIN_SCRIPT_SHARE:
        return "ARM"
    if _share(_RE_BENGALI, text) >= _MIN_SCRIPT_SHARE:
        return "BGD"
    if _share(_RE_SINHALA, text) >= _MIN_SCRIPT_SHARE:
        return "LKA"
    if _share(_RE_MYANMAR, text) >= _MIN_SCRIPT_SHARE:
        return "MMR"
    if _share(_RE_KHMER, text) >= _MIN_SCRIPT_SHARE:
        return "KHM"
    if _share(_RE_LAO, text) >= _MIN_SCRIPT_SHARE:
        return "LAO"
    if _share(_RE_ETHIOPIC, text) >= _MIN_SCRIPT_SHARE:
        return "ETH"
    if _share(_RE_THAI, text) >= _MIN_SCRIPT_SHARE:
        return "THA"
    if _share(_RE_CYRILLIC, text) >= _MIN_SCRIPT_SHARE:
        if _RE_UA_LETTERS.search(text):
            return "UKR"
        if _RE_SR_LETTERS.search(text):
            return "SRB"
        if _RE_BG_MARKERS.search(text):
            return "BGR"
        return "RUS"
    return None


_RE_JP_POSTAL = re.compile(r"〒?\s*(\d{3}-?\d{4})")
_RE_JP_SPLIT = re.compile(r"^(北海道|[一-鿿]{2,3}?[都府県])\s*(.*)$")
_RE_JP_CITY = re.compile(r"^((?:[぀-ヿ一-鿿]{1,6}?(?:市|郡)[぀-ヿ一-鿿]{0,6}?(?:区|町|村)?)|[぀-ヿ一-鿿]{1,5}?(?:区|町|村))\s*(.*)$")
_RE_CN_MUNI = re.compile(r"^(北京市|上海市|天津市|重庆市|重慶市)\s*(.*)$")
_RE_CN_PROV = re.compile(r"^([一-鿿]{2,6}?(?:省|自治区|特别行政区))\s*(.*)$")
_RE_CN_CITY = re.compile(r"^([一-鿿]{1,5}?(?:市|自治州|地区|盟))\s*(.*)$")
_RE_CN_DISTRICT = re.compile(r"^([一-鿿]{1,5}?(?:区|县|縣|區|旗))\s*(.*)$")
_RE_KR_STATE = re.compile(r"^(\S*?(?:특별시|광역시|특별자치시|특별자치도|도)|서울|부산|대구|인천|광주|대전|울산|세종|제주)\s+(.*)$")
_RE_KR_CITY = re.compile(r"^(\S+?[시군구])(?:\s+(\S+?구))?\s+(.*)$")

_RE_STREET_TOKEN = re.compile(
    r"^(?:ул|улица|пр|просп|проспект|пер|переулок|бул|бульвар|ш|шоссе|наб|пл|площадь|вул|ж\.к|жк|д|дом|кв|оф)\b\.?",
    re.IGNORECASE,
)
_RE_CITY_PREFIX = re.compile(r"^(?:г|гр|город|м|с|пос|пгт)\.?\s+", re.IGNORECASE)
_RE_REGION = re.compile(r"(?:обл(?:асть|\.)?|край|респ(?:ублика|\.)?|област)\b", re.IGNORECASE)


def _take_postal(text: str, pattern: "re.Pattern[str]") -> Tuple[str, str]:
    m = pattern.search(text)
    if not m:
        return text, ""
    postal = m.group(1)
    rest = (text[: m.start()] + " " + text[m.end():]).strip(" ,;")
    return " ".join(rest.split()), postal


def _split_jp(text: str) -> Tuple[str, str, str, str]:
    rest, postal = _take_postal(text, _RE_JP_POSTAL)
    state = city = ""
    m = _RE_JP_SPLIT.match(rest)
    if m:
        state, rest = m.group(1), m.group(2)
        mc = _RE_JP_CITY.match(rest)
        if mc and mc.group(2):
            city, rest = mc.group(1), mc.group(2)
    return rest, city, state, postal


def _split_cn(text: str) -> Tuple[str, str, str, str]:
    rest, postal = _take_postal(text, re.compile(r"(?<!\d)(\d{6})(?!\d)"))
    state = city = ""
    m = _RE_CN_MUNI.match(rest)
    if m:
        state, rest = m.group(1), m.group(2)
        md = _RE_CN_DISTRICT.match(rest)
        if md and md.group(2):
            city, rest = md.group(1), md.group(2)
        return rest, city, state, postal
    m = _RE_CN_PROV.match(rest)
    if m:
        state, rest = m.group(1), m.group(2)
    mc = _RE_CN_CITY.match(rest)
    if mc and mc.group(2):
        city, rest = mc.group(1), mc.group(2)
    return rest, city, state, postal


def _split_kr(text: str) -> Tuple[str, str, str, str]:
    rest, postal = _take_postal(text, re.compile(r"(?<!\d)(\d{5})(?!\d)"))
    state = city = ""
    m = _RE_KR_STATE.match(rest)
    if m:
        state, rest = m.group(1), m.group(2)
    mc = _RE_KR_CITY.match(rest)
    if mc:
        city = mc.group(1) + (" " + mc.group(2) if mc.group(2) else "")
        rest = mc.group(3)
    return rest, city, state, postal


def _split_cyrillic(text: str, postal_len: int) -> Tuple[str, str, str, str]:
    rest, postal = _take_postal(text, re.compile(r"(?<!\d)(\d{%d})(?!\d)\s*$" % postal_len))
    parts = [p.strip() for p in rest.split(",") if p.strip()]
    city = state = ""
    street_parts = []
    for i, p in enumerate(parts):
        if not city and _RE_CITY_PREFIX.match(p) and not _RE_STREET_TOKEN.match(p):
            city = _RE_CITY_PREFIX.sub("", p).strip()
        elif not state and _RE_REGION.search(p) and not re.search(r"\d", p):
            state = p
        elif not city and i == 0 and len(parts) > 1 and not re.search(r"\d", p) and not _RE_STREET_TOKEN.match(p):
            city = p
        else:
            street_parts.append(p)
    return ", ".join(street_parts), city, state, postal


def split_script_single_line(text: str, iso: str) -> Optional[Tuple[str, str, str, str]]:
    """Split a single-line non-Latin address into (street, city, state, postal); None if not applicable."""
    if not text:
        return None
    if iso == "JPN":
        res = _split_jp(text)
    elif iso == "CHN":
        res = _split_cn(text)
    elif iso == "KOR":
        res = _split_kr(text)
    elif iso in ("RUS", "BGR", "UKR", "SRB"):
        res = _split_cyrillic(text, {"RUS": 6, "BGR": 4, "UKR": 5, "SRB": 5}[iso])
    else:
        return None
    if not res[0]:
        return None
    return res
