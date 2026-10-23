# Versioning policy

The project follows [Semantic Versioning 2.0.0](https://semver.org/). The Python package, the npm package
(`@address-standardizer/client`) and the NuGet package (`AddressStandardizer.Client`) always share one version number;
`scripts/check_versions.py` enforces this at release time. The Go SDK is tagged separately (`sdks/go/v1.Y.Z`).
Every release has a section in [CHANGELOG.md](https://github.com/Jacob-white/Address-Standardizer/blob/main/CHANGELOG.md).

## What each version part means

| Part | Bumped when |
| :--- | :--- |
| MAJOR | A breaking change to the public contract (below) |
| MINOR | Backwards-compatible features, new optional fields, new opt-in flags, new reason codes |
| PATCH | Bug fixes that do not change the public contract |

## The public contract

These are covered by the policy:

- Python: names exported from `address_standardizer` and documented in the [API reference](api_reference.md), the CLI
  commands and flags, and the environment variables documented in `SECURITY.md` and `operations.md`.
- HTTP API: paths, methods, request fields, response fields and their types and nullability, HTTP status codes.
- SDKs: public types and functions of the TypeScript, .NET and Go clients.
- Machine-readable values: `failure_reason_codes`, routing tiers, precision names, DPV footnotes, error codes and
  error response shapes.
- Matching and cache **key formats** (`*_key` style fields, cache keys, audit identifiers). Persisted keys are part of
  customers' data, so changing how a key is derived is a breaking change.

Not covered: private modules and names starting with an underscore, the internals of the native extension, log text,
benchmark numbers, and the contents of the sample data.

## What counts as breaking

Breaking (requires a MAJOR bump, or for 0.x-style experiments a clear note):

- Removing or renaming a field, endpoint, flag, environment variable or exported name.
- Changing a field's type, or making a field that could be absent or null always required of the client, or the reverse
  (a non-null field becoming nullable is breaking for typed clients).
- Removing or renaming an error or reason code, or changing its meaning.
- Changing the derivation of any key so that the same input yields a different key.
- Raising the minimum supported Python version (see below) or dropping a supported platform.
- Changing a default so that an input that used to succeed is rejected.

Not breaking (MINOR or PATCH):

- Adding optional request fields, response fields, endpoints, flags, reason codes or enum-like values. Clients must
  ignore unknown fields; do not exhaustively switch over reason codes or tiers without a default branch.
- Correcting an output that was wrong. Address parsing is heuristic; a fix that changes the standardized output for a
  previously mis-parsed input is a PATCH or MINOR change and is listed under **Changed** or **Fixed** in the changelog.
  If you need frozen output, pin the version and re-run your regression corpus when upgrading.
- Performance improvements and internal refactors.

## Deprecation policy

1. A feature is first marked deprecated in a MINOR release: the changelog lists it under **Deprecated**, the docs say
   what replaces it, and Python callers receive a `DeprecationWarning` where practical.
2. It is removed no sooner than the next MAJOR release, and never in fewer than six months after the deprecation.
3. Security fixes may shorten this when a feature cannot be made safe; the changelog and a security advisory say so.

## Supported Python versions

- The supported range is the versions listed in the `Programming Language :: Python` classifiers in `pyproject.toml`
  and tested in CI (currently 3.11 to 3.13; CI runs the oldest and newest).
- A Python version is added in a MINOR release once CI passes on it.
- A version is dropped only in a MAJOR release, after it reaches upstream end-of-life, and is announced under
  **Deprecated** one MINOR release earlier.
- The SDKs follow the same rule for their runtimes (Node, .NET, Go as pinned in the CI workflow).

## Supported release lines

Security fixes and bug fixes target the latest MINOR line of the current MAJOR version. See `SECURITY.md` for the
security-support table.

## Pre-releases

The release workflow only publishes tags of the form `vX.Y.Z`; pre-release suffixes are not published.
