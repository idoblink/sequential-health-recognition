"""
Initialize the SQLite database.

Usage:
    python scripts/init_db.py

Creates the instance/ directory and health_states.db with all
required tables if they do not already exist.
"""

import sys
import os

# Add project root to path so we can import services
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.database import init_db, DEFAULT_DB_PATH


def main():
    print(f"[init_db] Initializing database at: {DEFAULT_DB_PATH}")
    init_db()
    print(f"[init_db] Database ready.")


if __name__ == "__main__":
    main()
