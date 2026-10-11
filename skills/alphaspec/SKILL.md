---
name: alphaspec
description: Write, fix, validate and submit AlphaSpec documents — declarative trading-strategy artifacts (a rule tree of indicators with entry/exit conditions, universe and risk settings) and model score submissions — and run them on an AlphaSpec runtime for backtest, gate and paper trading. Use when asked to turn a trading idea into a strategy, write or edit a strategy as JSON/DSL, add stops, position sizing or fill timing, explain an AlphaSpec validation error (SCHEMA, AS001–AS105), or submit / evaluate / promote a strategy.
---

# AlphaSpec

AlphaSpec documents are JSON and contain no code. Everything you need comes from the `alphaspec` command; do not guess indicator names or parameter keys.

## Setup (once)

```bash
pip install alphaspec          # validator, indicator catalog, schemas, examples, runtime client
alphaspec --version
```

If you have no shell but the `alphaspec` MCP server is connected, use its tools instead: the same steps map to `list_examples`/`get_example`, `search_indicators`/`get_indicator`, `validate`/`explain_rule`, `submit`, `evaluate` then poll `gate_result`, and `promote`.

## Workflow

1. **Pick the document type.**
   - The user has a model or factor producing a number per symbol per day → `kind: "score"` (see `alphaspec examples 01-model-scores` and `alphaspec schema score`).
   - The user describes conditions on indicators → `kind: "artifact"`. The rest of this guide is about artifacts.
2. **Start from an example**: `alphaspec examples` lists them; `alphaspec examples 01-ema-cross` prints one.
3. **Choose market and timeframe.** Markets: `alphaspec docs markets`. Timeframes are exactly `tick 1m 5m 15m 30m 1h 4h 1d 1w` (`1h`, never `60m`).
4. **Find indicators** — never invent names:
   - `alphaspec catalog --market <market> --search <word>` to find candidates (search in English or Chinese: `RSI`, `moving average`, `breakout`, `均线`). Add `--lang zh` or `--lang en` to pick the description language; the default follows the locale.
   - `alphaspec catalog --type <TYPE>` for the full entry: parameter keys, defaults, ranges, meaning, unit and **pitfalls**. Read the pitfalls; several conditions that look natural can never be true (e.g. `close > DAY_HIGH`).
5. **Write the document**, then **validate until clean**:
   ```bash
   alphaspec validate doc.json          # fix every ERROR; treat WARNINGs as probable mistakes
   alphaspec rules --explain AS003      # why a rule exists and how to fix it
   ```
6. **Submit and evaluate** (only if the user wants it run; see below).

## Rule tree essentials

```json
"dsl": {
  "version": 1,
  "params": { "fastPeriod": 20 },
  "indicators": {
    "fast":  { "type": "EMA", "period": { "ref": "fastPeriod" } },
    "slow":  { "type": "EMA", "period": 60 },
    "trend": { "type": "EMA", "period": 50, "timeframe": "1d", "barPolicy": "CLOSED" }
  },
  "entry": { "type": "AND",
             "left":  { "type": "CROSS_UP", "left": { "ind": "fast" }, "right": { "ind": "slow" } },
             "right": { "type": "GT", "left": { "ind": "close" }, "right": { "ind": "trend" } } },
  "exit":  { "type": "CROSS_DOWN", "left": { "ind": "fast" }, "right": { "ind": "slow" } }
}
```

