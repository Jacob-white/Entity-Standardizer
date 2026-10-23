# Performance, caching and scaling

This page records what was measured, what was changed because of it, how the result cache behaves across processes
and nodes, and how to load-test a running service. Every number below was measured on one Windows 11 developer
workstation (Python 3.13.5, pure-Python core, no native module) while other processes were running, so absolute values
move by tens of percent from run to run. Compare ratios, not digits, and re-measure on your hardware.

## Profile of the mixed real-world path

Reproduce with `python benchmarks/run_profile.py` (cProfile over the first 1,000 records of the domestic golden set,
cold result cache). Profiling roughly doubles absolute times; the proportions are what matter.

Findings, before any change:

| Cost | Share of `standardize_address` time | Cause |
| :--- | :--- | :--- |
| `lookup_corporate_registry` (4 calls per record) | ~22% cumulative | Compiled a regex per registry entry per call (`re.escape` + `re.compile` lookups, ~50,000 `re._compile` calls per 1,000 records) and re-ran the same lookup for the hub flag, the risk score and delivery intelligence. |
| `sqlite3` `execute` | ~7-9% | Offline rooftop index lookups (3 queries per unseen address) and the L2 cache write per computed result. |
| `damerau_levenshtein_distance` | ~7% | Fuzzy city/street healing (pure Python DP). |
| `re.sub` / `re.search` (about 40 call sites) | ~8-14% combined | Small normalisation patterns spread across modules; no single site above ~1%. |
| `usaddress` CRF tagger | ~5% | Only for inputs the fast path cannot handle. |
| Everything else | flat | No other function above ~4%. |

### Changes made (behaviour preserving)

1. `registry._contains_token_run` rejects non-matching entries with a plain substring test and uses a bounded
   `lru_cache` of compiled patterns for the rest. The pattern semantics are unchanged (tested).
2. `registry.lookup_corporate_registry` memoizes results in a bounded dict (4,096 entries, cleared when full). The memo
   is dropped automatically when the `CURATED_CORPORATE_REGISTRY` list object is replaced or changes length. Returned
   entries are the same objects as before.

Tried and **reverted**: restructuring `make_cache_key` to skip escaping for clean fields. Measured 2.0 us vs 2.1 us per
call, which is noise, so the original code stays.

### Measured effect

In-process A/B (`registry` toggled between the old and the new code inside one process, 11 interleaved rounds over the
1,000 mixed domestic records with a cold result cache, CPU time): median **1,220 rec/s before, 1,620 rec/s after
(+33%)**; rounds before: 1,049-1,391, after: 1,455-1,829. (Absolute values are lower than the table below because the
cache is cleared every round and the machine was loaded; the ratio is the result.)

`benchmarks/run_benchmarks.py --dataset domestic` (single pass, includes the result cache and warm-up), median of runs:

| Row | Before (3 runs) | After (5 runs) |
| :--- | :--- | :--- |
| Clean structured | 71,900 rec/s (60,600-72,500) | 65,100 rec/s (50,400-74,400) |
| Mixed golden batch | 2,205 rec/s (1,992-2,289) | 2,096 rec/s (1,606-2,275) |

These end-to-end runs were taken at different times while other agents were running test suites on the same machine,
and they do **not** show the improvement; the spread between runs (about 35%) is larger than the effect. Do not read
them as a regression or as proof of a gain: the interleaved A/B above is the controlled measurement. The clean
structured row is dominated by result-cache hits (about 15-30 us per call) and was not touched.

## Native (Rust) acceleration: not worth it for this hot path

The task was to move one pure function into the Rust module only if that gave at least 15% end-to-end on the mixed
benchmark. The profile rules every candidate out:

* The largest pure function candidate, `damerau_levenshtein_distance`, is ~7% of the total. Even if Rust made it
  free, the best possible gain is under 7%, and the call crosses the Python/Rust boundary with short strings
  (about 1,250 calls per 1,000 records), which costs part of the saving.
* Soundex is already native when the extension is installed and is below 1%.
* The remaining time is spread thinly over ~40 regex call sites, dictionary lookups, SQLite and dataclass
  construction. There is no single well-defined function to port.

So the Rust module is unchanged. A real native speed-up would require porting the whole parse/normalise pipeline, which
is out of scope (and is what earlier versions did, producing keys that depended on whether the extension was installed).

## The result cache: tiers, backends, and what is shared

`standardize_address` consults a result cache keyed by the normalised input fields and options (and the tenant
namespace when tenant isolation is on). The cache has two tiers:

| Tier | Where | Shared across processes? |
| :--- | :--- | :--- |
| L1 | In-process LRU (default 50,000 entries) | **No.** Each process (each uvicorn worker, each replica) has its own. |
| L2 | Pluggable backend, default embedded SQLite (`:memory:` unless `l2_db_path` is set) | SQLite `:memory:` **no**; SQLite file **yes between processes on the same host** (WAL mode, same file); Redis **yes between all processes and nodes that use the same Redis and prefix**. |

A lookup checks L1, then L2; an L2 hit is promoted into the caller's L1. A computed result is written to both.

### Backends

