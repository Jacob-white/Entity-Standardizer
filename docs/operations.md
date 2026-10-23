# Operations guide: running the HTTP service in production

This guide covers deploying the REST service (`address_standardizer.server:app`, started by `address-standardizer serve`
or `uvicorn`). Every feature below is **opt-in through environment variables**: with none of them set, the server behaves
exactly as it does in local development (open, no limits, `*` CORS). Configuration is read **once, when the app is
created** (process start); restart to change it. Misconfigured security settings (a malformed key list, a bad rate
limit) stop the process at startup rather than silently running unprotected.

Contents: [Environment variables](#environment-variables) ·
[Authentication](#authentication) · [Rate limiting and quotas](#rate-limiting-and-quotas) ·
[Request IDs, logs, metrics, tracing](#observability) · [Health and readiness](#health-and-readiness) ·
[Tenant isolation](#tenant-isolation) · [Limits, timeouts, headers](#limits-timeouts-and-headers) ·
[Docker and compose](#docker-and-compose) · [Reverse proxy / gateway](#reverse-proxy-and-gateway) ·
[Sizing and scaling](#sizing-and-scaling) · [Security checklist](#security-checklist)

## Environment variables

Booleans accept `1/true/yes/on` and `0/false/no/off`. All names are prefixed `ADDRESS_STANDARDIZER_`.

| Variable | Meaning | Default |
| :--- | :--- | :--- |
| `API_KEYS` | Enables authentication. Comma- or newline-separated `name:key` entries (see [Authentication](#authentication)). | unset: auth off |
| `API_KEYS_FILE` | Path of a file with one `name:key` entry per line (`#` comments allowed). Combined with `API_KEYS` if both are set. | unset |
| `AUTH_OPEN_PATHS` | Comma-separated exact paths that need no key and are not rate limited. | `/health,/ready` |
| `RATE_LIMIT` | Token-bucket rate per key (or per client IP when unauthenticated): `N/second`, `N/minute`, `N/hour` or `N/day`. | unset: no limit |
| `RATE_LIMIT_BURST` | Bucket capacity (requests allowed back-to-back). | `N` of `RATE_LIMIT` |
| `RATE_LIMIT_MAX_BUCKETS` | Cap on tracked identities for the limiter and quota tables (memory bound). | `10000` |
| `DAILY_QUOTA` | Maximum requests per key (or IP) per UTC day. | unset: no quota |
| `TRUST_FORWARDED_FOR` | Identify unauthenticated clients by the last `X-Forwarded-For` entry instead of the socket peer. Enable only behind a proxy you control. | off |
| `TENANT_ISOLATION` | Per-key cache namespace and audit ledger (needs `API_KEYS`). | off |
| `TENANT_AUDIT_DIR` | Directory for per-tenant SQLite ledgers (`<key name>.db`). Without it tenant ledgers are in memory. | unset |
| `REQUEST_TIMEOUT_SECONDS` | Cooperative time budget for `/v1/batch`; see [timeouts](#limits-timeouts-and-headers). `0` or unset disables. | unset |
| `ACCESS_LOG` | Emit one JSON line per request on logger `address_standardizer.access`. | on |
| `OTEL` | Create OpenTelemetry spans when the `opentelemetry` API is importable. `0` disables. | on (no-op if not installed) |
| `SECURITY_HEADERS` | Add `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` and `Cache-Control: no-store` on API responses. | on |
| `MAX_BATCH`, `MAX_BODY_BYTES` | Existing request size limits (HTTP 413). | `10000`, 16 MiB |
| `CORS_ORIGINS` | Existing CORS allow-list. | `*` without credentials |
| `DISABLE_DOCS` | Existing: turn off `/docs`, `/redoc`, `/openapi.json`. | docs on |
| `CACHE_MAX_SIZE` | Existing cache size (the Docker image sets 50 000). | see image |

## Authentication

Set `ADDRESS_STANDARDIZER_API_KEYS` (or `..._API_KEYS_FILE`) and every route except the open paths requires a key:

```bash
export ADDRESS_STANDARDIZER_API_KEYS="billing:$(openssl rand -hex 32),partner-x:$(openssl rand -hex 32)"
curl -H "X-API-Key: <key>" https://host/v1/standardize -d '{"address": "..."}'
curl -H "Authorization: Bearer <key>" https://host/v1/standardize -d '...'   # equivalent
```

- **Entries** are `name:key`. `name` is `[A-Za-z0-9_.-]`, up to 64 characters, and becomes the *key name* attached to
  every request: it appears in access logs, the `key_name` span attribute, per-key metrics and tenant namespaces. Keys
  must be at least 16 characters and contain no commas or whitespace.
- **Hashed storage.** Keys are held in memory only as SHA-256 digests and compared in constant time against every
  stored digest. You can avoid keeping plaintext on the server at all: `name:sha256:<64 hex>` is accepted
  (`printf %s "$KEY" | sha256sum`). Keys and digests are never logged or echoed; error messages cite the entry
  number only.
- **Rotation.** Entries may share a name: add the new key, move clients over, remove the old entry, restart.
- **Status codes.** `401` (with `WWW-Authenticate: Bearer`) when no credential is presented, `403` when a credential
  is presented but unknown or revoked. Error bodies are `{"detail": ..., "request_id": ...}`.
- **Open paths.** `/health` and `/ready` stay open so orchestrator probes work; change with `AUTH_OPEN_PATHS`.
  `/metrics` and the OpenAPI docs require a key when auth is on: give your scraper a key, or open `/metrics` only on a
  private network. Consider `DISABLE_DOCS=1` in production.
- Authentication runs inside the CORS layer, so browsers can read 401/403/429 responses.
- Not provided: key scopes/roles and brute-force lockout. Put failed-auth throttling (fail2ban, WAF) at the gateway.

## Rate limiting and quotas

`RATE_LIMIT=100/minute` with `RATE_LIMIT_BURST=20` gives each identity a 20-request bucket refilled at 100 per minute.
The identity is the **key name** when authenticated, else the **client IP**. Over the limit the service returns
`429` with `Retry-After` (whole seconds) and `X-RateLimit-Limit` / `X-RateLimit-Remaining` headers. A batch request
counts as one request regardless of size; bound batch cost with `MAX_BATCH`.

`DAILY_QUOTA=50000` additionally caps requests per identity per UTC day (`429`, `Retry-After` = seconds to midnight
UTC). The rate limit is checked first so rejected requests do not burn quota.

Memory is bounded: buckets idle long enough to have fully refilled are dropped, and the table never exceeds
`RATE_LIMIT_MAX_BUCKETS` entries (the least recently used identity is evicted and starts with a fresh bucket).

**The limiter is per process.** With `W` workers or `R` replicas the effective limit is up to `W x R` times the
configured value, and counters are lost on restart. For a global, exact limit enforce it at the gateway (nginx
`limit_req`, Envoy/Istio rate-limit service, Kong, API Gateway usage plans) and treat the in-process limiter as a
safety net, or pin each tenant to one worker with sticky routing. Daily quotas have the same caveat.

Behind a proxy all clients share the proxy's socket address; set `TRUST_FORWARDED_FOR=1` only when the proxy
overwrites/appends `X-Forwarded-For` (the **last** entry is used, since it is the one your proxy appended).

## Observability

**Request IDs.** Every response carries `X-Request-ID`. A client-supplied `X-Request-ID` (letters, digits, `.`, `_`,
`-`, up to 128 characters) is honoured; anything else is replaced by a generated one. HTTP error bodies include it
(`request_id`). Unhandled 500s raised by the server framework are plain-text and carry the header only.

**Access log.** One JSON object per request on logger `address_standardizer.access` at INFO:

```json
{"duration_ms":1.9,"key_name":"billing","method":"POST","n_addresses":1,"request_id":"3f2c...","route":"/v1/standardize","status":200,"ts":"2026-10-09T14:03:11.231+00:00"}
```

`route` is the route template (`unmatched` for 404s and for requests rejected before routing, such as 401/429), never
the raw path or query string. No address content and no credentials are ever logged. Python does not print INFO by
default; route the logger to stdout, for example with `uvicorn --log-config` or:

```python
import logging, sys
h = logging.StreamHandler(sys.stdout); h.setFormatter(logging.Formatter("%(message)s"))
logging.getLogger("address_standardizer.access").addHandler(h)
logging.getLogger("address_standardizer.access").setLevel(logging.INFO)
```

**Metrics** (`/metrics?format=prometheus`, plus the same data in the JSON form):

- existing: `address_standardizer_requests_total`, `..._addresses_processed_total`, `..._endpoint_requests_total{endpoint}`,
  `..._status_requests_total{code}`, `..._uptime_seconds`, `..._avg_latency_ms`
- new: `address_standardizer_request_duration_seconds` histogram (`_bucket{le}`, `_sum`, `_count`; buckets 1 ms to 10 s)
  and `address_standardizer_key_requests_total{key}` per key name.

Cardinality is bounded: at most 64 endpoint labels and 64 key labels; further values fold into `other`. Metrics are
per process; with several workers scrape each one or aggregate at the collector.

**Tracing (optional).** Install the extra: `pip install "address-standardizer[otel]"` (the OpenTelemetry API; add
`opentelemetry-sdk` and an exporter, or run with the `opentelemetry-instrument` launcher, to ship spans). When the API
is importable the service opens one span per request named `METHOD /route/template` with attributes
`http.request.method`, `http.route`, `http.response.status_code`, `address_standardizer.request_id` and (when
authenticated) `address_standardizer.key_name`. Without the SDK configured the API is a no-op. Set
`ADDRESS_STANDARDIZER_OTEL=0` to skip it entirely.

## Health and readiness

- `GET /health`: **liveness**. Always 200 while the process answers; includes version, engine capabilities and cache
  statistics. Use it for liveness probes and container health checks.
- `GET /ready`: **readiness**. Verifies that the cache, audit ledger and reference database are usable. Returns
  `200 {"status":"ready","checks":{...}}` or `503 {"status":"not_ready","checks":{"reference_db":"unavailable"}}`
  (names only; the cause is in the server log). Use it for load-balancer / Kubernetes readiness probes. Code that adds
  a data store can register a check with `address_standardizer.service.readiness.register_check(name, fn)`.

Neither endpoint requires a key or counts against rate limits (see `AUTH_OPEN_PATHS`).

## Tenant isolation

With `TENANT_ISOLATION=1` (requires `API_KEYS`), each key *name* becomes a tenant:

- **Cache**: result-cache keys get an `@<name>|` prefix, so tenants never read each other's cached results (this also
  protects against timing/probing of another tenant's data). The prefix is applied to both the in-process and the
  persistent cache tiers. Cost: identical addresses are computed once per tenant instead of once overall.
- **Audit ledger**: addresses routed to manual stewardship are recorded in a ledger per tenant instead of the shared
  one. In memory by default (bounded like the default ledger), or durable under `TENANT_AUDIT_DIR/<name>.db`.

Requests without a key (open paths, or auth off) use the shared cache and ledger. Keys that share a name share a
tenant. Isolation is logical, inside one process: it is not a substitute for separate deployments when tenants need
hard separation of compute or a different reference-data release.

## Limits, timeouts and headers

- **Size**: `MAX_BODY_BYTES` (413 as soon as the stream exceeds it) and `MAX_BATCH` (413). Also set the proxy's body
  limit a little above `MAX_BODY_BYTES`.
- **Batch time budget**: `REQUEST_TIMEOUT_SECONDS=30` is checked between items. The JSON array form answers
  `504 {"detail": "Batch processing exceeded the time limit"}`; the NDJSON forms (already streaming with status 200)
  end with a final line `{"error": "timeout", "index": N}` where `N` is the first item that was not processed. The
  budget is **cooperative**: a single item cannot be interrupted, and work already started in the worker thread
  finishes. Single `/v1/standardize` and autocomplete calls are sub-millisecond and have no budget; set the proxy
  timeout as the hard stop.
- **Headers** on every response: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`; and `Cache-Control: no-store` on `/v1/*`, `/metrics`, `/health`, `/ready`
  (existing values are never overridden). TLS-related headers (HSTS) belong on the TLS terminator.
- **CORS** is unchanged (`CORS_ORIGINS`).

## Docker and compose

The image runs as a non-root user with a read-only root filesystem in the provided compose file. Add the production
settings through the environment and mount the keys as a secret:

```yaml
services:
  address-standardizer:
    image: address-standardizer:latest
    read_only: true
    tmpfs: [/tmp]
    ports: ["127.0.0.1:8000:8000"]         # publish deliberately; terminate TLS in front
    environment:
      ADDRESS_STANDARDIZER_API_KEYS_FILE: /run/secrets/as_api_keys
      ADDRESS_STANDARDIZER_RATE_LIMIT: "300/minute"
      ADDRESS_STANDARDIZER_RATE_LIMIT_BURST: "50"
      ADDRESS_STANDARDIZER_DAILY_QUOTA: "200000"
      ADDRESS_STANDARDIZER_REQUEST_TIMEOUT_SECONDS: "30"
      ADDRESS_STANDARDIZER_DISABLE_DOCS: "1"
      ADDRESS_STANDARDIZER_TENANT_ISOLATION: "1"
      ADDRESS_STANDARDIZER_TENANT_AUDIT_DIR: /data/audit
    secrets: [as_api_keys]
    volumes: ["audit:/data/audit"]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/ready"]
secrets:
  as_api_keys:
    file: ./secrets/api_keys.txt          # lines of name:key (or name:sha256:<hex>)
volumes:
  audit:
```

Use `/ready` for orchestrator readiness and `/health` for liveness (the image's built-in healthcheck uses `/health`,
which stays open). With a read-only root filesystem, any directory the service writes to (`TENANT_AUDIT_DIR`, a
persistent cache path) must be a mounted volume.

## Reverse proxy and gateway

Terminate TLS, enforce global rate limits and body/time limits, and strip or overwrite client-supplied forwarding
headers at the edge. Example nginx fragment:

```nginx
limit_req_zone $binary_remote_addr zone=as:10m rate=50r/s;
server {
  listen 443 ssl;
  client_max_body_size 17m;               # slightly above MAX_BODY_BYTES
  proxy_read_timeout 60s;                 # hard stop above REQUEST_TIMEOUT_SECONDS
  add_header Strict-Transport-Security "max-age=63072000" always;
  location / {
    limit_req zone=as burst=100 nodelay;
    proxy_set_header X-Request-ID $request_id;            # propagate/generate correlation IDs
    proxy_set_header X-Forwarded-For $remote_addr;        # overwrite: never trust client-sent values
    proxy_buffering off;                                   # lets NDJSON responses stream
    proxy_pass http://127.0.0.1:8000;
  }
  location /metrics { allow 10.0.0.0/8; deny all; proxy_pass http://127.0.0.1:8000; }
}
```

Run uvicorn with `--proxy-headers --forwarded-allow-ips <proxy ip>` if you also want scheme/host awareness. If the
gateway authenticates users itself (mTLS, OIDC), you may leave `API_KEYS` off and bind the service to a private network
only; authentication in the service is defence in depth, not a replacement for network policy.

## Sizing and scaling

- Standardization is CPU-bound and runs in the worker threadpool, so one process uses roughly one core effectively
  (Python GIL; the optional Rust extension helps). Scale by **processes**: `uvicorn --workers N` or replicas, about one
  per core. Per-process state (cache, rate limiter, quota, metrics, tenant ledgers) is **not shared**; an optional Redis
  result-cache backend can be shared between workers and nodes (see [Performance and caching](performance.md)).
- Memory: the result cache is bounded by `CACHE_MAX_SIZE` entries per process; the limiter by `RATE_LIMIT_MAX_BUCKETS`;
  the in-memory audit ledger by `AUDIT_MAX_ROWS`; a batch holds up to `MAX_BODY_BYTES` plus its results in memory, so
  budget `workers x (cache + 3 x MAX_BODY_BYTES)` as a starting point and load-test with your address mix. The
  provided compose file caps the container at 2 CPUs / 2 GB.
- Cache hit rate drives latency: keep warm replicas, avoid frequent restarts, and prefer fewer larger workers over many
  tiny ones when the working set is large. Tenant isolation lowers hit rate across tenants.
- Use NDJSON streaming for large batches and keep individual requests well under `MAX_BATCH`; split bigger jobs
  client-side so one tenant cannot monopolize a worker.
- Per-process rate limits, quotas and metrics need an aggregating layer (gateway, Prometheus `sum by`) when you run more
  than one process.

## Security checklist

- [ ] TLS terminated in front; the service port is not published to the internet directly.
- [ ] `API_KEYS_FILE` (or sha256 entries) sourced from a secret store; keys 32+ random bytes (`openssl rand -hex 32`),
      one name per client, rotated on a schedule by adding the new key before removing the old.
- [ ] `RATE_LIMIT`, `DAILY_QUOTA`, `REQUEST_TIMEOUT_SECONDS`, `MAX_BATCH`, `MAX_BODY_BYTES` set deliberately; the same
      limits (and a global limiter) enforced at the gateway.
- [ ] `DISABLE_DOCS=1`; `/metrics` restricted to the monitoring network or given its own key.
- [ ] `CORS_ORIGINS` set to the real browser origins (or empty if there are none); no `*` with credentials.
- [ ] `TRUST_FORWARDED_FOR` on only when a trusted proxy sets `X-Forwarded-For`.
- [ ] Container runs non-root with a read-only filesystem, dropped capabilities, `no-new-privileges`, resource limits.
- [ ] Access logs shipped to your log platform and alerted on 401/403/429 spikes; request IDs propagated from the gateway.
- [ ] `/ready` wired to the load balancer; `/health` to the liveness probe.
- [ ] Tenant isolation enabled if API keys represent different customers; `TENANT_AUDIT_DIR` on a persistent volume.
- [ ] Dependencies and the base image scanned and updated (see SECURITY.md).
