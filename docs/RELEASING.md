# Releasing

Releases are driven by `.github/workflows/release.yml`, which runs when a tag matching `vX.Y.Z` (digits only, for
example `v3.3.1`; pre-release suffixes do not match) is pushed. This page describes what the workflow does, the
account setup it expects (which cannot be done from the repository), and the per-release checklist.

## Workflow overview

Jobs run in this order; each job needs the one before it, so a failure stops everything after it:

| Job | What it does | Credentials |
| :--- | :--- | :--- |
| `verify` | Checks out the full history, requires the tagged commit to be an ancestor of `origin/main`, and runs `python scripts/check_versions.py <tag>` | none |
| `ci` | Calls the full `.github/workflows/ci.yml` on the tag (see below) | none |
| `build` | Builds the Python sdist and wheel (`python -m build`, then `twine check`); in `sdks/typescript` runs `npm ci`, `npm test` and `npm pack`; runs `dotnet pack sdks/dotnet/AddressStandardizer.Client.csproj -c Release`; uploads everything as the `release-artifacts` artifact | none |
| `attest` | Creates signed build provenance attestations (`actions/attest-build-provenance`) for every file in `dist/python`, `dist/npm`, `dist/nuget` and `dist/sbom`; runs before any publish, so a failure blocks the release | `id-token: write`, `attestations: write` (this job only) |
| `pypi` | Publishes `dist/python/` with `pypa/gh-action-pypi-publish` | `id-token: write` (trusted publishing); environment `release` |
| `npm` | Runs `npm publish --access public --provenance dist/npm/*.tgz` | secret `NPM_TOKEN`, `id-token: write` (provenance); environment `release` |
| `nuget` | Runs `dotnet nuget push "dist/nuget/*.nupkg"` to `https://api.nuget.org/v3/index.json` | secret `NUGET_API_KEY`; environment `release` |
| `github-release` | After all three registries succeeded: extracts the `## [X.Y.Z]` section of `CHANGELOG.md` as release notes and runs `gh release create` with the Python, npm and NuGet artifacts and the CycloneDX SBOM attached | `contents: write` (this job only) |

`build` also generates a CycloneDX SBOM for the Python package (`dist/sbom/address-standardizer-python.cdx.json`, from
the built wheel installed with its `server` extra into a clean venv, using `cyclonedx-bom`).

Publishing is sequential: PyPI, then npm, then NuGet. The publish jobs upload the exact files produced by `build`
(downloaded from the `release-artifacts` artifact) rather than rebuilding them. Third-party actions are pinned to commit
SHAs; refresh them deliberately when upgrading.

### Checks that gate a release

- The tagged commit must be reachable from `main`.
- `scripts/check_versions.py` must find the same version in `pyproject.toml`, `sdks/typescript/package.json`,
  `sdks/dotnet/AddressStandardizer.Client.csproj` (`<Version>`), `address_standardizer/__init__.py` (`__version__`, when
  present) and the tag. The Go SDK is not part of this check.
- `CHANGELOG.md` must contain a non-empty `## [X.Y.Z]` section for the tagged version (`check_versions.py` fails
  otherwise, in the `verify` job, before any CI or build time is spent). Rename `## [Unreleased]` to
  `## [X.Y.Z] - YYYY-MM-DD` and add a fresh empty `[Unreleased]` section in the version-bump commit.
