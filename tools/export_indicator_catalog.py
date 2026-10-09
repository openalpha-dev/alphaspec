#!/usr/bin/env python3
"""Generate catalog/indicators.json from a reference runtime's indicator metadata.

The catalog is generated, never hand-edited: the runtime's metadata file is the
single source of truth for which indicator types exist and what parameters they take.

    python tools/export_indicator_catalog.py \
        ../EasyQuant/backend/easyquant-backend/easyquant-app/src/main/resources/dsl/indicator-metadata.json

Profiles:
  core      - computable from OHLCV bars alone; any market.
  ext.cn    - encodes China-market rules (price limits, sealed limit-up boards,
              call auction, main-force money flow). Valid only on cn_* markets.
  ext.l2    - needs order-book / trade-by-trade data from the market-data source.
  ext.data  - needs a runtime-side dataset beyond bars (fundamentals, index series, other legs).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "catalog" / "indicators.json"
# 手工维护的译文：键是中文原文。原文一改键就对不上，测试会报缺译，而不是悄悄沿用旧译文。
I18N_EN = OUT.parent / "i18n" / "en.json"

EXT_CN = {
    "ZTB_GOLDEN_PIT", "ZTB_DRAWDOWN_LINE", "LIMIT_UP_DAYS",
    "LIMIT_UP_PRICE", "LIMIT_DOWN_PRICE", "DIST_TO_LIMIT_UP_PCT", "DIST_TO_LIMIT_DOWN_PCT", "DIST_TO_LIMIT_PCT",
    "INTRADAY_LIMIT_UP_HOLDING", "SEAL_AMOUNT", "SEAL_RATIO", "SEAL_TREND", "IS_SEALED", "BREAK_COUNT",
    "TRIGGER_SEAL", "TRIGGER_BREAK", "TRIGGER_RESEAL",
    "DDE_MAIN_NET_RT", "RECENT_MAIN_NET", "DAY_MAIN_NET",
    "PIT_DEPTH_RT", "VOL_HOLDING_AT_PIT", "SECTOR_INTRADAY_STRENGTH",
    "PATTERN_OLD_DUCK_HEAD", "PATTERN_GOLDEN_PIT", "PATTERN_PARABOLIC_LEADER",
    "AUCTION_VOLUME", "AUCTION_VOLUME_RATIO", "AUCTION_VS_PREV_VOL", "AUCTION_VS_PREV_DAY_VOL", "AUCTION_TURNOVER_PCT",
}
EXT_DATA = {"FUNDAMENTAL", "INDEX_MA_DIST_PCT", "LEG"}

# Parameter keys every indicator accepts in addition to its own.
COMMON_KEYS = ["type", "timeframe", "barPolicy"]


def profile_of(t: dict) -> str:
    name = t["type"]
    if name in EXT_CN:
        return "ext.cn"
    if name in EXT_DATA:
        return "ext.data"
    if t.get("dataLevel") == "L2" or t.get("requiresTickDrive"):
        return "ext.l2"
    return "core"


def export_param(p: dict) -> dict:
    out = {"key": p["key"], "kind": p.get("kind", "string")}
    for k in ("default", "min", "max"):
        if k in p:
            out[k] = p[k]
    if p.get("options"):
        out["values"] = [o["value"] for o in p["options"]]
    if p.get("description"):
        out["description"] = p["description"]
    return out


def attach_english(entry: dict, en: dict[str, str], missing: set[str]) -> None:
    def tr(text: str) -> str | None:
        if text in en:
            return en[text]
        missing.add(text)
        return None

    label = entry.get("labels", {}).get("zh")
    if label and tr(label):
        entry["labels"]["en"] = en[label]
    block: dict = {}
    if entry.get("summary") and tr(entry["summary"]):
        block["summary"] = en[entry["summary"]]
    pits = [tr(p) for p in entry.get("pitfalls", [])]
    if pits and all(pits):
        block["pitfalls"] = pits
    params = {p["key"]: tr(p["description"]) for p in entry["params"] if p.get("description")}
    if params and all(params.values()):
        block["params"] = params
    if block:
        entry["en"] = block


def main(src: str) -> int:
    meta = json.loads(Path(src).read_text(encoding="utf-8"))
    en = json.loads(I18N_EN.read_text(encoding="utf-8")) if I18N_EN.exists() else {}
    missing: set[str] = set()
    types = []
    for t in meta["types"]:
        if t.get("enabled") is False:
            continue
        entry = {
            "type": t["type"],
            "profile": profile_of(t),
            "params": [export_param(p) for p in t.get("params", [])],
        }
        if t.get("operandKeys"):
            entry["operandKeys"] = t["operandKeys"]
        if t.get("dataLevel"):
            entry["dataLevel"] = t["dataLevel"]
        if t.get("maxPrimaryTimeframe"):
            entry["maxPrimaryTimeframe"] = t["maxPrimaryTimeframe"]
        if t.get("requiresTickDrive"):
            entry["requiresTickDrive"] = True
        if t.get("unit"):
            entry["unit"] = t["unit"]
        if t.get("labelZh"):
            entry["labels"] = {"zh": t["labelZh"]}
        # 语义：agent 只看类型名和参数键选不对指标，也写不对条件（例如 close > DAY_HIGH 恒不成立）。
        # 说明文字目前是中文（来自运行时的指标百科），英文版待补。
        tutorial = t.get("tutorial") or {}
        if tutorial.get("summary"):
            entry["summary"] = tutorial["summary"]
        if tutorial.get("pitfalls"):
            entry["pitfalls"] = tutorial["pitfalls"][:3]
        if t.get("pattern"):
            entry["pattern"] = {k: t["pattern"][k] for k in ("bias", "layer") if k in t["pattern"]}
        attach_english(entry, en, missing)
        types.append(entry)

    types.sort(key=lambda e: e["type"])
    catalog = {
        "catalogVersion": "0.1",
        "language": "zh",
        "translations": ["en"],
        "generatedFrom": "easyquant indicator-metadata.json",
        "commonKeys": COMMON_KEYS,
        "primarySeriesOnly": ["LIMIT_UP_DAYS", "ZTB_GOLDEN_PIT", "ZTB_DRAWDOWN_LINE"],
        "types": types,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for e in types:
        counts[e["profile"]] = counts.get(e["profile"], 0) + 1
    print(f"wrote {OUT} ({len(types)} types: {counts})")
    if missing:
        print(f"{len(missing)} text(s) have no English translation in {I18N_EN.name}; add them:", file=sys.stderr)
        for m in sorted(missing):
            print(f"  {m}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