* **Default**: L1 LRU + SQLite L2. Unchanged behaviour.
* **Redis** (optional): `pip install "address-standardizer[redis]"` (`redis>=5`). Select it either way:

```python
from address_standardizer.cache import configure_cache
from address_standardizer.cache_backends import RedisCacheBackend

configure_cache(backend="redis://cache.internal:6379/0")           # URL form
configure_cache(backend=RedisCacheBackend("rediss://cache:6380/1",  # explicit form
                                          prefix="addr:prod:", ttl_seconds=3600))
```

or set `ADDRESS_STANDARDIZER_CACHE_URL=redis://cache.internal:6379/0` before the process starts (the HTTP service picks
it up too). An explicit `backend=` wins over the variable; an unsupported URL is logged and the SQLite L2 is kept.

Redis backend behaviour:

* **TTL**: every entry expires after `ttl_seconds` (default 86,400; `None`/0 stores without expiry).
* **Namespace**: keys are stored as `prefix + key` (default prefix `address_standardizer:v1:`); tenant isolation
  prefixes the key itself with `@<tenant>|`, so tenants stay separate in Redis as well. `clear()` deletes only keys under
  the prefix (never `FLUSHDB`). Change the prefix when you change the library version in a way that alters results, or
  when several environments share one Redis.
* **Failure isolation**: a Redis error (down, timeout, auth, missing `redis` package, corrupt payload) is logged once,
  counted in `stats()` (`errors`, `skipped_while_down`, `degraded`), and treated as a cache miss or a skipped write. After
  a failure the backend does not touch Redis again for `retry_after` seconds (default 30), so an outage costs at most one
  slow call (`socket_timeout`, default 0.25 s) per window rather than one per request. Standardization never raises
  because of the cache.
* **Values** are the JSON payload of the result (the same representation the SQLite L2 stores), so they are readable by
  any process running a compatible library version and contain address data: treat the Redis instance as sensitive
  (network isolation, auth, TLS via `rediss://`).

### Multi-process and multi-node semantics

* **Per process, always**: the L1 LRU, its hit/miss counters, the rate limiter, quota and metrics. Two workers can both
  compute the same address once each before either L2 write is visible; with Redis the second worker then gets a hit.
* **Shared with Redis**: computed results. A result written by node A is served to node B after B's L1 misses.
* **Not coordinated**: there is no cross-process invalidation. `delete`/`clear` act on L2 immediately, but another
  process's L1 may keep serving its copy until it evicts it (L1 has no TTL). Restart workers, or call `clear_cache()`
  in each, when you need every process to forget. There is also no single-flight locking: concurrent misses for the same
  key compute independently and write the same value.
* **`get_cache_stats()`** reports this process's L1 and the backend's own counters (for Redis: this process's hits,
  misses and errors against Redis, not a cluster-wide total; `size` is `None`).
* Use one Redis per environment, or distinct prefixes, so a staging deploy cannot read production's results.

## Load-testing a running service

`scripts/load_test.py` is standard-library only: it drives `/v1/standardize` (one address per request) or `/v1/batch`
(`--batch-size` addresses per request) from concurrent threads and prints throughput and p50/p95/p99 latency measured by
the client.

```bash
address-standardizer serve --workers 2 &
python scripts/load_test.py --concurrency 16 --requests 5000
python scripts/load_test.py --endpoint batch --batch-size 100 --duration 20 --unique --json
python scripts/load_test.py --input my_addresses.jsonl --header "X-API-Key: <key>"
```

* `--unique` makes every address distinct so the run measures computation rather than result-cache hits; without it the
  built-in pool repeats and a warm cache will report very high numbers.
* `--input FILE` is JSON lines, one request object per line (`street1`, `city`, ... or `address`).
* The exit status is 1 when any request failed (non-2xx, timeout or connection error), so it can gate a pipeline.
* Latency includes the client thread, HTTP and JSON; run the client on a different machine, or at least pin it away from
  the server cores, before comparing numbers.

Smoke run on the same workstation against one `address-standardizer serve` process (default settings, client on the same
machine, so the two compete for CPU): 300 unique single-address requests from 4 threads gave 154 req/s with p50 22 ms,
p95 40 ms, p99 217 ms and no failures; 20 batch requests of 50 unique addresses from 2 threads gave about 900
addresses/s. These show the tool works; they are not a capacity claim.

## Transliteration (optional)

`address_standardizer.transliterate.transliterate(text)` produces a Latin rendering for display and matching. With the
optional `anyascii` package (`pip install "address-standardizer[translit]"`, ISC license) it covers every script
`anyascii` supports. Without it, a built-in fallback handles **Cyrillic and Greek** using the same letter tables as the
ASCII matching keys; it is a plain lossy romanisation (not BGN/PCGN or ISO 9; hard/soft signs and Greek accents are
dropped). Text in any other script raises `TransliterationUnavailable` (a `NotImplementedError`) with
`errors="strict"`, or is left unchanged with `errors="passthrough"`; no placeholder characters are ever substituted.
`std_to_latin(std)` returns `std.as_dict()` with `street1`, `street2`, `city` and `state` transliterated (passthrough by
default), and `address-standardizer parse --latin ...` prints those fields in Latin script with the originals kept under
`native`.
