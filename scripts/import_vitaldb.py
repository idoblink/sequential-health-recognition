"""
Import VitalDB cases into the local SQLite database.

Usage:
    python scripts/import_vitaldb.py              # Import default 5 cases
    python scripts/import_vitaldb.py --num-cases 3  # Import 3 cases

This script downloads real surgical-monitoring data from the VitalDB
open dataset using the official `vitaldb` Python package.  It requires
an internet connection on first run.

The import is idempotent: re-running will skip already-imported cases.
"""

import sys
import os
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.database import init_db
from services.vitaldb_loader import import_cases, DEFAULT_NUM_CASES


def main():
    parser = argparse.ArgumentParser(description="Import VitalDB cases into SQLite.")
    parser.add_argument(
        "--num-cases", type=int, default=DEFAULT_NUM_CASES,
        help=f"Number of cases to import (default: {DEFAULT_NUM_CASES})"
    )
    args = parser.parse_args()

    # Ensure database is initialized
    print("[import] Ensuring database is initialized...")
    init_db()

    print(f"[import] Importing {args.num_cases} VitalDB cases...")
    print("=" * 60)
    summary = import_cases(num_cases=args.num_cases)
    print("=" * 60)
    print(f"[import] Done. {summary['message']}")


if __name__ == "__main__":
    main()
