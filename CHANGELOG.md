# Changelog

## Unreleased

- New Agent Skill `alphaspec-diagnose`: a step-by-step diagnosis of a running strategy from its evidence
  (pipeline → rejections → target vs actual holdings → execution cost → the signal last), with who can
  fix each finding. `alphaspec skill --install DIR` now installs every bundled skill; `alphaspec skill NAME`
  prints one.
- Reference runtime evidence (contract unchanged, all fields already in 0.4): `rejects[].hint` says which
  document field fixes a rejection or that only the user can; `targetDeviation` for factor and score
  strategies; arrival-price slippage for live orders and `paperVsLiveDiffBps`; `pipeline` stages
  `REBALANCE` (replaces `SIGNAL_EVALUATION` for factor strategies) and `SCORE_FEED`.
- CLI `evidence` prints hints, the live-vs-paper gap and target deviations.
- HTTPS works out of the box on Pythons with an empty trust store (python.org macOS installer): the client
  falls back to certifi's bundle (new dependency) when the system store has no certificates; `SSL_CERT_FILE` /
  `SSL_CERT_DIR` still take precedence.

## 0.4.1 — 2026-10-13

- Response language: the runtime agent API answers in English or Chinese (`?lang=` / `Accept-Language`,
  reply carries `Content-Language`). Codes, paths and metric keys are unchanged; only human-readable text
  is translated, including gate results stored before this release.
- Client `lang=` (default `$ALPHASPEC_LANG`, else the locale) sends `Accept-Language`; CLI `--lang` on every
  runtime command; MCP runtime tools take `lang`. Skill: reply in the user's language, decide by codes.
- Institution keys: an institution tenant issues one agent key that acts as an ordinary user of the tenant
  (`whoami.tenantType = INSTITUTION`); it can promote on every enabled market. Promoted strategies are always
  created disabled for both key kinds.
- Reference runtime: US equities (`us_equity`) now have the 4 + 1 years of daily history evaluation needs;
  JSON Schema messages are always in English regardless of the server locale.
- CLI: a `CERTIFICATE_VERIFY_FAILED` error (python.org builds on macOS ship without CA certificates) now prints how to fix it.

## 0.4.0 — 2026-10-12

- Contract 0.4 (`schema/0.4/`): factor-ranked strategies (`signalMode`, `factorBindings` with `factor` /
  `direction` / `weight`, new `ranking` block; `dsl` optional for `FACTOR_ONLY`), short rules
  (`dsl.shortEntry` / `dsl.shortExit`).
- Lint rules AS019 (short rules on a market that cannot be shorted), AS020 (short entry without a short
  exit), AS021 (factor bound twice), AS022 (topN covers the whole symbol list).
- MARKETS.md: trading rules by market (lots, settlement, price limits, short selling).
- SPEC §4b–4d: factor strategies, short rules, score series.
- Client / CLI / MCP: `factors`, `submit-scores`, `scores`, `evidence`.
- RUNTIME_API: factor evaluation window (2 + 1 years), score series, evidence, new `RUNTIME_*` codes.
- Examples 07 (quality + value, monthly) and 08 (long/short futures).
- `alphaspec validate` reads files holding a JSON array or JSON lines; `submit_scores` waits up to 300 s.
- Reference runtime: factor backtests now report in-sample / out-of-sample segments, accept an explicit
  symbol list and record which artifact they evaluated (all three were missing); factor + rule strategies
  gate on rank only; score uploads write in bulk (30k rows in seconds instead of minutes); evidence judges
  intraday strategies by their last evaluated bar.

## 0.3.0 — 2026-10-12

- Contract 0.3 (`schema/0.3/`): new `capabilities` document kind; `gate-result.tradeSettings` reports the exits,
  sizing and execution an evaluation actually used and every value the runtime defaulted. Artifacts are unchanged
  from 0.2.
- Validator accepts 0.1, 0.2 and 0.3; a kind that does not exist in the declared version is `UNSUPPORTED_KIND`.
- Client / CLI / MCP: `capabilities`, `strategies`, `export` (`export_strategy`), and `promote --target`
  (`target_strategy_id`) to publish a passing modification as a new version of an existing strategy.
- RUNTIME_API: the capabilities endpoint, submission checks (`RUNTIME_*` codes, no quota used), export and
  write-back. Skill: check capabilities before writing; export–edit–resubmit flow.
- Reference runtime: markets whose history does not cover the evaluation window are rejected at submission
  instead of being backtested on a silently shorter in-sample; symbols with no bars in the window are rejected.

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
