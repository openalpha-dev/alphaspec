---
name: alphaspec-diagnose
description: Diagnose a strategy that is already running on an AlphaSpec runtime — why it did not trade, did not buy what its model scored, trades less than expected, or does worse in paper/live than in its backtest — from the runtime's execution evidence (pipeline, rejections with fix hints, target vs actual holdings, slippage, fills). Use when asked "why didn't my strategy trade / buy X", "what went wrong yesterday", "are my model scores being used", "why is it underperforming", or to health-check a promoted strategy. For writing or changing a strategy document, use the alphaspec skill.
---

# Diagnosing a running strategy

**Evidence first, strategy logic last.** Most "my strategy stopped working" cases are a pipeline or execution problem, not an alpha problem. Change the document only when the evidence points at a field in it, and never conclude "the signal is bad" before steps 1–4 are clean.

Everything here comes from the runtime's public evidence API. The same `alphaspec` package as the alphaspec skill; needs `ALPHASPEC_BASE_URL` and `ALPHASPEC_API_KEY`. With the MCP server instead of a shell, use `list_strategies`, `get_evidence`, `export_strategy` and `gate_result`.

## Step 0 — which strategy, which window

```bash
alphaspec strategies                                        # ids, market, running or stopped
alphaspec evidence <strategyId> --from 2026-10-01 --to 2026-10-14 --json
alphaspec evidence --artifact <artifactId> --json           # the strategy an artifact was promoted to
```

- Default window: the 30 days before `--to`. For "what happened yesterday", use a window of that one day. Dates are market-local (`window.timezone`); at most one year per call.
- Ask the runtime for the user's language (`--lang en|zh`, MCP `lang`), but decide by **codes** (`stage`, `status`, `code`, `reason`), which never change with the language.
- Read the JSON, not the summary. Field meanings: `alphaspec schema evidence` and `alphaspec docs runtime` (section Evidence).

## Step 1 — did it run? (`pipeline`)

Read the stages in order and **stop at the first one that is not `OK`**; later sections are consequences of it.

| Stage | Not OK means | Who fixes it |
|---|---|---|
| `STRATEGY_ENABLED` `ABSENT` | The strategy is stopped. Promoted strategies start stopped. Nothing else in the document matters until it runs. | The user starts it in the runtime's app. |
| `SIGNAL_EVALUATION` `DEGRADED` / `ABSENT` | Rule strategy: signals were not evaluated on the last trading day (or never). | Runtime side (data feed, scheduler). Report the violation text to the user; the document cannot fix it. |
| `REBALANCE` `DEGRADED`, violation `…skipped: REBALANCE_WAITING_INPUTS` | Factor / score strategy: the day's data was not in when the rebalance ran. | Runtime side; usually resolves the next day. |
| `… REBALANCE_NO_FACTOR_SCORES` | No symbol in the universe had a score that day. | Check `SCORE_FEED`; check that the factor covers the universe (`alphaspec factors`). |
| `… REBALANCE_NO_SYMBOLS` / `REBALANCE_NO_FACTOR_REFS` | Empty universe / factor bindings that do not resolve. | Document: `universe`, `factorBindings`. |
| `… REBALANCE_NO_NAV` | No account value, or no FX rate to convert it. | The user, in the runtime's app. |
| `REBALANCE` `DEGRADED`, violation `…ended PARTIAL_FAILED / BLOCKED / EXPIRED` | The rebalance ran but its orders did not complete. | Go to steps 2 and 3. |
| `REBALANCE` `ABSENT` | It never rebalanced (new strategy, or not started on a rebalance day yet). | Wait for the next rebalance day, or check `STRATEGY_ENABLED`. |
| `SCORE_FEED` `DEGRADED` / `ABSENT` | A `score:<name>` series stopped updating. The runtime does not trade on stale scores, so the strategy **silently stops rebalancing**. The most common failure for model-driven strategies. | The score producer: upload the missing dates (`alphaspec submit-scores`), then fix whatever job stopped uploading. |

A `REBALANCE` stage that is `OK` with an old `at` is not a failure: rebalances only happen on rebalance days.

## Step 2 — what was blocked? (`rejects`, `riskHits`)

- Sort `rejects` by `count`. `category` says where it was stopped: `UNIVERSE`, `RISK`, `BROKER`, `MARKET_DATA`, `STRATEGY`.
- **Follow `hint`.** It names the document field that fixes the rejection, or says that only the user or waiting can (account circuit breaker, stale data, broker-side cash or permissions). A code without a `hint` has no known remedy: quote `message` and do not invent one.
- `riskHits` with `blocking: false` are warnings, not causes.
- Weigh counts against `executionQuality.orders`: one rejection out of two orders is not a pattern; the same code on most orders is.

