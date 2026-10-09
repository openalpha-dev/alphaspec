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
