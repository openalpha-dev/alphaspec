"""Locate the bundled schema and catalog files.

Installed wheels carry them under alphaspec/_data; a source checkout reads them
from the repository root, so there is exactly one copy to edit.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "0.2"
# Every contract version this package can validate. Versions are additive: a 0.1 document is
# still checked against the 0.1 schemas, so it cannot pick up fields 0.1 did not have.
SUPPORTED_VERSIONS = ("0.1", "0.2")

_PKG_DATA = Path(__file__).resolve().parent / "_data"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _root() -> Path:
    if (_PKG_DATA / "schema").is_dir():
        return _PKG_DATA
    if (_REPO_ROOT / "schema").is_dir():
        return _REPO_ROOT
    raise FileNotFoundError("alphaspec schema files not found; reinstall the package")


def schema_dir(version: str = CONTRACT_VERSION) -> Path:
    return _root() / "schema" / version


@lru_cache(maxsize=None)
def load_schema(name: str, version: str = CONTRACT_VERSION) -> dict[str, Any]:
    path = schema_dir(version) / f"{name}.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def load_catalog() -> dict[str, Any]:
    path = _root() / "catalog" / "indicators.json"
    return json.loads(path.read_text(encoding="utf-8"))


def default_lang() -> str:
    """Language for catalog text: $ALPHASPEC_LANG, else zh on a Chinese locale, else en."""
    import os
    lang = os.environ.get("ALPHASPEC_LANG") or ""
    if lang in ("zh", "en"):
        return lang
    loc = os.environ.get("LC_ALL") or os.environ.get("LANG") or ""
    return "zh" if loc.lower().startswith("zh") else "en"


def localized(entry: dict[str, Any], lang: str) -> dict[str, Any]:
    """A catalog entry with summary, pitfalls, label and parameter descriptions in one language.

    The catalog keeps Chinese in the top-level fields and English under ``en``; agents asked
    for one language should not have to read both."""
    out = {k: v for k, v in entry.items() if k != "en"}
    labels = entry.get("labels") or {}
    if labels:
        out["label"] = labels.get(lang) or labels.get("zh")
        out.pop("labels")
    if lang == "en" and "en" in entry:
        en = entry["en"]
        out["summary"] = en.get("summary", out.get("summary"))
        if "pitfalls" in en:
            out["pitfalls"] = en["pitfalls"]
        descs = en.get("params", {})
        out["params"] = [{**p, "description": descs[p["key"]]} if p["key"] in descs else p
                         for p in entry.get("params", [])]
    return out


def data_root() -> Path:
    """Directory holding schema/, catalog/, examples/ and docs/ (installed copy or checkout)."""
    return _root()

