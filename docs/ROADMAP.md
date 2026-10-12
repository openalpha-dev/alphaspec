# Roadmap

**Goal: one AlphaSpec document describes a complete strategy** — what to trade, when to enter and
exit, how much to hold, how to cut losses, on any market and timeframe a runtime has data for — so
that a strategy written by hand, drafted by an AI or exported from a platform is the same object
everywhere.

The contract grows in additive steps. Each step bumps `contractVersion`, ships schemas, lint rules,
conformance cases and catalog updates together, and is implemented by the reference runtime
(EasyQuant) before it is called done. Runtimes declare what they support; a document asking for more
than a runtime offers is rejected up front, never silently downgraded.

## 0.2 — Trade settings (done)

Everything a strategy needs beyond its signal, in three optional blocks next to `dsl`
(semantics: [SPEC.md §4a](SPEC.md)):

- **`exits`**: fixed stop loss and take profit, trailing stop with an activation threshold,
  ATR-based stop and take profit, minimum holding period, exit after N days without a new high.
- **`sizing`**: fixed fraction of equity or ATR risk budget per entry, maximum number of
  holdings, pyramiding (number of add-ons, spacing in ATR, total cap).
- **`execution`**: fill timing (next bar's open or the signal bar's close).

```json
"exits": {
  "stopLossPct": 8, "takeProfitPct": 20,
  "trailingStopPct": 10, "trailingArmProfitPct": 5,
  "atrStopMultiplier": 2.5, "atrTakeProfitMultiplier": 4,
  "minHoldDays": 3, "noNewHighDays": 20
},
"sizing": {
  "positionMode": "FIXED_PCT", "targetPctPerOrder": 20, "maxHoldings": 10,
  "scaleIn": { "maxAddOns": 3, "spacingAtr": 1, "maxTotalPct": 40 }
},
"execution": { "fillTiming": "NEXT_OPEN" }
```

The per-symbol cap stays where it was, `riskProfile.maxSymbolExposurePct`.

## 0.3 — Capabilities and round trip (done)

- `capabilities` document: per market, whether daily / intraday history covers the evaluation
  window (and why not), usable indicator profiles, promotability, out-of-sample benchmark,
  evaluation windows and quota. `alphaspec capabilities`, MCP `get_capabilities`; the Skill reads it first.
- Runtimes reject at submission what they cannot run (`RUNTIME_*` codes), without using quota.
- `gate-result.tradeSettings`: the exits, sizing and execution actually used, and every default.
- Export: a runtime exports a strategy it holds as an artifact; a passing modification can be
  promoted as a new version of it (`targetStrategyId`).

## 0.4 — Factors, scores, short rules, evidence (done)

- Factor-ranked strategies: `signalMode`, `factorBindings`, `ranking` (topN, rebalance, weighting,
  neutralization, weight cap), with or without a rule tree.
- Score series: daily `score` documents form a series an artifact ranks by (`score:<scoreName>`).
- Short rules: `dsl.shortEntry` / `dsl.shortExit` on markets that allow shorting; market trading rules
  (lots, settlement, price limits, shorting) in MARKETS.md.
- Evidence for strategies a runtime runs: rejections, execution quality, risk hits, fills, pipeline.

## Later

- Whole-market universes and universes defined by screening conditions, filtered point-in-time on
  every rebalance date (a filter applied once at evaluation time is survivorship-biased).
- Continuous futures contracts and roll policy; options.
- Target-weight (`weights`) score submissions executed as given.
- Stops on factor-ranked books.

