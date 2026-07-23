"""Config loaders and validators.

No country or client logic lives in core code. Everything jurisdiction- or
client-specific is loaded from declarative JSON here and passed down as data.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class LoadedConfig:
    """Everything the pipeline needs, plus provenance for the manifest."""

    engine: dict
    country: dict
    client: dict
    paths: dict = field(default_factory=dict)
    hashes: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)

    # convenience accessors ------------------------------------------------
    @property
    def minor_exp(self) -> int:
        return int(self.country.get("minor_unit_exponent", 2))

    @property
    def rounding_abs_minor_per_doc(self) -> int:
        override = self.country.get("tolerances_override", {})
        if "rounding_abs_minor_per_doc" in override:
            return int(override["rounding_abs_minor_per_doc"])
        return int(self.engine["tolerances"]["rounding_abs_minor_per_doc"])

    @property
    def relative_tol(self) -> float:
        return float(self.engine["tolerances"]["relative_tol"])

    @property
    def max_relative_tol(self) -> float:
        return float(self.engine["tolerances"]["max_relative_tol_for_suggestion"])

    def account_class_for(self, gl_account: str | None) -> str:
        if gl_account is None:
            return "OTHER"
        acct = str(gl_account).strip()
        for cls, ranges in self.client.get("account_classes", {}).items():
            for lo, hi in ranges:
                if str(lo) <= acct <= str(hi):
                    return cls
        return "OTHER"

    def tax_rate_for(self, tax_code: str | None) -> tuple[Decimal | None, str | None]:
        if not tax_code:
            return None, None
        for r in self.country.get("tax_rates", []):
            if r["code"] == tax_code:
                return Decimal(str(r["rate"])), r.get("category")
        return None, None


def _expected_country_currency(country_pack: dict) -> str:
    return country_pack.get("currency", "")


def load_all(engine_path: str, country_path: str, client_path: str) -> LoadedConfig:
    engine = _read_json(engine_path)
    country = _read_json(country_path)
    client = _read_json(client_path)

    warnings: list[str] = []
    if country.get("completeness") == "partial":
        todos = [k for k, v in country.items() if v == "TODO"]
        warnings.append(
            f"Country pack {country.get('country')} is marked completeness=partial. "
            f"Fields still TODO: {sorted(todos)}. Engine will warn rather than assume."
        )

    cfg = LoadedConfig(
        engine=engine,
        country=country,
        client=client,
        paths={"engine": engine_path, "country": country_path, "client": client_path},
        hashes={
            "engine": file_sha256(engine_path),
            "country": file_sha256(country_path),
            "client": file_sha256(client_path),
        },
        warnings=warnings,
    )
    _validate(cfg)
    return cfg


def _validate(cfg: LoadedConfig) -> None:
    required_engine = ["tolerances", "matching", "scoring_weights", "plane_weights", "confidence_bands"]
    for key in required_engine:
        if key not in cfg.engine:
            raise ValueError(f"engine config missing '{key}'")
    w = cfg.engine["scoring_weights"]
    total = sum(float(v) for v in w.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"scoring_weights must sum to 1.0, got {total}")
    pw = cfg.engine["plane_weights"]
    if abs(sum(float(v) for v in pw.values()) - 1.0) > 1e-6:
        raise ValueError("plane_weights must sum to 1.0")
    if not cfg.client.get("field_mapping"):
        raise ValueError("client profile missing field_mapping")
