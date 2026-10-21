"""Throughput benchmark for Phone Standardizer across mixed multinational records."""

from __future__ import annotations

import time

from phone_standardizer import standardize_phone

SAMPLE_RECORDS: list[tuple[str, str | None]] = [
    ("+1 (415) 555-2671 ext. 104", None),
    ("1-800-FLOWERS", "US"),
    ("+44 (0) 20 7946 0912", None),
    ("030 12345678", "DE"),
    ("+52 1 55 1234 5678", None),
    ("(787) 555-0244", None),
    ("＋８１ ３-１２３４-５６７８", None),
    ("0412 345 678", "AU"),
]


def run_benchmark(iterations: int = 20000) -> float:
    """Run throughput benchmark and return records/sec."""
    start = time.perf_counter()
    total = 0
    for _ in range(iterations // len(SAMPLE_RECORDS)):
        for phone, country in SAMPLE_RECORDS:
            standardize_phone(phone, country=country)
            total += 1
    elapsed = max(1e-9, time.perf_counter() - start)
    rate = total / elapsed
    print(f"Processed {total:,} records in {elapsed:.3f}s -> {rate:,.0f} records/sec")
    return rate


if __name__ == "__main__":
    run_benchmark()
