# Runtime agent API (v1)

What a runtime exposes to agents and SDKs. The reference runtime (EasyQuant) implements it
under `/api/agent/v1`. Authenticate every request with an API key created in the runtime's
account page:

```
Authorization: Bearer eqk_<keyId>_<secret>
```

An API key can submit documents, run evaluations and read results. It **cannot** place
orders, start or stop strategies, operate accounts or manage keys; the runtime rejects it
everywhere outside this prefix.

Two kinds of key holders (`whoami.tenantType`):

- `CONSUMER` — an individual user's own key (created in their profile). Promotion follows the
  consumer product's rules (plan, indicator tiers, market whitelist).
- `INSTITUTION` — one agent for a whole institution tenant, issued by its administrators. The key
  acts as an ordinary user of that tenant: every enabled market can be promoted, no plan limits.

Either way a promoted strategy is created **disabled**; a person enables it (and binds an
account) in the runtime's UI.

**Response language.** Human-readable text (`message`, `hint`, `reason`, `error`, notes) follows
`?lang=en|zh`, else the `Accept-Language` header, else the runtime's default (Chinese for the reference
runtime); the reply carries `Content-Language`. Codes (`AS0xx`, `RUNTIME_*`, `GATE_*`), JSON paths,
metric keys and numbers never change with the language — branch on those, show the text to people.
The Python client sends `Accept-Language` from `Client(lang=...)` / `--lang` / `$ALPHASPEC_LANG`; the MCP
tools take a `lang` argument. Your own document text (names, descriptions) is never translated.

| Method & path | Success | Other responses |
|---|---|---|
| `GET /whoami` | 200 identity, `tenantType` (`CONSUMER` / `INSTITUTION`), `contractVersion` (latest) and `contractVersions` (all accepted), today's `evaluationQuota`, what the key can and cannot do | 401 invalid / revoked / expired key |
| `GET /capabilities` | 200 `capabilities` document (contract 0.3): what can be evaluated and promoted right now | |
| `POST /artifacts` — body: an `artifact` document | 201 `{artifactId, warnings}` | 422 `{issues}` (validator codes, plus `RUNTIME_*` codes below) · 400 unusable universe |
| `GET /artifacts` | 200 your submissions, newest first, with the latest verdict | |
| `POST /artifacts/{id}/evaluate` | 202 `{evaluationId, status}` | 422 `{issues}` the runtime cannot run it (not counted against the quota) · 429 daily evaluation quota used up · 503 queue full |
| `GET /artifacts/{id}/gate-result` | 200 `gate-result` document | 202 still running · 409 `{status: FAILED, error}` |
| `POST /artifacts/{id}/promote` — body optional: `{name, targetStrategyId}` | 201 `{strategyId, created, enabled: false}` · 200 if already promoted · 200 `{updated: true}` with `targetStrategyId` | 400 gate not passed, market not promotable, or target's market / universe differs · runtime product rules (pool size, names) apply as in its UI |
| `GET /strategies` | 200 your existing strategies | |
| `GET /strategies/{id}/evidence?from&to` | 200 `evidence` document (contract 0.4) for one of your strategies | 400 bad dates (max one year) |
| `GET /artifacts/{id}/evidence?from&to` | 200 `evidence` of the strategy the artifact was promoted to | 400 not promoted |
| `GET /factors` | 200 `{factors, scores}`: factors you can bind and your score series | |
| `POST /scores` — body: a `score` document or an array (same scoreName, market) | 201 `{scoreName, market, factor, dates, rows, warnings?}` | 422 `{issues}` |
| `GET /scores` | 200 your score series with date coverage | |
| `GET /strategies/{id}/alphaspec` | 200 `{document, issues}` — an artifact you can edit and resubmit | 422 `{document, issues}` exported but does not validate (e.g. a factor strategy before 0.4) |

## Capabilities

`GET /capabilities` is computed from the runtime's live market data and changes as data is added. For
every market it says whether the **daily** and **intraday** evaluation windows are covered by history
(and, when not, how much history exists versus how much the window needs), which indicator profiles an
evaluation can use there, whether a passing strategy can be promoted, and which index the out-of-sample
segment is compared against. Read it before writing a document; the Skill does.

The reference runtime's rules:

- A market is evaluable on a timeframe tier when its bars reach back to the start of that tier's
  in-sample window and are current. Today that is China A-shares, ETFs on daily bars; other markets
  have months, not years, of history and are declared not evaluable until it is backfilled.