## Step 3 — did the holdings match the target? (`targetDeviation`, factor and score strategies)

Compares the latest finished rebalance in the window with what was actually bought and sold. Weights are fractions of the account value at planning time, and both sides use the same reference price, so a deviation means **quantity not achieved**, not a price move. Absent field = no finished rebalance in the window (or a rule strategy).

| `reason` | Typical cause | What to do |
|---|---|---|
| `LOT_ROUNDING` | The target is smaller than one lot (A shares: 100 shares) at that price. | Fewer holdings (`ranking.topN`), avoid very high-priced names, or a larger account. |
| `PRICE_LIMIT` | The name was limit-up (buy) or limit-down (sell): untradable that day. | If the model keeps picking such names, that is a model issue: its top scores sit on stocks that are often untradable at the next open (e.g. names closing at the limit). Score them lower or `null`; risk limits have nothing to do with it. |
| `SETTLEMENT_RULE` | T+1: bought today, cannot sell today; or shares already held by another sell order. | Market rule. Nothing to fix unless the strategy relies on same-day exits. |
| `RISK_REJECT` | A risk limit stopped the order. | The matching entry in `rejects` and its `hint`. |
| `NOT_IN_UNIVERSE` | The model scored a symbol outside the strategy's universe. | Score only universe members, or widen `universe`. |
| `NO_PRICE` / `HALTED` | No price at planning time, or suspended. | Send `null` scores for halted names. |
| `MIN_FEE_FLOOR` | The trade was too small to be worth the minimum commission. | Fewer, larger positions. |
| `OTHER` | Cash short at execution, opening price outside the allowed range, a partial immediate fill. | Read `rejects` messages for the same symbols and day. |

## Step 4 — what did execution cost? (`executionQuality`, `caliber`)

- Read `caliber` first: `slippageBasis` (`VS_ARRIVAL_PRICE` = the quote when the order was sent), `feeIncluded` (fees are separate, in `ledger[].fee`), `currency`.
- `avgSlippageBps` / `p95SlippageBps`: positive = cost. To see what it does to returns: annual drag ≈ 2 × average slippage × annual turnover (round trips). Compare with what the backtest assumed (`alphaspec result <artifactId>` lists the trade settings used); if live costs are higher, the backtest overstated returns by that much.
- `paperVsLiveDiffBps` (live orders only): live fill vs the price the paper simulator would have given the same order; positive = live was worse. Limit orders can only fill at or better than their limit, so this mostly measures price improvement. **Orders that never filled live do not appear here**; look at `fillRatePct`.
- Low `fillRatePct` with few rejects = immediate orders finding no liquidity: narrow `universe` to more liquid names or reduce `sizing`.

## Step 5 — only now, the strategy itself

If the pipeline is `OK`, rejections are rare, deviations are small and costs are near the backtest's assumptions, but results are still poor, then it is the signal.

- Compare with the gate result's out-of-sample numbers (`alphaspec result <artifactId>`), not with in-sample ones.
- Do not judge from fewer than about 20 round trips or a few weeks: say the sample is too small.
- A change is a new artifact: export, edit, submit, evaluate, promote with `--target` (the alphaspec skill). Count it in `producer.searchTrials`. Do not tune to fit the last month.

## Reporting to the user

1. **Verdict, one line**: stopped / not running when it should / running but blocked / running and executing as intended.
2. **Evidence**: the codes and numbers, each with its unit and caliber (`targetWeight 0.20 → actualWeight 0.00, RISK_REJECT`, `avgSlippageBps 12.4 vs arrival price`).
3. **Cause**, and **who can fix it**: a document field, the user in the runtime's app, the runtime operator, or nobody (market rule, wait).
4. **Proposed change**, only when the fix is in the document; name the field and the risk being given up.

## Never

- Diagnose from fills or P&L alone without reading `pipeline` first.
- Loosen every risk limit to make rejections go away. One rejection code, one targeted change, and say what protection it removes.
- Submit, evaluate or promote without the user asking: evaluations count against a daily quota, and promotion changes what runs.
- State numbers the evidence did not return, or translate a code into a guess.
- Assume evidence sees everything: it does not show other strategies on the same account, manual orders, or the broker's own account state.
