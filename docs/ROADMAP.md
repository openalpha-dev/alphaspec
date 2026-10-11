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

## 0.3 — Capabilities

A runtime publishes what it can do so an agent can plan before it writes:

- markets with data, timeframes per market, indicator profiles available per market;
- universe modes, benchmark used for out-of-sample comparison, where a passing strategy can be
  promoted (paper account type per market);
- `alphaspec capabilities` and an MCP tool; the Skill checks capabilities first.

## 0.4 — Direction and derivatives

- Long and short rule sets (`longEntry`, `longExit`, `shortEntry`, `shortExit`) for markets that
  allow shorting.
- Futures and options semantics: contract multiplier, margin basis, continuous-contract roll policy.
- Market profiles document lot sizes, settlement (T+0 / T+1), price limits and short-selling rules.

## 0.5 — Factors and scores

- Factor-ranked strategies end to end: `factorBindings`, `signalMode`, rebalance schedule.
- L1 `score` submissions: per-date scores or target weights from your own model, run through the
  same sizing, risk and gate.

## 0.6 — Universes

- Whole-market universes with filters (listing age, liquidity, market cap, exclusions).
- Dynamic universes defined by screening conditions and re-evaluated on a schedule.

## Round trip and evidence

- **Export**: a runtime can export any strategy it holds as AlphaSpec, so an agent can read,
  modify and resubmit an existing strategy; promotion can target a new version of it.
- **Evidence**: execution evidence (rejections, slippage, fills, drift from target) returned as
  `evidence` documents for promoted strategies.
