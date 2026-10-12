"""Semantic lint rules. Each rule exists because the mistake it catches was made in
production at least once and the runtime accepted it without complaint.

Every rule code here must be documented in docs/RULES.md (enforced by tests).
"""
from __future__ import annotations

import datetime as _dt
from collections.abc import Iterator
from typing import Any

from ._resources import load_catalog
from .validate import Issue

RULES: dict[str, str] = {
    "AS001": "Indicator reference does not resolve",
    "AS002": "Parameter reference does not resolve",
    "AS003": "Higher-timeframe indicator uses LIVE bars (look-ahead)",
    "AS004": "Indicator references form a cycle",
    "AS005": "Unknown indicator type",
    "AS006": "Unknown indicator parameter",
    "AS007": "Indicator not available on this market",
    "AS008": "timeframe/barPolicy ignored for primary-series-only indicator",
    "AS009": "Indicator timeframe finer than primary timeframe",
    "AS010": "tick timeframe cannot be bar-backtested",
    "AS011": "Symbol missing venue suffix",
    "AS012": "searchTrials required for generated output",
    "AS013": "No exit rule",
    "AS014": "Intraday indicator on a too-coarse primary timeframe",
    "AS015": "Indicator defined but never used",
    "AS016": "Trailing-stop activation without a trailing stop",
    "AS017": "Entry size above the per-symbol exposure cap",
    "AS018": "Pyramiding cap leaves no room for an add-on",
    "AS019": "Short rules on a market that cannot be shorted",
    "AS020": "Short entry without a short exit",
    "AS021": "Factor bound more than once",
    "AS022": "topN covers the whole symbol list",
    "AS101": "Duplicate symbol in submission",
    "AS102": "Every score is null",
    "AS103": "asOf is in the future",
    "AS104": "Zeros look like missing values",
    "AS105": "Weights sum above 1",
}

_TF_SECONDS = {"tick": 1, "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
               "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800}

# Markets whose codes are only unique together with a venue suffix (600000.SH vs 600000.SZ...).
_SUFFIX_MARKET_PREFIXES = ("cn_", "hk_")

# Built-in aliases the runtime resolves without an indicators entry.
_BUILTIN_ALIASES = {"close"}

# Markets where a short position cannot be opened (cash equities, spot crypto).
_NON_SHORTABLE_MARKETS = {"cn_stock", "cn_etf", "cn_convbond", "crypto_spot"}

_RULE_KEYS = ("entry", "exit", "shortEntry", "shortExit")


def _issue(code: str, sev: str, path: str, msg: str, hint: str = "") -> Issue:
    return Issue(code, sev, path, msg, hint)


def run(doc: dict[str, Any], kind: str) -> list[Issue]:
    if kind == "artifact":
        return list(_artifact(doc))
    if kind == "score":
        return list(_score(doc))
    return []


# ---------------------------------------------------------------- shared

def _walk(node: Any, path: str) -> Iterator[tuple[str, Any]]:
    yield path, node
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}/{i}")


def _ind_refs(node: Any, path: str) -> Iterator[tuple[str, str]]:
    for p, n in _walk(node, path):
        if isinstance(n, dict) and isinstance(n.get("ind"), str):
            yield p, n["ind"]


def _param_refs(node: Any, path: str) -> Iterator[tuple[str, str]]:
    for p, n in _walk(node, path):
        if isinstance(n, dict) and set(n) == {"ref"} and isinstance(n["ref"], str):
            yield p, n["ref"]


def _symbols_need_suffix(market: str) -> bool:
    return market.startswith(_SUFFIX_MARKET_PREFIXES)


def _check_symbol(market: str, symbol: str, path: str) -> Iterator[Issue]:
    if _symbols_need_suffix(market) and "." not in symbol:
        yield _issue("AS011", "error", path,
                     f"symbol {symbol!r} has no venue suffix; on {market} the suffix is part of the identity",
                     "write e.g. 600000.SH / 000001.SZ / 00700.HK")


def _check_producer(producer: dict[str, Any], path: str) -> Iterator[Issue]:
    if producer.get("kind") in ("AI_AGENT", "FACTOR_MINER") and "searchTrials" not in producer:
        yield _issue("AS012", "error", f"{path}/searchTrials",
                     f"producer.kind={producer['kind']} must report searchTrials",
                     "count every candidate you evaluated before submitting this one; "
                     "it feeds the multiple-testing correction")


# ---------------------------------------------------------------- artifact

def _artifact(doc: dict[str, Any]) -> Iterator[Issue]:
    market: str = doc["market"]
    if "dsl" in doc:
        yield from _rule_tree(doc, market)
    yield from _factors(doc)

    universe = doc.get("universe") or {}
    for i, sym in enumerate(universe.get("symbols", [])):
        yield from _check_symbol(market, sym, f"/universe/symbols/{i}")

    yield from _check_producer(doc["producer"], "/producer")