- Indicator profiles: `core` everywhere; `ext.cn` on `cn_*`; `ext.data` on `cn_stock` (the fundamentals and
  index datasets cover A-shares only); `ext.l2` nowhere (it needs order-book data a bar backtest does not have).
- Out-of-sample benchmark: CSI 300 for `cn_stock`, `cn_etf`, `cn_convbond`; other markets are judged on an
  absolute Sharpe floor.
- Promotable markets: `cn_stock`, `cn_etf`, `cn_convbond`. Other evaluable markets return a gate result
  but cannot be promoted.

### Checks at submission

These run on `POST /artifacts` and again before `evaluate` enqueues. Errors reject the document (422)
and do not use the evaluation quota.

| code | severity | meaning |
|---|---|---|
| `RUNTIME_MARKET_UNSUPPORTED` | error | the runtime does not run this market |
| `RUNTIME_NO_HISTORY` | error | the market's bars do not cover the evaluation window for this timeframe (or `tick`) |
| `RUNTIME_PROFILE_UNAVAILABLE` | error | an indicator's profile is not usable in an evaluation on this market |
| `RUNTIME_UNIVERSE_MODE` | error | `ALL_MARKET` or no universe (until 0.4) |
| `RUNTIME_SYMBOL_NO_DATA` | error | a listed symbol has no bars in the window — almost always a typo |
| `RUNTIME_SYMBOL_PARTIAL_HISTORY` | warning | a symbol's history starts more than a month after the window does (its in-sample is shorter) |
| `RUNTIME_NOT_PROMOTABLE` | warning | evaluable, but a passing strategy cannot be promoted on this runtime |
| `RUNTIME_SIGNAL_MODE_UNSUPPORTED` | error | `FACTOR_OR_RULE` (the reference runtime supports `FACTOR_ONLY` and `FACTOR_AND_RULE`) |
| `RUNTIME_TIMEFRAME` | error | a factor strategy on a timeframe other than `1d` |
| `RUNTIME_SETTING_UNSUPPORTED` | error | `exits` / `sizing` / `execution` on a `FACTOR_ONLY` strategy (its backtest rebalances by `ranking` and would ignore them, while live stops would not) |
| `RUNTIME_UNIVERSE_TOO_SMALL` | error | a factor strategy on fewer than 5 listed symbols |
| `RUNTIME_FACTOR_UNKNOWN` / `RUNTIME_FACTOR_AMBIGUOUS` / `RUNTIME_FACTOR_LOCKED` | error | the factor is not in your library, exists both as a global and as your own factor (write `global:CODE` or `tenant:CODE`), or needs a higher plan |
| `RUNTIME_FACTOR_HISTORY` | error | a global factor or score series does not cover the factor evaluation window |

## Evaluation

The runtime picks the windows; the submitter cannot. The reference runtime runs **one**
continuous backtest and reports statistics for two segments of it, so positions carry
across the boundary and indicators warm up once:

| Strategy timeframe | In-sample | Out-of-sample |
|---|---|---|
| `1d`, `1w` | 4 years | the most recent 1 year |
| any strategy with `factorBindings` | 2 years | the most recent 1 year |
| intraday | 18 months | the most recent 6 months |

Performance figures are recomputed by the runtime (`computedBy: PLATFORM`) and annualised
on trading time (A-shares 242 days a year, Hong Kong 247, US 252; crypto 24×7). Checks beyond
the basic in-sample return / drawdown / Sharpe thresholds:

Each check names what its number is in `metric` (`excessReturnVsIndex`, `sharpe`,
`deflatedSharpeProbability`, ...). Read it rather than inferring from the code: the same check can
change measure.

- `GATE_OUT_OF_SAMPLE` — the out-of-sample segment must **beat the market index over the same
  period** (`metric: excessReturnVsIndex`, a fraction, threshold 0) and stay within the drawdown limit. A single
  year in a falling market makes absolute Sharpe look bad without saying anything about the
  strategy; relative performance does. Markets without a benchmark index in the runtime fall
  back to an absolute Sharpe floor, and the hint says so.
