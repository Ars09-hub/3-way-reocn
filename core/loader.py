"""Load the three JSON config files."""
from __future__ import annotations

import json
import os

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")


def _load(name: str) -> dict:
    with open(os.path.join(CONFIG_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


def load_config() -> dict:
    return {
        "account_scope": _load("account_scope.json"),
        "engine": _load("engine.json"),
        "ksa": _load("ksa.json"),
    }
