"""Module execution entry point for python -m entity_standardizer."""

from __future__ import annotations

import sys

from phone_standardizer.cli import main

if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
