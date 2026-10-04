"""Seed-script entry point: ``cd backend && python test_seed_data.py [--scale X]``.

Thin wrapper over the canonical implementation in ``src/tests/seed_data.py``
so the tests, locust, and docs all share one module.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from tests.seed_data import main

if __name__ == "__main__":
    main()
