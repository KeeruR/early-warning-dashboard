"""Delete the local database so the next app start rebuilds the demo data.

Usage:  python scripts/reset_demo_data.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import config  # noqa: E402

for path in (config.DB_PATH, config.SEED_CSV_PATH):
    if path.exists():
        path.unlink()
        print(f"Deleted {path}")
print("Done. Restart the app to rebuild the synthetic demo data.")