- `GATE_MULTIPLE_TESTING` — Deflated Sharpe on the in-sample segment using `producer.searchTrials`;
  the reference runtime passes it at 0.90. For a daily strategy (4-year in-sample) that is roughly an
  annualised Sharpe of 0.64 with 1 trial, 0.90 with 2, 1.24 with 5 and 1.43 with 10: every extra
  candidate you tried raises the bar. The gate only promotes to paper trading, which is the real
  out-of-sample test.
- `GATE_LOOKAHEAD` — the structural look-ahead checks passed at intake.

### Trade settings used by the evaluation

The evaluation backtest and the promoted strategy use the same `exits`, `sizing` and
`execution` (contract 0.2). Fields you leave out:

- `exits`: off. No stop is added for you.
- `execution.fillTiming`: `NEXT_OPEN`.
- `sizing`: **the reference runtime's account default, which is not a fixed fraction**: each
  entry buys as much as the account's per-order notional limit, the per-symbol exposure cap
  (60% of equity unless `riskProfile.maxSymbolExposurePct` says otherwise) and available cash
  allow. With a handful of symbols that concentrates the book in the first two or three
  signals. Always send a `sizing` block if position size matters to your result — it usually
  does.

The gate result (contract 0.3) reports what was actually used in `tradeSettings`: the effective
`exits`, `sizing` and `execution`, and under `defaults` every field the runtime filled in. When the
default sizing cannot be written as an AlphaSpec `sizing` block, `sizing` is absent and the `/sizing`
default says in words how positions were sized, with the limits that applied. `FACTOR_ONLY` strategies
have no `tradeSettings`: their holdings come from `ranking` alone.

"Out-of-sample" here means *chosen by the platform*, not *unseen at submission*: recent
market data is public. The only truly unseen period is the one after you submit, which is
what paper trading is for.

## Promotion

`promote` turns a gate-passed artifact into a paper-trading strategy in your runtime
account. It is created **disabled**; you start it yourself in the runtime's UI.

The reference runtime stores strategies with plain values only: on intake, `dsl.params` is
inlined (`{"ref": "x"}` becomes the value, or `{"const": value}` where an operand is expected)
and dropped. The promoted strategy therefore carries no `params`; your submitted document, with
its parameters, stays attached to the artifact. Trade settings are carried over unchanged and show
up in the runtime's strategy builder as its stop, position-size and fill-timing settings.

Factor-driven strategies use the shorter window because the reference runtime keeps three years of
factor scores (global factors start in 2023-09); a longer window would leave the early in-sample
period without scores and the book in cash.

### Score series

Upload one `score` document per date (batch them: an array of up to 800 documents per call). The
runtime stores the series under your account only; bind it in an artifact as `score:<scoreName>`.
Scores dated T are used from the next trading day. Re-uploading a date replaces it. For a promoted
strategy, keep uploading daily: the rebalance uses the latest scores and will not trade on stale ones.

### Evidence

`GET /strategies/{id}/evidence` reports, for a date range in the market's calendar: rejections grouped by
reason code (category from the risk rule that fired; the original message is kept), fill and reject
rates, slippage against the quote snapshot taken when the order was sent (`VS_ARRIVAL_PRICE`; positive =
cost), risk hits, up to 500 fills, and `pipeline` — whether the strategy is enabled and whether its
signals were evaluated on the last trading day. Paper and live orders are both included; `subject.mode`
is `LIVE` if any live order exists.

### Updating an existing strategy

`GET /strategies/{id}/alphaspec` exports one of your strategies (rules, trade settings, risk limits,
universe) as an artifact. Edit it, submit it as a new artifact (count it in `searchTrials`), evaluate,
and promote with `targetStrategyId` to publish it as a new version of that strategy. Market and
universe must stay the same; change those in the runtime's UI or promote to a new strategy instead.
From 0.4, factor strategies and long/short rule sets export too; factor bindings carry their source
(`global:`, `tenant:`, `score:`) so they resolve the same way on resubmission.

## Python

```python
from alphaspec import Client

c = Client()                       # ALPHASPEC_BASE_URL, ALPHASPEC_API_KEY
aid = c.submit(doc)["artifactId"]  # validates locally first
c.evaluate(aid)
gate = c.wait(aid)                 # polls until done
if gate["passed"]:
    c.promote(aid, name="my strategy")

c.capabilities()                   # what can be evaluated right now
doc, issues = c.export_strategy(438)
# ... edit doc, submit, evaluate ...
c.promote(new_aid, target_strategy_id=438)
```