- `AND` / `OR`: `left` and `right` are **rules**. `NOT` / `DAY_LATCH`: the child goes in `rule`, not `left`.
- Comparisons `GT GTE LT LTE EQ NEQ CROSS_UP CROSS_DOWN`: `left` / `right` are **operands**.
- An operand is `{"ind": alias}`, `{"const": n}`, `{"ref": param}`, inline arithmetic `{"op": "SUB", "left": …, "right": …}` or `{"op": "COUNT" | "BARS_SINCE", "rule": …, "bars": n}`. **Never a bare number**: `"right": 30` is invalid, write `{"const": 30}`.
- `close` is a built-in alias. Every other alias must be declared in `indicators`.
- Temporal rules: `HOLD_FOR` (held each of the last N bars), `WITHIN` (held at least once in the last N), `SEQUENCE` (`first` then `then` within N bars).
- Level events `TOUCH BREAK RECLAIM RETEST HOLD` take any operand as `level` (a band, a moving average, a pivot).
- An indicator on a coarser `timeframe` than the strategy's must use `barPolicy: "CLOSED"` (the default). `LIVE` there is look-ahead (AS003).
- Put anything tunable in `dsl.params` and reference it with `{"ref": …}`.
- Symbols on `cn_*` / `hk_*` carry the venue suffix: `600000.SH`, `000001.SZ`, `00700.HK` (AS011).
- Indicators of profile `ext.cn` (price-limit streaks, sealed boards, call auction) exist only on `cn_*` markets.

## Trade settings (contract 0.2)

Stops, sizing and fill timing go in three optional top-level blocks — not in the rule tree. Set `"contractVersion": "0.2"` to use them.

```json
"exits":     { "stopLossPct": 8, "trailingStopPct": 10, "trailingArmProfitPct": 15, "noNewHighDays": 20 },
"sizing":    { "positionMode": "FIXED_PCT", "targetPctPerOrder": 20, "maxHoldings": 5 },
"execution": { "fillTiming": "NEXT_OPEN" }
```

- Other exits: `takeProfitPct`, `atrStopMultiplier`, `atrTakeProfitMultiplier` (ATR 14), `minHoldDays` (calendar days during which stops do not fire). Percentages are 0–100.
- Leave a field out to turn that exit off; never write `0` (rejected).
- **Always write `sizing`.** Without it the reference runtime sizes entries by its account limits (up to 60% of equity per symbol), which rarely matches what the user has in mind.
- Keep `sizing.targetPctPerOrder` ≤ `riskProfile.maxSymbolExposurePct` (AS017).
- Volatility sizing: `"positionMode": "ATR_RISK", "targetPctPerOrder": 1` = risk 1% of equity per ATR(14).
- Pyramiding: `"scaleIn": {"maxAddOns": 3, "spacingAtr": 0.5, "maxTotalPct": 40}` inside `sizing`; keep `maxTotalPct` ≥ 2 × `targetPctPerOrder` under FIXED_PCT (AS018).
- Not available, rejected if written: fixed share counts, averaging down. If the user asks for one, say so instead of approximating it.
- Full field semantics: `alphaspec docs spec` (section 4a); example: `alphaspec examples 06-trend`.

## Producer

If you (an AI) wrote or tuned the document: `"producer": {"kind": "AI_AGENT", "name": "<your tool>@<version>", "modelId": "<model>", "searchTrials": N}`, where `N` counts **every** candidate evaluated in this search, including discarded ones. Under-reporting it hides search luck from the gate.

## Submitting to the runtime

Needs `ALPHASPEC_BASE_URL` and `ALPHASPEC_API_KEY` (the user creates the key in the runtime's account page; never ask them to paste it into a file you commit).

```bash
alphaspec whoami                         # check the key first
alphaspec submit doc.json --evaluate     # validate, submit, evaluate on platform-chosen windows, print the gate result
alphaspec result <artifactId>            # re-read the latest gate result
alphaspec promote <artifactId>           # only after the gate passed; creates a DISABLED paper strategy
```

- Exit code 1 = rejected, gate not passed or evaluation failed. Read the printed checks and hints, change the document, submit it again as a new artifact and count it in `searchTrials`.
- Evaluations have a daily quota. Do not loop submissions hunting for a passing variant; that is exactly the search luck the gate corrects for.
- Never state backtest numbers the runtime did not return. After `promote`, tell the user the strategy is created disabled and they start it themselves.
- Full API and status codes: `alphaspec docs runtime`.

## Never

- Put code, scripts or expression strings into a document.
- Include orders, account ids or broker routes.
- Report performance figures as fields of a submission. The runtime computes them.

## Reference

`alphaspec docs spec` (field semantics: time, bars, units) · `alphaspec docs rules` (every lint rule) · `alphaspec schema artifact` (the JSON Schema).
