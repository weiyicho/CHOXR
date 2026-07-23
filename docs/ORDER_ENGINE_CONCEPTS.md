# 下單機觀念地圖

這份文件不是策略教學。策略決定要交易什麼與各腿的關係；通用下單機只負責
把一個已核准、參數完整的訂單安全地送出，並持續保存它的真實生命週期。

一句話版本：

> 保存不可變的交易意圖，透過 gateway 執行一次明確動作，接收交易所事件，
> 並在斷線或 timeout 時以原本的 client order ID 對帳。

## 先建立這個 schema

```text
Strategy
   |  選市場、方向、預算、各腿關係
   v
PlanningRequest + fresh account/book/rules
   |
   v
OrderPlanner ---> immutable OrderIntent
                       |
                       v
              OrderExecutionService
                 |             ^
                 v             |
          TradingGateway   OrderEvent
                 |             |
                 +---- Exchange+

WebSocket 是正常事件來源；REST reconciliation 是 timeout、斷線與重啟後的
恢復路徑。Funding 的雙腿協調只存在 `strategies/funding_rate/`，不在 engine。
```

正 funding 是第一個使用者，它在策略層定義：

```text
Spot base quantity > 0
USD-M perpetual base quantity < 0
Spot quantity + perpetual quantity ~= 0
```

雙腿交易不是 atomic transaction。CHOXR 的進場順序是 perpetual maker 先掛；
每次收到新的 perpetual 累積成交量，就建立相同增量的 Spot market BUY。
Spot hedge 失敗時的 retry、unwind 與 manual halt 是 funding 策略 recovery，
不是所有下單系統都必須知道的規則。

## 六個一定要懂的觀念

### 1. State、event、action 不一樣

- `PARTIALLY_FILLED` 是 state。
- `TRADE` 是 event。
- `submit_order()` 是 action。
- `CANCEL_REQUESTED` 不等於 `CANCELED`。
- HTTP timeout 代表結果未知，不代表下單失敗。

現在的實作入口：`engine/domain/order_state_machine.py`。

### 2. ExecType 與 OrderStatus 不一樣

FIX 將「這次為何收到訊息」與「處理後的訂單狀態」分開。Binance Spot
`executionReport` 也分成 `x`（execution type）與 `X`（order status）。

數量也要分開：

- requested quantity；
- last fill quantity；
- cumulative filled quantity；
- leaves quantity。

曝險與持倉永遠使用 cumulative actual fills，不能使用原始委託量。

### 3. Idempotency 是 intent identity

每張訂單在送出前就要有穩定的 `client_order_id`。相同 ID 代表相同且不可
變的 intent；timeout 後要用原 ID 查單，不能換新 ID 再送一次。

```text
SUBMITTING
    | timeout
    v
UNKNOWN
    | query by client_order_id
    v
RECONCILED exchange state
```

### 4. Retry 與 reconciliation 不一樣

- validation / balance / symbol error：不要盲目 retry；
- rate limit 或暫時性 transport error：有限次 backoff + jitter；
- side-effect 結果不明：先 reconciliation；
- 未分類錯誤：保守進入 recovery。

只有 execution layer 擁有 retry policy；底層 gateway 不應暗中重複送出
具有副作用的下單 request。

### 5. Compensation 不是 rollback

如果 Spot 實際成交 `0.73 ETH`、Perpetual 被拒絕，可以：

1. forward recovery：補上 `0.73 ETH` 的 Futures short；
2. compensation：賣回實際成交的 `0.73 ETH` Spot；
3. manual halt：保存狀態並等待人工處理。

Compensation 本身也是一張新訂單，也會 timeout、partial fill 或失敗，所以
它同樣需要完整 lifecycle。

### 6. Strategy orchestration 與單張訂單 execution 必須分開

`OrderExecutionService` 不知道下一張單是 Spot、perpetual、Binance 或其他
交易所；它只處理一張 `OrderIntent`。策略 coordinator 觀察已成交量後，才決定
是否產生下一張 intent。這讓 funding 的 maker-first 規則不會污染 engine。

現在的實作入口：

- `engine/domain/order.py`
- `engine/planning/planner.py`
- `engine/execution/order_service.py`
- `engine/ports/trading_gateway.py`
- `strategies/funding_rate/entry_coordinator.py`

## V1 invariants

1. 策略不能直接組 Binance payload 或呼叫 Binance API；它只能建立 engine intent
   並透過 execution service 執行。
2. Binance 是 actual orders、fills、balances、positions 的最終依據。
3. Client order ID 建立後，intent parameters 不可改變。
4. UNKNOWN order 未釐清前，不得建立可能重複曝險的新 order。
5. Cancel pending 期間仍可能收到 fills。
6. WebSocket 斷線時停止開新倉，但仍用 REST 管理及對帳既有部位。
7. Funding coordinator 的 perpetual 累積成交量與已 hedge 數量必須持久化；
   replay 相同成交事件不能產生第二張 Spot 單。
