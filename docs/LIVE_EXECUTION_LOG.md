# Live Execution Log

This file records explicitly authorized live smoke tests. It must never contain
API credentials or signatures.

## 2026-07-22 — DOGEUSDT timed market round trip

Purpose:

- Verify that the Classic Portfolio Margin adapter can submit a USD-M order.
- Verify immediate `reduceOnly` close sequencing.
- Establish a first local execution-latency baseline.

Account and safety context:

- Account mode: `PM_2` / Classic Portfolio Margin.
- Position mode: `ONE_WAY`.
- Preflight DOGEUSDT position: `0`.
- Quantity: `69 DOGE`.
- Preflight best bid/ask: `0.073380 / 0.073390 USDT`.
- Approximate notional: `5.063910 USDT`.
- Binance minimum notional: `5 USDT`.

Orders:

| Leg | Client order ID | Exchange order ID | Result | Quantity | Average price |
|---|---|---:|---|---:|---:|
| Open `MARKET BUY` | `cx-doge-b-260721161523` | `100752526155` | `FILLED` | `69` | `0.073390` |
| Close `MARKET SELL` | `cx-doge-s-260721161523` | `100752526167` | `FILLED` | `69` | `0.073380` |

The close order used `reduceOnly=true`. Binance recorded the buy fill at
`2026-07-22T00:15:23.164+08:00` and the sell fill at
`2026-07-22T00:15:23.218+08:00`. The final DOGEUSDT position was verified as
zero.

Observed latency:

| Measurement | Milliseconds |
|---|---:|
| Buy submit REST round trip | `62.901625` |
| Buy fill confirmation | `62.915500` |
| Buy confirmation to sell-submit start | `0.005541` |
| Sell submit REST round trip | `55.618417` |
| Sell fill confirmation | `55.653209` |
| Binance fill-to-fill time | `54.000000` |
| Sell confirmation to flat-position confirmation | `94.521166` |
| Total locally observed round trip | `213.096708` |

Economics:

- Buy quote quantity: `5.063910 USDT`.
- Sell quote quantity: `5.063220 USDT`.
- Realized price loss: `0.00068999 USDT`.
- Buy taker commission: `0.00253195 USDT`.
- Sell taker commission: `0.00253161 USDT`.
- Total commission: `0.00506356 USDT`.
- Net result after reported commissions: approximately `-0.00575355 USDT`.

Interpretation and limitations:

- Timing uses `ExecutionTimingTrace` with a monotonic nanosecond clock.
- The `0.005541 ms` gap measures local code time after the REST buy response
  confirmed the fill and before the sell submit call began.
- This is not yet the production funding-arbitrage hedge-latency measurement.
  That measurement must start when the process receives a perpetual maker-fill
  WebSocket event and end at Spot hedge submission, acknowledgement and fill.
- The initial MARKET order response reported a zero average price even though
  the order was filled. A later read-only order reconciliation supplied the
  correct average price. Terminal-order metadata enrichment was added without
  delaying the close leg.

Local audit database: `runtime/live_orders.sqlite3`.
