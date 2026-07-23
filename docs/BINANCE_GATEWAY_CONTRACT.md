# Binance Gateway Contract

本文件定義通用 CHOXR engine 的第一個 Binance adapter。它不是 endpoint 大全；
funding arbitrage 只是第一個呼叫這些能力的外部策略。

本 repo 已驗證的實際帳戶模式記錄在
[`BINANCE_ACCOUNT_PROFILE.md`](BINANCE_ACCOUNT_PROFILE.md)，目前是
`CLASSIC_PORTFOLIO_MARGIN`。

## 第一個設定必須是 account mode

三種模式不可混用，也不可在錯誤後自動 fallback 到另一套 API：

| Mode | Spot／現貨資產腿 | USD-M perpetual 腿 | Account management |
|---|---|---|---|
| `REGULAR` | `/api/v3/*` | `/fapi/*` | Spot `/api` + UM `/fapi` |
| `CLASSIC_PORTFOLIO_MARGIN` | `/papi/v1/margin/*`，`NO_SIDE_EFFECT` | `/papi/v1/um/*` | `/papi/v1/*` |
| `PORTFOLIO_MARGIN_PRO` | 交易面使用 `/papi` 家族 | 交易面使用 `/papi` 家族 | `/sapi/v1/portfolio/*` |

啟動時必須用 read-only account endpoint 驗證設定的 mode。不能因為某個 request
失敗，就依次猜 `/fapi`、`/papi` 或 `/sapi`。

PM Pro 的 trade plane 判斷來自目前官方 modular SDK 的分工：Pro package 只有
`/sapi` account／asset management，完整交易模組在 Portfolio Margin package。
在接上真實帳戶前仍須用 read-only account checks 驗證實際權限。

舊 repo 的 private base URL 固定為 PAPI，所以它實際上只接近 Classic
Portfolio Margin，並不是通用 Binance Futures client。

## V1 execution contract

每條腿都需要：

```text
place order
query by exchange order ID or original client order ID
cancel order
list open orders
list fills/trades
read account balance and position
subscribe to account/order events
```

共同要求：

- quantity、price 與 balance 全程使用 `Decimal`，送 API 時轉 decimal string；
- 每個 intent 的 client order ID 必填且不可重用；
- 使用兩邊各自的 `exchangeInfo` filters 做 quantization 與 validation；
- server time offset、`recvWindow` 與 `-1021` recovery 必須集中管理；
- gateway 不暗中 retry side-effect requests；
- side-effect request 的網路 timeout、`-1006`、`-1007`，以及帶有官方
  `Unknown error, please check...` 訊息的 503 才是 unknown outcome，先查單；
- Binance 已回覆的驗證、權限、rate-limit 或參數錯誤是確定拒絕：gateway
  轉成 `OrderSubmissionRejected`，execution service 以同一 client order ID
  原子寫入 `REJECTED` 與拒絕原因，不可留在 `SUBMITTING`；
- `Service Unavailable`、`Internal error` 與 `-1008` 是確定失敗，只能由上層
  bounded retry policy 決定是否重送，transport 本身不重送；
- 保存 rate-limit headers 與 `Retry-After`；429 backoff、418／403 halt。

## Regular Spot 最小 API

| 用途 | API |
|---|---|
| Server time | `GET /api/v3/time` |
| Symbol rules | `GET /api/v3/exchangeInfo` |
| Order validation | `POST /api/v3/order/test` |
| Place/query/cancel | `POST/GET/DELETE /api/v3/order` |
| Open orders | `GET /api/v3/openOrders` |
| Symbol kill switch | `DELETE /api/v3/openOrders` |
| Account | `GET /api/v3/account` |
| Fills | `GET /api/v3/myTrades` |

Spot User Data Stream 要使用 WebSocket API
`userDataStream.subscribe.signature`。舊 listen-key REST methods 已停止提供，
不能再用舊文章的方式建立新版 Spot stream。

## Regular USD-M Futures 最小 API

| 用途 | API |
|---|---|
| Server time／rules | `GET /fapi/v1/time`, `GET /fapi/v1/exchangeInfo` |
| Place/query/cancel | `POST/GET/DELETE /fapi/v1/order` |
| Open orders／fills | `GET /fapi/v1/openOrders`, `GET /fapi/v1/userTrades` |
| Position／account | `GET /fapi/v3/positionRisk`, `/account`, `/balance` |
| Position config | `GET /fapi/v1/accountConfig`, `/symbolConfig` |
| Leverage | `GET /fapi/v1/leverageBracket`, `POST /fapi/v1/leverage` |
| Funding earned | `GET /fapi/v1/income`, filter `FUNDING_FEE` |

## Classic Portfolio Margin 最小 API

| 用途 | API |
|---|---|
| Margin asset leg | `/papi/v1/margin/order`, `/openOrders`, `/myTrades` |
| UM perpetual leg | `/papi/v1/um/order`, `/openOrders`, `/userTrades` |
| UM position | `/papi/v1/um/positionRisk` |
| Account truth | `/papi/v1/account`, `/papi/v1/balance` |
| UM config／leverage | `/papi/v1/um/accountConfig`, `/symbolConfig`, `/leverageBracket`, `/leverage` |
| Funding earned | `/papi/v1/um/income`, filter `FUNDING_FEE` |

