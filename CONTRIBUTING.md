# Contributing to Entity Standardizer

Thank you for contributing to **Entity Standardizer** (`entity_standardizer`, `address_standardizer`, and `phone_standardizer`)! Owned and maintained by **HobbyHabbit LLC** under the **MIT License**.

## Quality & Testing Gates

1. **100% Line & Branch Coverage Floor**: `pytest --cov` enforces `fail_under = 100` with `branch = true` in `pyproject.toml`. Every new branch, legal suffix, cross-healing rule, or dial-plan adjustment must include corresponding unit tests in `tests/`.
2. **Zero Linter Warnings**: `ruff check .` must exit cleanly with `0` warnings.
3. **Dual-Runtime & Multi-SDK Contract Parity**:
   - Native Rust changes in `src/lib.rs` must pass `cargo test` and preserve 100% behavioral parity with the pure-Python fallback in `phone_standardizer/_native_dispatch.py` and `entity_standardizer/company.py`.
   - Any additions to response dataclasses (`StandardizedPhone`, `StandardizedAddress`, `StandardizedCompany`, `StandardizedPerson`, `StandardizedJobTitle`, `StandardizedEmail`, `StandardizedUrl`, `StandardizedSocial`, `StandardizedContact`) must be synchronized across `sdks/typescript/src/types.ts`, `sdks/go/models.go`, and `sdks/dotnet/Models.cs` (enforced by `tests/test_sdk_contract.py`).
4. **Synthetic Test Data Only**: Never commit real personal phone numbers, residential street addresses, or private emails. Always use official fictitious/drama ranges (e.g., North American `NPA-555-0100` to `0199`, UK Ofcom `020 7946 0xxx` / `01632 960xxx`, or RFC 2606 test domains).
