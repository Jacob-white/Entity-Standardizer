"""Tests for Sub-National Intelligence, Timezones, TCPA Windows, Multi-Tier Caching, and Stewardship Audit Ledger."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from phone_standardizer import (
    HealingAction,
    LRUCache,
    MultiTierCache,
    PhoneStewardshipLedger,
    SQLiteCache,
    clear_cache,
    configure_cache,
    evaluate_calling_window,
    explain_phone,
    extract_phones_from_text,
    get_cache_stats,
    get_default_cache,
    make_cache_key,
    resolve_carrier_hint,
    resolve_locality,
    resolve_timezones,
    standardize_phone,
)
from phone_standardizer.mcp import handle_mcp_request
from phone_standardizer.server import app


def test_intelligence_locality_timezones_and_carrier() -> None:
    # Locality lookup
    assert resolve_locality(None, None) is None
    assert resolve_locality("1", "415") == "San Francisco"
    assert resolve_locality("44", "20") == "London"
    assert resolve_locality("81", "3") == "Tokyo"
    assert resolve_locality("1", "999") is None

    # Timezone lookup
    assert resolve_timezones("US", "CA") == ("America/Los_Angeles",)
    assert resolve_timezones("US", "FL") == ("America/New_York", "America/Chicago")
    assert resolve_timezones("GB", None) == ("Europe/London",)
    assert resolve_timezones("AQ", None) == ("UTC",)

    # Carrier MNO lookup
    assert resolve_carrier_hint(None, None) is None
    assert resolve_carrier_hint("DE", "15123456789") == "Telekom Deutschland"
    assert resolve_carrier_hint("DE", "17223456789") == "Vodafone Germany"
    assert resolve_carrier_hint("DE", "17623456789") == "Telefónica O2 Germany"
    assert resolve_carrier_hint("DE", "3012345678") is None
    assert resolve_carrier_hint("CN", "13912345678") == "China Mobile"
    assert resolve_carrier_hint("CH", "791234567") == "Swisscom"


def test_tcpa_calling_window_evaluation() -> None:
    # 15:00 UTC is 10:00 EST / 11:00 EDT in New York -> callable
    dt_day = datetime(2026, 10, 21, 15, 0, 0, tzinfo=timezone.utc)
    win_ok = evaluate_calling_window(("America/New_York",), utc_dt=dt_day)
    assert win_ok.is_callable_now is True

    # Naive datetime (converted to UTC) at 04:00 UTC -> 00:00 EDT in New York -> not callable
    dt_night = datetime(2026, 10, 21, 4, 0, 0)
    win_night = evaluate_calling_window(("America/New_York",), utc_dt=dt_night)
    assert win_night.is_callable_now is False

    # Empty timezones fallback to UTC
    win_utc = evaluate_calling_window((), utc_dt=dt_day)
    assert win_utc.timezones == ("UTC",)
    assert win_utc.is_callable_now is True


def test_brazil_legacy_mobile_and_free_text_extraction() -> None:
    # Brazil legacy 10-digit mobile (11 + 88765432 -> +5511988765432)
    br_leg = standardize_phone("+55 11 8876-5432")
    assert br_leg.e164 == "+5511988765432"
    assert HealingAction.BRAZIL_MOBILE_9_INSERTED in br_leg.healing_actions

    # Free-text phone extraction
    assert extract_phones_from_text(None) == []
    assert extract_phones_from_text("") == []
    sample_doc = (
        "Contact our San Francisco desk at (415) 555-2671 or our New York desk "
        "at 212-555-0299 ext 12. Duplicate: (415) 555-2671. Invalid: 111-111-1111."
    )
    found = extract_phones_from_text(sample_doc, default_country="US")
    assert len(found) == 2
    assert found[0].e164 == "+14155552671"
    assert found[1].e164 == "+12125550299"
    assert found[1].extension == "12"


def test_multi_tier_cache_l1_and_l2(tmp_path: Path) -> None:
    key1 = make_cache_key("(415) 555-2671", "US", "US")
    key2 = make_cache_key("(212) 555-0299", None, "US")
    key3 = make_cache_key(None, None, "US")
    assert key1 == "US|US|(415) 555-2671"
    assert key3 == "US||"

    rec1 = standardize_phone("(415) 555-2671")
    rec2 = standardize_phone("(212) 555-0299")

    # Test L1 eviction & update in-place
    lru = LRUCache(max_size=1)
    assert lru.get(key1) is None
    lru.set(key1, rec1)
    lru.set(key1, rec1)  # update existing key
    assert lru.get(key1) == rec1
    lru.set(key2, rec2)  # evicts key1
    assert lru.evictions == 1
    assert lru.get(key1) is None

    # Test MultiTierCache with L2 SQLite
    db_file = tmp_path / "cache.sqlite"
    cache = configure_cache(l1_max_size=2, sqlite_path=db_file)
    assert get_default_cache() is cache
    assert cache.get(key1) is None
    cache.set(key1, rec1)
    assert cache.get(key1) == rec1

    # Clear L1 only to test L2 hit promotion back to L1
    cache.l1.clear()
    promoted = cache.get(key1)
    assert promoted is not None and promoted.e164 == "+14155552671"
    stats = get_cache_stats()
    assert stats["l2_enabled"] is True and stats["l2_hits"] == 1

    clear_cache()
    assert cache.get(key1) is None

    # Also test MultiTierCache without L2
    mem_only = MultiTierCache(l1_max_size=4, sqlite_path=None)
    assert mem_only.get(key1) is None
    mem_only.set(key1, rec1)
    assert mem_only.stats()["l2_enabled"] is False
    mem_only.clear()

    # Direct SQLiteCache test
    sql_c = SQLiteCache(":memory:")
    assert sql_c.get(key1) is None


def test_explain_and_stewardship_ledger() -> None:
    dt = datetime(2026, 10, 21, 16, 0, 0, tzinfo=timezone.utc)
    rep = explain_phone("(415) 555-2671", utc_dt=dt)
    assert rep["intelligence"]["locality"] == "San Francisco"
    assert rep["intelligence"]["timezones"] == ["America/Los_Angeles"]
    assert rep["explanation"]["requires_human_review"] is False

    # Ledger
    ledger = PhoneStewardshipLedger(":memory:")
    clean_phone = standardize_phone("(415) 555-2671")
    assert ledger.record_if_flagged(clean_phone) is None

    flagged_phone = standardize_phone("(415) 555-0142")  # Fictitious 555-01XX -> FUZZY_REVIEW
    entry_id = ledger.record_if_flagged(flagged_phone)
    assert entry_id is not None

    pending = ledger.list_pending()
    assert len(pending) == 1
    assert pending[0]["e164"] == "+14155550142"

    assert ledger.resolve_entry(entry_id, status="APPROVED", note="Test fixture") is True
    assert ledger.list_pending() == []

    # FastAPI /v1/explain and MCP explain_phone
    client = TestClient(app)
    r_exp = client.post("/v1/explain", json={"phone": "(415) 555-2671"})
    assert r_exp.status_code == 200
    assert r_exp.json()["intelligence"]["locality"] == "San Francisco"

    mcp_exp = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {"name": "explain_phone", "arguments": {"phone": "+49 151 23456789"}},
        }
    )
    assert "Telekom Deutschland" in mcp_exp["result"]["content"][0]["text"]
