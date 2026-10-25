"""Throughput and latency benchmark suite across all 6 Entity-Standardizer pillars."""

from __future__ import annotations

import json
import statistics
import time

import entity_standardizer._native_dispatch as nd
from entity_standardizer import (
    batch_standardize,
    batch_standardize_companies,
    batch_standardize_contacts,
    batch_standardize_persons,
    batch_standardize_phones,
    batch_standardize_urls,
    clear_cache,
    get_engine_info,
    standardize_batch_e164_dispatch,
    standardize_phone,
)
from entity_standardizer.address import _native_dispatch as addr_nd

SAMPLE_PHONES = [
    "(415) 555-2671",
    "+44 (0) 20 7946 0912 ext. 402",
    "030 12345678",
    "1-800-FLOWERS",
    "+81 3-1234-5678",
    "＋８１ ３-１２３４-５６７８",
    "0033 1 42 68 55 00",
    "212.555.0199 #88",
    "+61 2 9374 4000",
    "415-555-267O",
]

SAMPLE_ADDRESSES = [
    {"street1": "350 Fifth Avenue Suite 4200", "city": "New York", "state": "NY", "postal_code": "10118", "country": "US"},
    {"street1": "1600 Amphitheatre Pkwy", "city": "Mountain View", "state": "CA", "postal_code": "94043", "country": "US"},
    {"street1": "10 Downing Street", "city": "London", "postal_code": "SW1A 2AA", "country": "GB"},
    {"street1": "Friedrichstraße 123", "city": "Berlin", "postal_code": "10117", "country": "DE"},
]

SAMPLE_COMPANIES = [
    "The I. B. M. & Co. L.L.C.",
    "Société Générale S.A.",
    "Novo Nordisk A/S",
    "KKR Opportunities III S.à r.l.",
    "Đorđe & Łódź Holdings GmbH",
    "Brașov & Constanța Logistics S.A.",
    "Booking.com B.V.",
]

SAMPLE_PERSONS = [
    "Dr. François-Xavier D'Angelo Jr., MD, PhD",
    "Prof. Đorđe Kovačević III",
    "María José Carreño Quiñones",
    "Sören Ørsted-Lindqvist",
    "Nguyễn Thị Minh Khai",
]

SAMPLE_WEB = [
    "https://WWW.Example.COM:443/path/to/page/?utm_source=newsletter&id=42#section",
    "http://sub.booking.com:80/hotels?fbclid=12345",
    "https://github.com/Jacob-white/Entity-Standardizer/",
    "www.deutsche-bank.de/home?gclid=abc",
]

SAMPLE_CONTACTS = [
    {
        "person": "Dr. Jane A. Doe, PhD",
        "company": "Acme Holdings, Inc.",
        "phone": "(415) 555-2671",
        "address": "350 Fifth Ave Ste 4200, New York, NY 10118",
        "email": "jane.doe+vip@acme.com",
        "url": "https://www.acme.com/?utm_medium=cpc",
        "country": "US",
    },
    {
        "person": "Jean-Luc Picard",
        "company": "Société Générale S.A.",
        "phone": "+33 1 42 68 55 00",
        "address": "29 Boulevard Haussmann, 75009 Paris",
        "email": "jpicard@socgen.fr",
        "country": "FR",
    },
]


def _set_pure_mode(pure: bool, saved_nd_mod, saved_addr_flag: bool) -> None:
    if pure:
        nd._native_mod = None
        addr_nd._FORCE_PURE_PYTHON = True
    else:
        nd._native_mod = saved_nd_mod
        addr_nd._FORCE_PURE_PYTHON = saved_addr_flag


