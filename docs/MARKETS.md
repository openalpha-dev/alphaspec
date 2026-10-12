# Market registry

Market ids are lower snake case. A runtime declares which ids it supports and rejects the
rest. New ids are added here by pull request.

| id | Instruments | Calendar / time zone | Symbol form | Notes |
|---|---|---|---|---|
| `cn_stock` | China A-shares | SSE/SZSE, Asia/Shanghai | `600000.SH`, `000001.SZ`, `830799.BJ` | T+1, daily price limits, 100-share lots |
| `cn_etf` | China ETFs | SSE/SZSE, Asia/Shanghai | `510300.SH` | |
| `cn_convbond` | China convertible bonds | SSE/SZSE, Asia/Shanghai | `113039.SH` | quantity in units of 10 bonds |
| `cn_future` | China futures | CFFEX/SHFE/DCE/CZCE/INE/GFEX, Asia/Shanghai | `RB2505.SHF` | night sessions belong to the next trading day |
| `cn_option` | China options | SSE/SZSE/CFFEX, Asia/Shanghai | `10008001.SH` | contract multiplier |
| `hk_stock` | Hong Kong equities | HKEX, Asia/Hong_Kong | `00700.HK` | board lots vary per stock; half-day sessions |
| `us_equity` | US equities and ETFs | NYSE/Nasdaq, America/New_York | `AAPL` | |
| `crypto_spot` | crypto spot pairs | 24/7, UTC | `BTCUSDT` | |

## Trading rules by market

What a document can assume about each market. A runtime enforces these in backtests and in its
paper and live accounts; contract rules (e.g. AS019) refer to this table.

| id | Lot size | Settlement | Price limits | Short selling |
|---|---|---|---|---|
| `cn_stock` | 100 shares (STAR Market 200, then 1) | T+1 | ±10% (ST ±5%, ChiNext / STAR ±20%, BSE ±30%) | no |
| `cn_etf` | 100 units | T+1 (cross-border / bond ETFs T+0) | ±10% | no |
| `cn_convbond` | 10 bonds | T+0 | ±20% | no |
| `cn_future` | 1 contract × multiplier | T+0 | per contract, daily | yes |
| `cn_option` | 1 contract × multiplier | T+0 | per contract | yes (writing) |
| `hk_stock` | per-stock board lot | T+0 | none (VCM bands) | runtime-dependent |
| `us_equity` | 1 share | T+0 | none (LULD bands) | runtime-dependent |
| `crypto_spot` | exchange minimum | T+0 | none | no (spot) |

Futures symbols are specific contracts (`RB2701.SHF`); a runtime may roll an open position to the
next contract before expiry, and must say so in its evidence. Continuous-contract series are not
part of the contract yet.

## Indicator profiles

Every catalog entry has a profile:

| profile | Meaning | Allowed on |
|---|---|---|
| `core` | computable from OHLCV bars | any market |
| `ext.cn` | encodes China exchange rules: price-limit streaks, sealed boards, call auction, main-force money flow | `cn_*` |
| `ext.l2` | needs order-book or trade-by-trade data | markets where the runtime's data source provides it |
| `ext.data` | needs a runtime dataset beyond bars (fundamentals, index series) | where the runtime provides it |

Market rules are scoped, not deleted. A new market brings its own rules the same way:
as a profile, with lint rules stating where it applies.
