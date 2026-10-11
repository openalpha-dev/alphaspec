# AlphaSpec 0.2 — semantics

The JSON Schemas in `schema/<version>/` define the shape of each document. This page defines
what the fields **mean**, where the shape alone cannot. Where this page and a runtime
disagree, the runtime is non-compliant.

## 1. Documents

Every document has `contractVersion` and `kind`.

| kind | Written by | Purpose |
|---|---|---|
| `artifact` | strategy author / agent | a complete declarative strategy (L2) |
| `score` | model / research pipeline | cross-sectional scores or target weights (L1) |
| `gate-result` | runtime | the verdict on a submission |
| `evidence` | runtime | what happened when it ran |

A runtime must refuse a `contractVersion` it does not implement rather than guess.
Versions are additive: a document is validated against the schemas of the version it
declares, so a `0.1` document carrying `0.2` fields is rejected, not half-read. Use `0.2`
when you need trade settings (section 4a).

## 2. Time

### 2.1 Market-local calendar
All dates (`asOf`, sample windows) are trading days in the **market's own calendar and
time zone**: `Asia/Shanghai` for `cn_*`, `America/New_York` for `us_equity`, and so on.
"Today" for a market is never the server's date.

### 2.2 `asOf` for scores
A score with `asOf = T` may use information available at T's close and nothing later.
It is executed no earlier than the next session after T. A runtime receiving a score
after its rebalance cutoff for T+1 must say what it did (skipped, used it late) in
evidence; it must not silently trade on stale scores.

### 2.3 Bars
A bar is identified by its **end**: the 1d bar of T covers T's whole session and becomes
visible only after the session closes. A 15m bar labelled 10:00 covers 09:45–10:00.

### 2.4 `barPolicy`
On an indicator whose `timeframe` is coarser than the artifact's primary timeframe:

- `CLOSED` (default): the indicator sees only completed bars of its timeframe. At 10:00
  on day T, a daily indicator sees days up to T-1.
- `LIVE`: the indicator includes the forming bar, updated with intraday data.

`LIVE` is meaningful in live trading, and look-ahead in a backtest unless the runtime
rebuilds the forming bar strictly from data before each evaluation point. Version 0.1
forbids it for higher timeframes (rule AS003).

## 3. Instruments

### 3.1 Identity
An instrument is `(market, symbol)`. On `cn_*` and `hk_*` markets the venue suffix is
part of the symbol (`600000.SH`); elsewhere the symbol is the venue's own ticker
(`AAPL`, `BTCUSDT`).

### 3.2 Units
Quantities in evidence are in `caliber.volumeUnit`. Derivatives are counted in
contracts; notional = quantity × price × contract multiplier, and
`caliber.multiplierApplied` states whether reported notionals already include it.
Monetary fields are in `caliber.currency`.

## 4. Rule tree (artifact `dsl`)

- `indicators` maps aliases to indicator instances. Rules reference them as
  `{"ind": "alias"}`. `close` is a built-in alias.
- Operands are `{"ind"}`, `{"const"}`, `{"ref"}`, inline arithmetic
  `{"op": "SUB", "left", "right"}`, or rule statistics `{"op": "COUNT" | "BARS_SINCE", "rule", "bars"}`.
  **A bare number is not an operand**; write `{"const": 0}`.
- Scalar settings (`period`, `bars`, `tolerancePct`, ...) take a number, `{"const"}` or `{"ref"}`.
- `{"ref": "name"}` resolves against `dsl.params`. Put anything you intend to tune there.
- Logical nodes: `AND`/`OR` take `left`/`right` rules; `NOT` and `DAY_LATCH` take `rule`.
- Comparisons: `GT GTE LT LTE EQ NEQ CROSS_UP CROSS_DOWN` take `left`/`right` operands.
- Temporal: `HOLD_FOR` (held on each of the last N bars), `WITHIN` (held on at least one
  of the last N bars), `SEQUENCE` (`then` holds now and `first` held within the previous
  N bars), `DAY_LATCH` (stays true for the rest of the session once true).
- Level events: `TOUCH BREAK RECLAIM RETEST HOLD` against any operand as `level`.