def _factors(doc: dict[str, Any]) -> Iterator[Issue]:
    seen: dict[str, int] = {}
    for i, b in enumerate(doc.get("factorBindings") or []):
        f = b["factor"]
        if f in seen:
            yield _issue("AS021", "warning", f"/factorBindings/{i}/factor",
                         f"{f} is already bound at index {seen[f]}; its weight is counted twice",
                         "merge the two bindings into one with the combined weight")
        else:
            seen[f] = i
    ranking = doc.get("ranking") or {}
    symbols = (doc.get("universe") or {}).get("symbols") or []
    if "topN" in ranking and symbols and ranking["topN"] >= len(symbols):
        yield _issue("AS022", "warning", "/ranking/topN",
                     f"topN={ranking['topN']} with {len(symbols)} symbols holds every symbol: the factor ranks nothing",
                     "use a larger universe or a smaller topN")


def _rule_tree(doc: dict[str, Any], market: str) -> Iterator[Issue]:
    primary: str = doc["timeframe"]
    dsl: dict[str, Any] = doc["dsl"]
    indicators: dict[str, Any] = dsl["indicators"]
    params: dict[str, Any] = dsl.get("params", {})
    catalog = load_catalog()
    by_type = {t["type"]: t for t in catalog["types"]}
    primary_only = set(catalog.get("primarySeriesOnly", []))
    common_keys = set(catalog.get("commonKeys", []))

    known_aliases = set(indicators) | _BUILTIN_ALIASES

    # AS001 / AS002 - every reference resolves.
    for p, alias in _ind_refs(dsl, "/dsl"):
        if alias not in known_aliases:
            yield _issue("AS001", "error", p, f"indicator alias {alias!r} is not defined in dsl.indicators",
                         "an unresolved reference compiles to nothing and the rule never fires")
    for p, name in _param_refs(dsl, "/dsl"):
        if name not in params:
            yield _issue("AS002", "error", p, f"parameter {name!r} is not defined in dsl.params")

    # AS004 - cycles between indicators.
    graph = {a: {r for _, r in _ind_refs(spec, "")} & set(indicators) for a, spec in indicators.items()}
    yield from _cycles(graph)

    # AS015 - unused indicators.
    used = {r for _, r in _ind_refs({k: dsl.get(k) for k in _RULE_KEYS}, "")}
    frontier = list(used)
    while frontier:
        for r in graph.get(frontier.pop(), ()):
            if r not in used:
                used.add(r)
                frontier.append(r)
    for alias in indicators:
        if alias not in used:
            yield _issue("AS015", "warning", f"/dsl/indicators/{alias}",
                         f"indicator {alias!r} is never referenced by entry/exit/shortEntry/shortExit")

    for alias, spec in indicators.items():
        path = f"/dsl/indicators/{alias}"
        itype = spec["type"]
        meta = by_type.get(itype)
        if meta is None:
            yield _issue("AS005", "error", f"{path}/type", f"unknown indicator type {itype!r}",
                         "see catalog/indicators.json for the supported types")
            continue

        allowed = common_keys | {p["key"] for p in meta.get("params", [])} \
            | set(meta.get("operandKeys", [])) | {"in", "left", "right"}
        for key in spec:
            if key not in allowed:
                yield _issue("AS006", "warning", f"{path}/{key}",
                             f"{itype} has no parameter {key!r}; it will be ignored")

        profile = meta.get("profile", "core")
        if profile == "ext.cn" and not market.startswith("cn_"):
            yield _issue("AS007", "error", f"{path}/type",
                         f"{itype} encodes China-market rules (profile ext.cn) and has no meaning on {market}")

        tf = spec.get("timeframe")
        if itype in primary_only and (tf or "barPolicy" in spec):
            yield _issue("AS008", "warning", path,
                         f"{itype} is always computed on the primary series; timeframe/barPolicy are ignored")
            continue

        if tf:
            if _TF_SECONDS[tf] < _TF_SECONDS[primary]:
                yield _issue("AS009", "error", f"{path}/timeframe",
                             f"indicator timeframe {tf} is finer than the primary timeframe {primary}",
                             "a finer series cannot be derived from coarser bars; lower the primary timeframe")
            elif _TF_SECONDS[tf] > _TF_SECONDS[primary] and spec.get("barPolicy") == "LIVE":
                yield _issue("AS003", "error", f"{path}/barPolicy",
                             f"{tf} indicator on a {primary} strategy with barPolicy=LIVE reads the "
                             f"still-forming {tf} bar; in a backtest that bar already contains the future",
                             "use barPolicy CLOSED (the default)")

        max_tf = meta.get("maxPrimaryTimeframe")
        if max_tf and _TF_SECONDS[primary] > _TF_SECONDS.get(max_tf, 10**9):
            yield _issue("AS014", "error", f"{path}/type",
                         f"{itype} is an intraday indicator and needs a primary timeframe of {max_tf} or finer, "
                         f"strategy runs on {primary}")

    if primary == "tick":
        yield _issue("AS010", "warning", "/timeframe",
                     "tick strategies are evaluated per market-data frame; that dimension does not exist "
                     "in bar history, so bar backtests will refuse them")

    exits: dict[str, Any] = doc.get("exits") or {}
    if "entry" in dsl and "exit" not in dsl and not exits:
        yield _issue("AS013", "warning", "/dsl",
                     "no exit rule and no exits block: positions close only through rebalancing",
                     "add dsl.exit or an exits block (stop loss, trailing stop, ...)")
    if "shortEntry" in dsl and "shortExit" not in dsl and not exits:
        yield _issue("AS020", "warning", "/dsl/shortEntry",
                     "short entry without dsl.shortExit or an exits block: short positions are never covered by a rule",
                     "add dsl.shortExit or stops in exits")
    if market in _NON_SHORTABLE_MARKETS:
        for k in ("shortEntry", "shortExit"):
            if k in dsl:
                yield _issue("AS019", "error", f"/dsl/{k}",
                             f"{market} cannot be sold short; short rules have no meaning there",
                             "remove the short rules, or use a market that allows shorting (e.g. cn_future)")

    yield from _trade_settings(doc, exits)


