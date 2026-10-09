# Changelog

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
