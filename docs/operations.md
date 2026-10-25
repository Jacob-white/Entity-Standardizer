# Operations & Deployment Guide 🚀

Entity Standardizer provides the unified FastAPI HTTP microservice (`entity_standardizer.server:app`), started via:

```bash
uvicorn entity_standardizer.server:app --host 0.0.0.0 --port 8000
```

It exposes **20 HTTP routes** across:
- **Liveness & Readiness Probes**: `GET /health`, `GET /ready`
- **Joint 6-Pillar Contact Standardization & Comparison**: `POST /v1/contact`, `POST /v1/contact/compare`
- **Organization / Company**: `POST /v1/company`, `POST /v1/company/compare`
- **Person & Job Title**: `POST /v1/person`, `POST /v1/person/compare`, `POST /v1/job-title`
- **Email, Website URL & Social**: `POST /v1/email`, `POST /v1/url`, `POST /v1/social`
- **Physical Address**: `POST /v1/address`
- **Telephone**: `POST /v1/standardize`, `POST /v1/explain`, `POST /v1/compare`, `POST /v1/deduplicate`, `POST /v1/batch`, `GET /v1/countries`, `GET /v1/countries/{identifier}`

---

## 1. Environment Variables

All operational features are **opt-in** through environment variables. With none of them set, the service runs with zero-configuration defaults suitable for local development and private VPC deployment. Legacy `ADDRESS_STANDARDIZER_*` environment variables are also recognized as backward-compatible fallbacks for the address subsystem.

| Variable | Meaning | Default |
| :--- | :--- | :--- |
| `ENTITY_STANDARDIZER_API_KEYS` | Comma-separated list of valid API keys required on `/v1/*` routes via `X-API-Key` or `Authorization: Bearer <key>`. | unset (auth disabled) |
| `ENTITY_STANDARDIZER_FORCE_PURE` | When set to `1`, `true`, `yes`, or `on`, forces the pure-Python engine even if `_entity_standardizer_rs` is compiled. | unset (auto-detects Rust PyO3) |
| `ENTITY_STANDARDIZER_CACHE_URL` | Optional Redis connection URL (`redis://host:6379/0` or `rediss://...`) for shared L2 address result caching across workers. | unset (in-process LRU + SQLite L2) |
| `ENTITY_STANDARDIZER_CACHE_MAX_SIZE` | Maximum entries in the in-process L1 LRU address cache per worker process. | `50000` |
| `ENTITY_STANDARDIZER_CACHE_DB` | File path for persistent SQLite L2 address cache (or `:memory:`). | `:memory:` |
| `ENTITY_STANDARDIZER_AUDIT_ENABLED` | Set to `1` to automatically record low-confidence (`MANUAL_REVIEW`) address standardizations into the stewardship ledger. | `0` (off unless ledger initialized) |
| `ENTITY_STANDARDIZER_AUDIT_DB` | SQLite database path for the address stewardship audit ledger. | `:memory:` |
| `ENTITY_STANDARDIZER_AUDIT_MAX_ROWS` | Maximum rows retained in an in-memory audit ledger (`0` disables pruning). | `10000` |
| `ENTITY_STANDARDIZER_ALLOW_LOCALITY` | Set to `1` to accept city/state/postal locality-only inputs globally in `standardize_address`. | `0` (`True` on `POST /v1/address`) |
| `ENTITY_STANDARDIZER_CORRECT_STATE_FROM_ZIP` | Set to `1` to replace mismatched US state codes with the authoritative state for the 5-digit ZIP code. | `0` (reports mismatch without overwriting) |

---

## 2. Health & Readiness Probes

- **`GET /health` (Liveness)**: Always returns `200 OK` with `{"status": "ok", "version": "2.1.0"}` while the process is alive.
- **`GET /ready` (Readiness)**: Returns `200 OK` with `{"status": "ready", "version": "2.1.0", "native_available": true|false}`, reporting whether the compiled Rust PyO3 native extension (`_entity_standardizer_rs`) is active.

Both `/health` and `/ready` remain open without authentication even when `ENTITY_STANDARDIZER_API_KEYS` is set, allowing Kubernetes and container orchestrators to probe the service directly.

---

## 3. API Key Authentication

Set `ENTITY_STANDARDIZER_API_KEYS` to a comma-separated list of valid secret keys to require authentication on all `/v1/*` routes:

```bash
export ENTITY_STANDARDIZER_API_KEYS="prod-key-1,prod-key-2"

# Authenticate via X-API-Key header:
curl -H "X-API-Key: prod-key-1" \
     -H "Content-Type: application/json" \
     -d '{"phone": "(415) 555-2671", "country": "US"}' \
     http://127.0.0.1:8000/v1/standardize

# Or via Authorization: Bearer <key> header:
curl -H "Authorization: Bearer prod-key-2" \
     -H "Content-Type: application/json" \
     -d '{"phone": "(415) 555-2671", "country": "US"}' \
     http://127.0.0.1:8000/v1/standardize
```

Requests to `/v1/*` with a missing or invalid key receive `401 Unauthorized` (`{"detail": "Invalid or missing API key."}`).

---

## 4. Docker & Compose Deployment

```yaml
services:
  entity-standardizer:
    build: .
    read_only: true
    tmpfs: [/tmp]
    ports: ["127.0.0.1:8000:8000"]
    environment:
      ENTITY_STANDARDIZER_API_KEYS: "${ENTITY_STANDARDIZER_API_KEYS:-}"
      ENTITY_STANDARDIZER_CACHE_MAX_SIZE: "50000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 15s
      timeout: 3s
      retries: 3
```

---

## 5. Reverse Proxy, Sizing & Scaling

- **Process scaling**: Standardization is CPU-bound and zero-network. Run `uvicorn entity_standardizer.server:app --workers N` (typically 1 worker per vCPU core) or scale container replicas horizontally.
- **Lazy initialization**: Both the multi-tier SQLite cache and the stewardship audit ledger initialize lazily on first use, and SQLite connections automatically re-initialize across `os.fork()` boundaries when running under multi-worker Gunicorn/Uvicorn pre-fork servers.
- **Gateway termination**: Terminate TLS, enforce global rate limits, and configure request size/timeout bounds at your edge reverse proxy (Nginx, Envoy, AWS ALB, or Cloudflare).