8. 重啟後先 reconciliation，不能先讓策略開新倉。
9. 所有 transition、intent、exchange ID、fill 與 recovery action 都要可稽核。
10. Binance UI 的 Auto Aggregate Balances 是正常資金歸集機制；API fund
    collection 只保留為需要 live flag 與人工確認的 recovery command，不能由
    單張訂單、startup 或 settlement event 自動呼叫。

## 建議學習順序

前一版把可靠性工程放得太前面。它解釋的是「下單出問題後怎麼辦」，不是
「一張單怎麼下」。在進入狀態機前，先用目前帳戶實際會走的 Classic
Portfolio Margin API 學會單腿訂單。

### 第一階段：一張單到底怎麼運作

先讀 [Binance Portfolio Margin Trade API](https://developers.binance.com/en/docs/catalog/advanced-trading-derivatives-trading-portfolio-margin/api/rest-api/trade)，只看以下六個操作：

1. New Margin Order：`POST /papi/v1/margin/order`
2. Query Margin Order：`GET /papi/v1/margin/order`
3. Cancel Margin Order：`DELETE /papi/v1/margin/order`
4. New UM Order：`POST /papi/v1/um/order`
5. Query UM Order：`GET /papi/v1/um/order`
6. Cancel UM Order：`DELETE /papi/v1/um/order`

讀的時候只回答這些具體問題：

- `MARKET` 與 `LIMIT` 差在哪裡？
- `quantity`、`price`、`timeInForce` 各控制什麼？
- `BUY` / `SELL` 在 Margin 與 UM Futures 各自改變哪個部位？
- `orderId` 與 `clientOrderId` 有什麼不同？
- request 被接受、訂單成交、訂單完全成交，是否是同一件事？
- 一張單要怎麼查詢與撤銷？

正 funding 開倉可以先想成兩個完全獨立的 request：

```text
Margin asset leg
POST /papi/v1/margin/order
BUY ETHUSDT MARKET quantity=0.01
sideEffectType=NO_SIDE_EFFECT

UM perpetual hedge leg
POST /papi/v1/um/order
SELL ETHUSDT MARKET quantity=0.01
positionSide=BOTH
```

這裡先不談 retry，也先不假設兩張單會同時成功。目標只是看懂每個參數、
response，以及如何查到最後的 `status` 與 `executedQty`。

接著讀 Binance symbol filters，理解 `tickSize`、`stepSize`、最小數量與最小
名目金額。這些規則決定一張訂單能不能被交易所接受。

### 第二階段：訂單送出後會經歷什麼

1. [Binance Spot User Data Stream](https://developers.binance.com/en/docs/products/spot/user-data-stream)
   — 觀察 NEW、PARTIALLY_FILLED、FILLED、CANCELED、REJECTED 事件與成交數量。
2. [FIX Order State Changes](https://www.fixtrading.org/online-specification/order-state-changes/)
   — 補齊 partial fill、cancel race、reject 等完整 lifecycle。
3. [Microsoft State Machine Workflows](https://learn.microsoft.com/en-us/dotnet/framework/windows-workflow-foundation/state-machine-workflows)
   — 最後才用 state、event、transition、guard、action 把 lifecycle 寫成程式。

### 第三階段：系統壞掉時，如何避免多下一張單

1. [AWS Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/)
   — timeout 後為什麼要先用原 `clientOrderId` 查單。
2. [AWS Timeouts, retries, and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/)
   — 哪一層可以 retry，以及 retry 次數與延遲如何受限。
3. [Microsoft Compensating Transaction](https://learn.microsoft.com/en-us/azure/architecture/patterns/compensating-transaction)
   — 雙腿只成交一腿時，如何補 hedge、unwind 或 manual halt。

## 三個階段讀完後應該能回答

- 一張 `MARKET BUY` request 被接受，是否代表已經完全成交？
- Margin `BUY` 與 UM `SELL` 各自建立了什麼部位？
- 如何用 `clientOrderId` 查單、如何撤單、如何確認實際成交量？
- `x=TRADE, X=PARTIALLY_FILLED` 各自代表什麼？
- Cancel request 送出後又成交 `0.2`，這筆成交要不要計入 position？
- Submit timeout 且沒有 WebSocket event，為何不能換 ID 再送一次？
- Spot 成交 `0.73 ETH`、Futures rejected，三種 recovery 路徑是什麼？
- 哪些證據足以讓 position 從 `RECOVERING` 進入 `HEDGED`？