- `ci.yml` must pass on the tag. It contains these jobs:
  - `python`: `ruff check .`, `pytest -m "not perf"` with coverage, then `pytest -m perf` (throughput/memory SLA tests,
    with `ADDRESS_STANDARDIZER_SLA_SCALE=0.6`), on Python 3.11 and 3.13, on Ubuntu and Windows.
  - `rust`: `cargo test --locked` (Rust 1.85.0), builds the native extension with maturin and runs the native/pure
    parity and acceleration tests.
  - `sdks`: `tests/test_sdk_contract.py` (SDK model fields against the server's OpenAPI schema), then starts a live
    server and runs the TypeScript suite (`npm ci`, `npm test`; Node 20), the Go checks (`gofmt -l`, `go vet ./...`,
    `go test ./...`; Go 1.21) and `dotnet test sdks/dotnet/tests/AddressStandardizer.Client.Tests -c Release` (.NET
    8.0.x), all with `ADDRESS_STANDARDIZER_URL=http://127.0.0.1:8000` so the live-server integration tests run.
  - `docker`: builds the image and smoke-tests it (runs as non-root, native core active, `/health` and
    `/v1/standardize` respond).
- In `build`, the npm package is tested again (`npm test`) before it is packed. The NuGet package is packed but no
  .NET tests run in that job; the .NET tests run in `ci`.

## One-time setup (needs an account owner)

The workflow expects these to exist; the repository cannot create them.

| Target | What the workflow needs | Used by |
| :--- | :--- | :--- |
| **GitHub** | An environment named `release` (add required reviewers to gate publishing; restrict deployment to tags matching `v*`) | `pypi`, `npm`, `nuget` |
| **GitHub** | Settings, Actions, General: workflow permissions can stay "read" (jobs request what they need). Attestations need a public repository (or GitHub Enterprise Cloud for private ones); on a private repo the `attest` job fails and blocks the release | `attest`, `github-release` |
| **PyPI** | Trusted publishing configured for this repository, workflow `release.yml` and environment `release`; no token is read by the workflow | `pypi` |
| **npm** | A token stored as the repository/environment secret `NPM_TOKEN` with permission to publish `@address-standardizer/client` (the package `name` in `sdks/typescript/package.json`) | `npm` |
| **NuGet** | An API key stored as the secret `NUGET_API_KEY` with permission to push package id `AddressStandardizer.Client` | `nuget` |

### Owner checklist (accounts and settings)

None of this can be done from the repository; do it once before the first tag.

1. **PyPI**: create the project `address-standardizer` (or use a "pending publisher" before the first upload) and add a
   trusted publisher: owner `Jacob-white`, repository `Address-Standardizer`, workflow `release.yml`, environment
   `release`.
2. **npm**: create/claim the `@address-standardizer` scope (organization) and generate an automation (or granular,
   publish-scoped) token; store it as the secret `NPM_TOKEN` (environment `release` is best).
3. **NuGet**: reserve the package ID `AddressStandardizer.Client` (or choose another, see below), create an API key
   scoped to push that ID, and store it as the secret `NUGET_API_KEY` (environment `release`).
4. **GitHub environment `release`**: Settings, Environments, New environment; add required reviewers (not the person
   who pushes the tag, if you have more than one maintainer) and restrict deployment branches/tags.
5. **Tag protection**: add a tag ruleset for `v*` (restrict creation and block deletion/force-update).
6. **Security features**: Settings, Code security: enable Dependabot alerts and security updates (version updates are
   configured in `.github/dependabot.yml`), private vulnerability reporting (security advisories), secret scanning with
   push protection, and code scanning (CodeQL default setup).
7. **GitHub Pages for docs**: the `docs` workflow only builds the site on pull requests. To publish, either run
   `mkdocs gh-deploy --force` from a checkout with `pip install -e ".[docs,server]"`, or add a deploy job and set
   Settings, Pages, Source to "GitHub Actions". The configured `site_url` in `mkdocs.yml` assumes
   `https://jacob-white.github.io/Address-Standardizer/`; change it if you use another host.
8. **Go**: no secrets; the module is served from the git tag `sdks/go/v1.Y.Z`.

Verify a published artifact with `gh attestation verify <file> --repo Jacob-white/Address-Standardizer`.

The `Dependency audit` workflow (`.github/workflows/audit.yml`) runs weekly and on demand (`pip-audit`, `npm audit`,
`cargo audit`, NuGet vulnerability listing) and fails visibly on findings; it opens no issue. Watch the Actions tab or
subscribe to failed-workflow notifications.

If a package name is unavailable on its registry, change `name` in `sdks/typescript/package.json` or `<PackageId>` in
`sdks/dotnet/AddressStandardizer.Client.csproj`, and update the install commands in `sdks/README.md` and the SDK READMEs.
The PyPI project name comes from `pyproject.toml`.

## Go SDK

`release.yml` has no Go job and nothing in the workflow publishes the Go module; it is not covered by
`check_versions.py`. The workflow's header comment and `scripts/check_versions.py` state that the Go SDK is released by
pushing a `sdks/go/vX.Y.Z` tag (the module lives in the `sdks/go` subdirectory, and `sdks/README.md` explains why it
stays on `v1`). The `vX.Y.Z` tag filter does not match such tags, so pushing one does not start `release.yml`; the `ci`
workflow's Go job is the only automated check, and it runs on pushes to `main` and on pull requests. Make sure it passed
on the commit you tag. Consumers then run `go get github.com/Jacob-white/Address-Standardizer/sdks/go`, per
`sdks/go/go.mod`.

## Per-release checklist

1. Bump the version in `pyproject.toml`, `address_standardizer/__init__.py`, `sdks/typescript/package.json` and
   `sdks/dotnet/AddressStandardizer.Client.csproj`; turn the `[Unreleased]` section of `CHANGELOG.md` into
   `[X.Y.Z] - date` (choose the number by [VERSIONING.md](VERSIONING.md)); run `python scripts/check_versions.py vX.Y.Z`
   (the tag argument adds the tag and the CHANGELOG check to the comparison).
2. Merge to `main` and wait for CI to pass.
3. Tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`. Approve the `release` environment when prompted; each of
   the `pypi`, `npm` and `nuget` jobs waits on it.
4. For a Go release, push `sdks/go/v1.Y.Z` separately.

If a publish job fails partway, the earlier registries already have the release (publishing is sequential and not
transactional). Registries typically do not allow re-uploading the same version, so fix forward with a new version.
