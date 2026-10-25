# Releasing (`Entity Standardizer`)

Releases follow [Semantic Versioning 2.0.0](VERSIONING.md) and are gated by the repository's 6 GitHub Actions CI jobs (`.github/workflows/ci.yml`) and SDK/OpenAPI contract suite (`tests/test_sdk_contract.py`).

## Version Synchronization Contract

The following 8 locations must always share the exact same release version (e.g., `2.1.0`), enforced automatically by `tests/test_sdk_contract.py::test_version_and_openapi_docs_sync`:
1. `pyproject.toml` (`[project].version`)
2. `Cargo.toml` (`[package].version`)
3. `phone_standardizer/__init__.py` (`__version__`)
4. `phone_standardizer/server.py` (`FastAPI(version=...)` and `/health` response)
5. `phone_standardizer/mcp/server.py` (`serverInfo.version` in `initialize` response)
6. `sdks/typescript/package.json` (`version` for `@phone-standardizer/client`)
7. `sdks/dotnet/PhoneStandardizer.Client.csproj` (`<Version>` for `PhoneStandardizer.Client`)
8. `docs/openapi.json` (`info.version`)

---

## CI Quality Gates Required Before Tagging

Every release commit on `main` must pass all 6 CI jobs in `.github/workflows/ci.yml`:
- **Python Test & Coverage Matrix (`python` — 4 jobs across `ubuntu-latest` & `windows-latest` on Python `3.11` & `3.13`)**:
  - `ruff check .` (zero lint errors)
  - `pytest --cov --cov-report=term-missing` (**100% statement and branch coverage** enforced via `fail_under = 100` in `pyproject.toml`)
- **Native Rust PyO3 Extension (`rust` — 1 job)**:
  - `cargo test --locked`
  - `cargo build --release --locked` followed by `pytest` verifying 100% Python/Rust parity
- **Multi-Platform Client SDKs (`sdks` — 1 job)**:
  - TypeScript/React SDK (`cd sdks/typescript && npm test`)
  - Go SDK (`cd sdks/go && go vet ./... && go test -v ./...`)
  - .NET 8 SDK (`dotnet build sdks/dotnet/PhoneStandardizer.Client.csproj -c Release`)

---

## Per-Release Checklist

1. **Synchronize Versions**:
   Update the version string across `pyproject.toml`, `Cargo.toml`, `phone_standardizer/__init__.py`, `phone_standardizer/server.py`, `phone_standardizer/mcp/server.py`, `sdks/typescript/package.json`, and `sdks/dotnet/PhoneStandardizer.Client.csproj`.
2. **Regenerate OpenAPI Schema**:
   ```bash
   python -c "import json; from phone_standardizer.server import app; open('docs/openapi.json', 'w').write(json.dumps(app.openapi(), indent=2) + '
')"
   ```
3. **Update `CHANGELOG.md`**:
   Document all added features, bug fixes, SDK updates, and documentation improvements under `## [X.Y.Z] - YYYY-MM-DD`.
4. **Run Full Verification Suite Locally**:
   ```bash
   ruff check .
   pytest --cov --cov-report=term-missing
   cargo test --locked
   (cd sdks/typescript && npm test)
   (cd sdks/go && go vet ./... && go test -v ./...)
   dotnet build sdks/dotnet/PhoneStandardizer.Client.csproj -c Release
   ```
5. **Merge & Tag**:
   Merge the release PR into `main`, wait for all 6 GitHub Actions checks to turn green, and tag `vX.Y.Z` (and `sdks/go/vX.Y.Z` for the Go module).