def _trade_settings(doc: dict[str, Any], exits: dict[str, Any]) -> Iterator[Issue]:
    if "trailingArmProfitPct" in exits and "trailingStopPct" not in exits:
        yield _issue("AS016", "warning", "/exits/trailingArmProfitPct",
                     "trailingArmProfitPct only says when a trailing stop starts; without trailingStopPct "
                     "there is nothing to start",
                     "add trailingStopPct, or remove trailingArmProfitPct")

    sizing: dict[str, Any] = doc.get("sizing") or {}
    fixed_pct = sizing.get("positionMode", "FIXED_PCT") == "FIXED_PCT"
    per_order = sizing.get("targetPctPerOrder")
    cap = (doc.get("riskProfile") or {}).get("maxSymbolExposurePct")
    # Under ATR_RISK targetPctPerOrder is a risk budget, not a position size; nothing to compare.
    if fixed_pct and per_order is not None and cap is not None and per_order > cap:
        yield _issue("AS017", "warning", "/sizing/targetPctPerOrder",
                     f"each entry asks for {per_order}% of equity but riskProfile.maxSymbolExposurePct caps a "
                     f"symbol at {cap}%; every entry will be cut to {cap}%",
                     "make them agree so the backtest sizes positions the way you read the document")

    total = (sizing.get("scaleIn") or {}).get("maxTotalPct")
    if fixed_pct and per_order is not None and total is not None and total < 2 * per_order:
        yield _issue("AS018", "warning", "/sizing/scaleIn/maxTotalPct",
                     f"the first entry already takes {per_order}% and each add-on another {per_order}%; "
                     f"a {total}% cap leaves no room for a single add-on",
                     f"raise maxTotalPct to at least {2 * per_order}, or drop scaleIn")


def _cycles(graph: dict[str, set[str]]) -> Iterator[Issue]:
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}
    reported: set[frozenset[str]] = set()

    def visit(n: str, stack: list[str]) -> Iterator[Issue]:
        color[n] = GREY
        stack.append(n)
        for m in sorted(graph[n]):
            if color[m] == GREY:
                cyc = stack[stack.index(m):]
                key = frozenset(cyc)
                if key not in reported:
                    reported.add(key)
                    yield _issue("AS004", "error", f"/dsl/indicators/{m}",
                                 "indicator references form a cycle: " + " -> ".join(cyc + [m]))
            elif color[m] == WHITE:
                yield from visit(m, stack)
        stack.pop()
        color[n] = BLACK

    for n in sorted(graph):
        if color[n] == WHITE:
            yield from visit(n, [])


# ---------------------------------------------------------------- score

def _score(doc: dict[str, Any]) -> Iterator[Issue]:
    market = doc["market"]
    rows_key = "scores" if "scores" in doc else "weights"
    rows = doc[rows_key]

    seen: dict[str, int] = {}
    for i, row in enumerate(rows):
        sym = row["symbol"]
        if sym in seen:
            yield _issue("AS101", "error", f"/{rows_key}/{i}/symbol",
                         f"{sym} also appears at index {seen[sym]}")
        else:
            seen[sym] = i
        yield from _check_symbol(market, sym, f"/{rows_key}/{i}/symbol")

    if rows_key == "scores":
        values = [r["score"] for r in rows]
        if all(v is None for v in values):
            yield _issue("AS102", "error", "/scores", "every score is null; nothing can be ranked")
        zeros = sum(1 for v in values if v == 0)
        if zeros and None not in values and zeros / len(values) >= 0.2:
            yield _issue("AS104", "warning", "/scores",
                         f"{zeros} of {len(values)} scores are exactly 0 and none are null",
                         "if 0 means 'no data', send null: 0 is a real rank position")
    else:
        total = sum(r["weight"] for r in rows)
        if total > 1 + 1e-9:
            yield _issue("AS105", "error", "/weights", f"weights sum to {total:.6f}; must be <= 1 (remainder is cash)")

    as_of = _dt.date.fromisoformat(doc["asOf"])
    # One day of slack: asOf is in the market's calendar, which can be ahead of UTC.
    if as_of > _dt.datetime.now(_dt.timezone.utc).date() + _dt.timedelta(days=1):
        yield _issue("AS103", "error", "/asOf", f"asOf {as_of} is in the future")

    yield from _check_producer(doc["producer"], "/producer")