舊 SDK 的 `/papi/v1/userTrades` 路徑不正確；UM 必須是
`/papi/v1/um/userTrades`。

## One-way mode 是 V1 invariant

V1 啟動時查詢 position mode，若為 Hedge mode 就拒絕啟動，不自動切換：

- One-way 進場 short：`SELL`；
- One-way 出場：`BUY` + `reduceOnly=true`；
- Hedge mode 必須帶 `positionSide=SHORT`，而且不能傳 `reduceOnly`。

Leverage 只改變 margin requirement，不改變 delta-neutral 的 base quantity。

## Fund Auto-collection

這就是舊 `auto_allocation()` 真正在做的事。它不是「啟用自動配置」，也不屬於
單張訂單 execution core；它是具有副作用的 account maintenance command：

| Account mode | Official route | 語意 |
|---|---|---|
| Classic PM | `POST https://papi.binance.com/papi/v1/auto-collection` | Portfolio Margin fund collection |
| PM Pro | `POST https://api.binance.com/sapi/v1/portfolio/auto-collection` | Futures assets → Margin account |

兩個 route 都不會收集 BNB，且 rolling hour 最多 500 次；Classic PM weight
750，PM Pro weight 1500。因此不能在每筆 order、每次 reconciliation 或每次
程式啟動時呼叫。

目前帳戶已在 Binance UI 開啟 **Auto Aggregate Balances**。正常路徑是：

```text
Binance Auto Aggregate Balances
      -> CHOXR read-only account reconciliation / monitoring
```

`LiveAccountGuard.collect_futures_funds()` 只保留給人工判斷 Auto Aggregate
異常後的 recovery。它需要同時開啟 live mutation flag 並傳入明確人工確認；
不得從 order、funding settlement、reconciliation 或 startup 自動呼叫。人工
執行後仍須重新讀 balance 對帳。

## Event 與 reconciliation

Spot `executionReport` 與 Futures `ORDER_TRADE_UPDATE` 都要先轉成內部
`OrderEvent`，再交給 state machine。WebSocket 是低延遲增量，不是永久帳本。

Classic Portfolio Margin user stream 使用：

```text
POST /papi/v1/listenKey
             |
             v
wss://fstream.binance.com/pm/ws/<listenKey>
```

- listen key 在 60 分鐘內未 keepalive 會過期，runtime 每 45 分鐘更新一次；
- WebSocket 連線最長 24 小時，runtime 在 23 小時 50 分重新連線，但沿用仍有效的
  listen key，避免不必要的事件缺口；
- 收到 `listenKeyExpired` 或 keepalive 回傳 `-1125` 才重建 listen key；
- 其他網路斷線沿用同一 listen key，使用最高 30 秒的 bounded backoff；
- account、balance、risk 等非訂單事件不進入 order queue；目前只接受
  `executionReport` 與 `ORDER_TRADE_UPDATE`；
- 同步 REST listen-key、event handling 與 reconciliation 都由 worker thread 執行，
  不阻塞 WebSocket receive／ping event loop；
- runtime 消費獨立 lifecycle signal；`RECONNECTING` 立刻清除 synchronized
  readiness，首次 `CONNECTED` 與每次 `RECONNECTED` 都完成 REST reconciliation
  後才重新標記 ready；
- 同一 `client_order_id` 的 REST/WS mutation 由 per-order lock 序列化，不同訂單
  不共用一把全域鎖；較舊 cumulative TRADE 會留下 journal 但不倒退本地狀態；
- SQLite production wiring 使用 atomic persistence，在同一 transaction 內寫入
  order event 與 materialized order snapshot。

以下情況必須 REST reconciliation；startup 與 reconnect 已由 runtime 自動接好：

- 程式啟動；
- user stream 斷線／到期；
- submit 或 cancel timeout；
- 本地狀態與 event 衝突；
- 進入或離開 recovery 前。

查單要支援 original client order ID。不要只查 open order，因為 filled 或
canceled order 已不在 open orders 裡。

## Testnet 現實

- Spot Testnet 支援 `/api/*`，不支援 `/sapi/*`；
- USD-M Futures Testnet 支援 `/fapi/*`；
- 官方目前沒有文件化的 PAPI／PM Pro testnet。

因此 PM 路徑要先通過 FakeGateway 與 contract tests，再做 production
read-only smoke test，最後才可能以極小 notional 驗證；目前 active code 不會
送出真實訂單。

## 官方來源

- [Binance Spot API docs](https://github.com/binance/binance-spot-api-docs)
- [Spot REST API](https://developers.binance.com/en/docs/products/spot/rest-api)
- [Spot User Data Stream](https://developers.binance.com/en/docs/products/spot/user-data-stream)
- [USD-M Trade API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade)
- [USD-M Account API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/account)
- [Classic Portfolio Margin Account API](https://developers.binance.com/en/docs/catalog/advanced-trading-derivatives-trading-portfolio-margin/api/rest-api/account)
- [Classic Portfolio Margin Trade API](https://developers.binance.com/en/docs/catalog/advanced-trading-derivatives-trading-portfolio-margin/api/rest-api/trade)
- [Portfolio Margin Pro Account API](https://developers.binance.com/en/docs/catalog/advanced-trading-derivatives-trading-portfolio-margin-pro/api/rest-api/account)
- [Official modular Python connector](https://github.com/binance/binance-connector-python)