Entry fires on the bar where `entry` evaluates true. Position size, fill timing and
protective exits are set in section 4a; the rest of the execution model (slippage, costs,
partial fills) is the runtime's and is reported in evidence.

## 4a. Trade settings (0.2: `exits`, `sizing`, `execution`)

`dsl.entry` / `dsl.exit` say **when** to trade. These three optional blocks say how a
position is managed once it exists. Field names are the ones visual strategy builders on the
reference runtime already use, so an exported strategy and a hand-written one look the same.

**`exits`** — evaluated on each bar's close, long positions, in addition to `dsl.exit`.
Whichever fires first closes the whole position.

| field | closes when |
|---|---|
| `stopLossPct` | close ≤ entry × (1 − p/100) |
| `takeProfitPct` | close ≥ entry × (1 + p/100) |
| `trailingStopPct` | close ≤ highest close since entry × (1 − p/100) |
| `trailingArmProfitPct` | (modifies the trailing stop) it only starts once the gain reached p%; 0 = from entry |
| `atrStopMultiplier` | close ≤ entry − k × ATR(14) |
| `atrTakeProfitMultiplier` | close ≥ entry + k × ATR(14) |
| `noNewHighDays` | n trading days pass without a new highest close since entry |
| `minHoldDays` | (modifies everything, `dsl.exit` included) nothing closes the position until n **trading days** after entry |

- Omit a field to leave that exit off. `0` is rejected for the on/off fields: one runtime's
  "disabled" is another's "stop immediately".
- `minHoldDays` counts trading days in the market's calendar: the entry day is day 0, weekends and
  holidays do not count, and the meaning is the same on every timeframe (3 on a 5m strategy is three
  trading days). It holds back rule exits too: its purpose is to keep a fresh position from being
  shaken out by short-term noise. Leave it out if the strategy should be free to exit at once.

**`sizing`** — how large each position is and how many are held.

| field | meaning |
|---|---|
| `positionMode` | `FIXED_PCT` (default): each entry buys `targetPctPerOrder`% of current equity. `ATR_RISK`: each entry is sized so one ATR(14) against it costs `targetPctPerOrder`% of equity; no entry while ATR cannot be computed |
| `targetPctPerOrder` | the percentage above (required when `sizing` is present) |
| `maxHoldings` | at most n symbols held at once; buys already queued count as held, so signals on the same bar cannot overshoot; further entries are skipped |
| `scaleIn` | pyramiding: `{maxAddOns, spacingAtr, maxTotalPct}` — add to a winner each time the close is `spacingAtr` × ATR(14) above the last buy, at most `maxAddOns` times; an add-on that would take the symbol above `maxTotalPct`% of equity is skipped; filled per `execution.fillTiming`, never on a bar that closes the position |

Equity is cash plus the market value of all positions. Every buy rounds down to the market's
lot and is capped by `riskProfile.maxSymbolExposurePct` and by cash. Without a `sizing`
block the runtime applies its own default, which a runtime must document (the reference
runtime's is in RUNTIME_API.md); write the block whenever position size matters.

**`execution`** — `fillTiming`: `NEXT_OPEN` (default) confirms the signal on the bar's close
and fills at the next bar's open; `BAR_CLOSE` fills at the signal bar's close.

**Not in 0.2, rejected if present**: fixed share counts, averaging down (adding as the price
falls), add-ons spaced in percent rather than ATR.

## 5. Gates

A gate result with `computedBy: "SELF_REPORTED"` carries numbers the submitter supplied.
Public rankings and any automatic promotion to live trading must use `PLATFORM` results
only. Additional checks for generated output (`producer.kind` `AI_AGENT` or
`FACTOR_MINER`):

- `GATE_OUT_OF_SAMPLE`: the most recent segment of the runtime's evaluation, judged relative to
  the market over the same period (beat the index, stay within the drawdown limit).
- `GATE_MULTIPLE_TESTING`: Sharpe deflated by `producer.searchTrials`.
- `GATE_LOOKAHEAD`: the structural checks of section 2 hold.

Deflation alone does not catch leakage; it is necessary, not sufficient.

## 6. What a document must never contain

- Orders, accounts, broker routes. A spec document states intent; execution goes through
  the runtime's single order path, the same one a human uses.
- Code, or strings that are executed.
- Performance figures as trusted input.