def run_benchmarks() -> dict:
    saved_nd_mod = nd._native_mod
    saved_addr_flag = addr_nd._FORCE_PURE_PYTHON

    # 1. Cold-cache single-call latency (Phone)
    clear_cache()
    latencies_us: list[float] = []
    for _ in range(200):
        clear_cache()
        for raw in SAMPLE_PHONES:
            t0 = time.perf_counter_ns()
            standardize_phone(raw, "US")
            latencies_us.append((time.perf_counter_ns() - t0) / 1000.0)

    # 2. Warm-cache single-call latency (Phone)
    for raw in SAMPLE_PHONES:
        standardize_phone(raw, "US")
    warm_latencies_us: list[float] = []
    for _ in range(500):
        for raw in SAMPLE_PHONES:
            t0 = time.perf_counter_ns()
            standardize_phone(raw, "US")
            warm_latencies_us.append((time.perf_counter_ns() - t0) / 1000.0)

    # 3. Batch E.164 throughput (10,000 numbers)
    batch_10k = SAMPLE_PHONES * 1000
    t0 = time.perf_counter()
    res_e164_native = standardize_batch_e164_dispatch(batch_10k, "1")
    elapsed_batch = time.perf_counter() - t0
    throughput_per_sec = len(batch_10k) / max(elapsed_batch, 1e-9)

    # 4. All 6 Pillars: Native vs Pure-Python Throughput & 100% Parity Verification
    phone_batch = SAMPLE_PHONES * 100
    addr_batch = SAMPLE_ADDRESSES * 100
    comp_batch = SAMPLE_COMPANIES * 200
    person_batch = SAMPLE_PERSONS * 200
    web_batch = SAMPLE_WEB * 200
    contact_batch = SAMPLE_CONTACTS * 100

    pillars_report: dict[str, dict] = {}

    try:
        # Warm up one-time reference/offline index singletons before timing
        _set_pure_mode(False, saved_nd_mod, saved_addr_flag)
        batch_standardize(SAMPLE_ADDRESSES[:1], max_workers=1)
        batch_standardize_contacts(SAMPLE_CONTACTS[:1])

        # Native mode runs
        clear_cache()
        t0 = time.perf_counter()
        nat_phones = [p.to_dict() for p in batch_standardize_phones(phone_batch, default_country="US")]
        t_phone_nat = time.perf_counter() - t0

        clear_cache()
        t0 = time.perf_counter()
        nat_addrs = [a.as_dict() for a in batch_standardize(addr_batch, max_workers=1)]
        t_addr_nat = time.perf_counter() - t0

        t0 = time.perf_counter()
        nat_comps = [c.to_dict() for c in batch_standardize_companies(comp_batch)]
        t_comp_nat = time.perf_counter() - t0

        t0 = time.perf_counter()
        nat_persons = [p.to_dict() for p in batch_standardize_persons(person_batch)]
        t_person_nat = time.perf_counter() - t0

        t0 = time.perf_counter()
        nat_webs = [w.to_dict() for w in batch_standardize_urls(web_batch)]
        t_web_nat = time.perf_counter() - t0

        clear_cache()
        t0 = time.perf_counter()
        nat_contacts = [c.to_dict() for c in batch_standardize_contacts(contact_batch)]
        t_contact_nat = time.perf_counter() - t0

        # Pure-Python mode runs
        _set_pure_mode(True, saved_nd_mod, saved_addr_flag)
        res_e164_pure = standardize_batch_e164_dispatch(batch_10k, "1")
        assert res_e164_native == res_e164_pure, "E.164 batch parity mismatch"

        clear_cache()
        t0 = time.perf_counter()
        pure_phones = [p.to_dict() for p in batch_standardize_phones(phone_batch, default_country="US")]
        t_phone_pure = time.perf_counter() - t0
        assert nat_phones == pure_phones, "Phone pillar parity mismatch"

        clear_cache()
        t0 = time.perf_counter()
        pure_addrs = [a.as_dict() for a in batch_standardize(addr_batch, max_workers=1)]
        t_addr_pure = time.perf_counter() - t0
        assert nat_addrs == pure_addrs, "Address pillar parity mismatch"

        t0 = time.perf_counter()
        pure_comps = [c.to_dict() for c in batch_standardize_companies(comp_batch)]
        t_comp_pure = time.perf_counter() - t0
        assert nat_comps == pure_comps, "Company pillar parity mismatch"

        t0 = time.perf_counter()
        pure_persons = [p.to_dict() for p in batch_standardize_persons(person_batch)]
        t_person_pure = time.perf_counter() - t0
        assert nat_persons == pure_persons, "Person pillar parity mismatch"

        t0 = time.perf_counter()
        pure_webs = [w.to_dict() for w in batch_standardize_urls(web_batch)]
        t_web_pure = time.perf_counter() - t0
        assert nat_webs == pure_webs, "Web pillar parity mismatch"

        clear_cache()
        t0 = time.perf_counter()
        pure_contacts = [c.to_dict() for c in batch_standardize_contacts(contact_batch)]
        t_contact_pure = time.perf_counter() - t0
        assert nat_contacts == pure_contacts, "Joint Contact pillar parity mismatch"
    finally:
        _set_pure_mode(False, saved_nd_mod, saved_addr_flag)

    for name, count, t_nat, t_pure in [
        ("phone", len(phone_batch), t_phone_nat, t_phone_pure),
        ("address", len(addr_batch), t_addr_nat, t_addr_pure),
        ("company", len(comp_batch), t_comp_nat, t_comp_pure),
        ("person", len(person_batch), t_person_nat, t_person_pure),
        ("web", len(web_batch), t_web_nat, t_web_pure),
        ("contact", len(contact_batch), t_contact_nat, t_contact_pure),
    ]:
        pillars_report[name] = {
            "records": count,
            "native_records_per_sec": round(count / max(t_nat, 1e-9), 1),
            "pure_python_records_per_sec": round(count / max(t_pure, 1e-9), 1),
            "speedup_ratio": round(t_pure / max(t_nat, 1e-9), 2),
            "parity_verified": True,
        }

    latencies_sorted = sorted(latencies_us)
    warm_sorted = sorted(warm_latencies_us)

    return {
        "engine_info": get_engine_info(),
        "cold_cache_latency_us": {
            "p50": round(statistics.median(latencies_sorted), 2),
            "p95": round(latencies_sorted[int(len(latencies_sorted) * 0.95)], 2),
            "mean": round(statistics.mean(latencies_sorted), 2),
        },
        "warm_cache_latency_us": {
            "p50": round(statistics.median(warm_sorted), 2),
            "p95": round(warm_sorted[int(len(warm_sorted) * 0.95)], 2),
            "mean": round(statistics.mean(warm_sorted), 2),
        },
        "batch_10k_e164": {
            "elapsed_sec": round(elapsed_batch, 4),
            "records_per_sec": round(throughput_per_sec, 1),
        },
        "pillars": pillars_report,
    }


if __name__ == "__main__":
    report = run_benchmarks()
    print(json.dumps(report, indent=2))
