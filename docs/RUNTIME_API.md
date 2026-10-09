# Runtime agent API (v1)

What a runtime exposes to agents and SDKs. The reference runtime (EasyQuant) implements it
under `/api/agent/v1`. Authenticate every request with an API key created in the runtime's
account page:

```
Authorization: Bearer eqk_<keyId>_<secret>
```

An API key can submit documents, run evaluations and read results. It **cannot** place
orders, operate accounts or manage keys; the runtime rejects it everywhere outside this
prefix.

| Method & path | Success | Other responses |
|---|---|---|
| `GET /whoami` | 200 identity, contract version, what the key can and cannot do | 401 invalid / revoked / expired key |
| `POST /artifacts` — body: an `artifact` document | 201 `{artifactId, warnings}` | 422 `{issues}` (same codes as the local validator) · 400 unusable universe |
| `GET /artifacts` | 200 your submissions, newest first, with the latest verdict | |
| `POST /artifacts/{id}/evaluate` | 202 `{evaluationId, status}` | 429 daily evaluation quota used up · 503 queue full |
| `GET /artifacts/{id}/gate-result` | 200 `gate-result` document | 202 still running · 409 `{status: FAILED, error}` |
| `POST /artifacts/{id}/promote` — body optional: `{name}` | 201 `{strategyId, created, enabled: false}` · 200 if already promoted | 400 gate not passed · runtime product rules (market, pool size, names) apply as in its UI |

## Evaluation

The runtime picks the windows; the submitter cannot. The reference runtime runs **one**
continuous backtest and reports statistics for two segments of it, so positions carry
across the boundary and indicators warm up once:

| Strategy timeframe | In-sample | Out-of-sample |
|---|---|---|
| `1d`, `1w` | 4 years | the most recent 1 year |
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

"Out-of-sample" here means *chosen by the platform*, not *unseen at submission*: recent
market data is public. The only truly unseen period is the one after you submit, which is
what paper trading is for.

## Promotion

`promote` turns a gate-passed artifact into a paper-trading strategy in your runtime
account. It is created **disabled**; you start it yourself in the runtime's UI.

The reference runtime stores strategies with plain values only: on intake, `dsl.params` is
inlined (`{"ref": "x"}` becomes the value, or `{"const": value}` where an operand is expected)
and dropped. The promoted strategy therefore carries no `params`; your submitted document, with
its parameters, stays attached to the artifact.

## Python

```python
from alphaspec import Client

c = Client()                       # ALPHASPEC_BASE_URL, ALPHASPEC_API_KEY
aid = c.submit(doc)["artifactId"]  # validates locally first
c.evaluate(aid)
gate = c.wait(aid)                 # polls until done
if gate["passed"]:
    c.promote(aid, name="my strategy")
```
