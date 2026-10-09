# Lint rules

Schema validation tells you a document is well-formed. These rules tell you it will do
what you think. Every rule here exists because a runtime accepted the mistake, ran it,
and produced wrong results without raising an error.

Severity: **error** = a compliant runtime must reject the document.
**warning** = accepted, but almost certainly not what the author meant.

Each rule has at least one case in `conformance/cases/` named after it.

## Artifact rules

### AS001
**Indicator reference does not resolve** · error

A rule refers to `{"ind": "alias"}` but `dsl.indicators` has no such alias (`close` is
built in). The reference runtime compiles the node to nothing; the strategy runs, never
enters, and reports nothing wrong.

### AS002
**Parameter reference does not resolve** · error

`{"ref": "name"}` where `dsl.params` has no `name`.

### AS003
**Higher-timeframe indicator uses LIVE bars (look-ahead)** · error

An indicator on a timeframe above the primary one with `barPolicy: "LIVE"`. Live, that
reads the still-forming bar, which is legitimate. In a backtest, that bar has already
finished: a daily bar read at 10:00 contains the 15:00 close. Backtest results look
excellent and cannot be reproduced. Use `CLOSED` (the default): only completed
higher-timeframe bars are visible.

### AS004
**Indicator references form a cycle** · error

`a` uses `b` and `b` uses `a`.

### AS005
**Unknown indicator type** · error

The type is not in `catalog/indicators.json`.

### AS006
**Unknown indicator parameter** · warning

A key the indicator type does not take, e.g. `length` on `EMA` (which takes `period`).
The runtime ignores it and uses the default, so the strategy runs with a different
parameter than the one written.

### AS007
**Indicator not available on this market** · error

An indicator from the `ext.cn` profile (price-limit streaks, sealed limit-up boards,
call auction, main-force money flow) on a market outside `cn_*`. These encode China
exchange rules and have no meaning elsewhere.

### AS008
**timeframe/barPolicy ignored for primary-series-only indicator** · warning

Some indicators (listed in the catalog under `primarySeriesOnly`) always compute on the
primary series with their own daily aggregation. A `timeframe` or `barPolicy` on them
has no effect.

### AS009
**Indicator timeframe finer than primary timeframe** · error

A 5m indicator on a 1d strategy. A finer series cannot be derived from coarser bars.

### AS010
**tick timeframe cannot be bar-backtested** · warning

`tick` means "evaluate on every market-data frame". That timing dimension does not
exist in bar history, so a bar backtest of a tick strategy would be a different strategy.

### AS011
**Symbol missing venue suffix** · error

On `cn_*` and `hk_*` markets the code is only unique together with its venue:
`600000.SH`, `000001.SZ`, `00700.HK`. A bare code is stored and looked up as a different
series, so data silently splits in two.

### AS012
**searchTrials required for generated output** · error

`producer.kind` is `AI_AGENT` or `FACTOR_MINER` and `searchTrials` is missing. Anyone who
tries a thousand variants will find one with a great backtest. The number of trials is
the input to correcting for that (deflated Sharpe); without it the gate cannot tell
search luck from signal.

### AS013
**No exit rule** · warning

Positions close only through stop rules or rebalancing.

### AS014
**Intraday indicator on a too-coarse primary timeframe** · error

Indicators such as `DAY_HIGH` or `MINUTES_SINCE_OPEN` measure within a session. On a
daily strategy there is nothing inside the bar to measure.

### AS015
**Indicator defined but never used** · warning

Usually a leftover from editing, or an entry/exit rule that references the wrong alias.

## Score rules

### AS101
**Duplicate symbol in submission** · error

### AS102
**Every score is null** · error

### AS103
**asOf is in the future** · error

`asOf` is the last trading day whose information the scores used. A future date means
the producer's clock or calendar is wrong, and every downstream timing is suspect.

### AS104
**Zeros look like missing values** · warning

At least 20% of scores are exactly `0` and none are `null`. If `0` means "no data",
send `null`: in a cross-sectional ranking `0` is a real position, and those symbols
will be bought or sold as if the model had an opinion about them.

### AS105
**Weights sum above 1** · error

Target weights must sum to at most 1; the remainder is cash. Leverage is a runtime and
account decision, not a field in the submission.
