# Contributing to Phone Standardizer

Thank you for contributing to **Phone Standardizer**! Owned and maintained by **HobbyHabbit LLC** under the **MIT License**.

## Quality & Testing Gates

1. **100% Line & Branch Coverage Floor**: `pytest --cov` enforces `fail_under = 100` in `pyproject.toml`. Every new branch or country rule must include corresponding unit tests in `tests/`.
2. **Zero Linter Warnings**: `ruff check .` must exit cleanly with `0` warnings.
3. **Synthetic Test Numbers Only**: Never commit real personal phone numbers. Always use official fictitious/drama ranges (e.g., North American `NPA-555-0100` to `0199` or UK Ofcom `020 7946 0xxx` / `01632 960xxx`).
