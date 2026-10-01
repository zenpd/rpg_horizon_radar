"""Loads the mock data files. In production these are replaced by the database
(signals, storylines, insights) written by the daily 17:00 pipeline."""
from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def load(name: str):
    with open(DATA_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


REF = load("reference")
