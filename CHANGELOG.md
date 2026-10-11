# Changelog

## 0.2.1 — 2026-10-11

Semantics clarified to match what a runtime can apply the same way in backtests and live trading:

- `exits.minHoldDays` counts **trading days** (entry day = 0; weekends and holidays excluded) and holds back
  `dsl.exit` as well as the other exits. 0.2.0 said calendar days and left `dsl.exit` free.
- `sizing.scaleIn` add-ons are filled per `execution.fillTiming` (next open under `NEXT_OPEN`), and never on a bar
  that also closes the position. 0.2.0 said "at the close of the triggering bar".
- Reference runtime: backtests and live trading now apply both rules identically; live pyramiding honours
  `maxTotalPct`; live minimum holding is counted from the start of the current position, not the first time the
  symbol was ever held.

## 0.2.0 — 2026-10-11

- Contract 0.2 (`schema/0.2/`): trade settings in three optional artifact blocks.
  - `exits`: stop loss, take profit, trailing stop with activation, ATR stop / take profit, minimum holding days
    (see 0.2.1), no-new-high exit.
  - `sizing`: `FIXED_PCT` or `ATR_RISK` per entry, `maxHoldings`, pyramiding `scaleIn`.
  - `execution`: fill timing (`NEXT_OPEN` / `BAR_CLOSE`).
  Semantics in SPEC §4a.
- Versions are additive: the validator accepts 0.1 and 0.2 and checks each document against the schemas of the
  version it declares. `CONTRACT_VERSION` is now `"0.2"`; `SUPPORTED_VERSIONS` lists both.
- New lint rules AS016 (trailing-stop activation without a trailing stop), AS017 (entry size above the per-symbol
  cap) and AS018 (pyramiding cap leaves no room for an add-on). AS013 no longer fires when an `exits` block closes
  positions.
- Example `06-trend-with-trade-settings`.
- RUNTIME_API documents the reference runtime's default sizing when a document has no `sizing` block.
- Reference runtime: portfolio backtests (used by `evaluate`) now honour holding caps, ATR risk sizing and
  pyramiding, and size fixed-fraction entries on equity rather than remaining cash. Before this release those
  settings were silently ignored there, which is why they were not in 0.1.

## 0.1.0 — 2026-10-09

- Contract 0.1 drafts: `artifact`, `score`, `gate-result`, `evidence`, shared `common` definitions.
- Indicator catalog generated from the reference runtime (core / ext.cn / ext.l2 / ext.data profiles).
- Lint rules AS001–AS015 (artifact) and AS101–AS105 (score), each with a conformance case.
- Python validator and `alphaspec` CLI.
- Agent Skill in `skills/alphaspec`.
- Runtime client (`alphaspec.Client`, standard library only) and CLI commands: `whoami`, `submit`, `evaluate`, `result`, `list`, `promote`.
- `docs/RUNTIME_API.md`: the agent API a runtime exposes.
- Indicator catalog now carries meaning: summary, parameter descriptions, unit, pitfalls, in Chinese and English (`catalog/i18n/en.json`, keyed by the Chinese text so a changed description fails the tests until it is re-translated). `catalog --lang en|zh`, MCP `lang`.
- Reference commands so an installed Agent Skill needs no checkout: `catalog`, `schema`, `examples`, `docs`, `rules --explain`. Examples and docs ship inside the wheel.
- Agent Skill rewritten to be self-contained (`pip install alphaspec` + the commands above).
- RUNTIME_API: evaluation is one continuous backtest split into in-sample / out-of-sample segments; daily strategies use 4y + 1y; out-of-sample is judged relative to the market index.
- gate-result checks carry `metric`, naming what `actual` measures; the CLI prints every check's hint, not only failing ones.
- Reference runtime: `DONCHIAN_UPPER / MIDDLE / LOWER` now cover the N bars **before** the current one (turtle convention), so `close > DONCHIAN_UPPER` is a reachable breakout. Previously the band included the current bar and that condition could never hold.
- Reference runtime: Deflated Sharpe pass line 0.95 → 0.90 (documented in RUNTIME_API with the Sharpe it implies per number of trials).
- MCP server `alphaspec-mcp` (extra `alphaspec[mcp]`, stdio) exposing the offline reference tools and the runtime calls; no order tool.
- `alphaspec skill [--install DIR]`: the Agent Skill ships in the wheel, so installing it needs no checkout.
- Schema `$id` URLs: `https://openalpha-dev.github.io/alphaspec/schema/0.1/…`, served by GitHub Pages from this repository.
