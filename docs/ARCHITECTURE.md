# CHOXR Architecture

CHOXR is organized around an exchange-agnostic order engine.  Binance is the
first adapter and positive-funding arbitrage is the first strategy; neither is
part of the engine's domain rules.

## Package ownership

```text
CHOXR/
├── engine/                 generic order domain, planning, risk and execution
│   ├── domain/
│   ├── ports/
│   ├── planning/
│   ├── risk/
│   └── execution/
├── adapters/               implementations of engine ports
│   ├── binance/
│   └── persistence/
├── strategies/
│   └── funding_rate/       opportunity scanning, capital and leg coordination
├── app/                    generic configuration, safety, runtime and wiring
├── tests/                  unit, contract, integration and guarded live tests
├── docs/
└── legacy/                 reference-only V1; production code must not import it
```

## Dependency rules

- `engine` never imports `adapters`, `strategies`, or `app`.
- `engine` contains no Binance endpoint, Binance payload, or funding-rate rule.
- `adapters` implement interfaces declared in `engine.ports`.
- The Binance adapter keeps Portfolio Margin asset-leg and USD-M order payloads
  in separate product gateways. An adapter-local router exposes one
  `TradingGateway` to the exchange-neutral execution service.
- `strategies` express trading intent through engine models and services; they
  never sign or send exchange requests directly.
- `app` is the composition root and may import every package to wire the process.
- `legacy` is not importable by production packages.

These rules are structural safety properties.  A new exchange should require a
new adapter, not changes to the order state machine or execution service.  A new
strategy should compose engine capabilities, not add strategy invariants to
generic order models.

## Responsibility boundary

| Package | Owns | Does not own |
|---|---|---|
| `engine.domain` | Order/instrument/account vocabulary and lifecycle invariants | API transport, strategy sequencing |
| `engine.planning` | Capital sizing, price/quantity calculation, symbol normalization | Opportunity selection |
| `engine.risk` | Pure fail-closed pre-trade account and exposure decisions | Funding-rate thresholds, exchange I/O |
| `engine.execution` | Submit, event application, cancellation, reconciliation, recovery | Which leg should trade first |
| `adapters.binance` | Signing, endpoints, payload parsing, Binance error semantics | Trading decisions |
| `strategies.funding_rate` | Read-only opportunity filtering and monitor, capital split, maker-perpetual/taker-Spot coordination, strategy unwind | Generic order lifecycle |
| `app` | Settings, shared dependency construction, process lifecycle | Domain calculations |

## Read-only funding monitor

`strategies.funding_rate.monitor` is intentionally separate from the private
account and execution runtime. It builds only public Binance Spot/USD-M
market-data clients and the optional outbound Discord notifier. The scan uses
public GET responses to select liquid positive-funding USDT perpetuals, then
asks the existing market-data gateway for executable Spot ask and perpetual bid
prices for the ranked candidates.

The monitor never constructs `PortfolioMarginApi`, an order-event stream, or an
`OrderExecutionService`. Its scanner logic is a pure function in
`strategies.funding_rate.scanner`; process timing, error backoff, Discord
PNG-table rendering and error throttling live in the monitor entry point.
Continuous mode uses one hourly interval for both scanning and successful
Discord reports. After each scan, the monitor selects the highest-ranked
candidate with executable prices, calls `FundingCapitalAllocator` with the Spot
ask and perpetual bid, and atomically replaces
`strategies/funding_rate/runtime/order_plan.json`. A no-candidate scan overwrites
the file with `NO_CANDIDATE` instead of leaving a stale symbol behind.

The JSON contains a decision snapshot and equal pre-rounding base quantities
for a Spot BUY and perpetual SELL. It is not an `OrderIntent`: exchange filter
rounding, pre-trade risk approval, private API access and submission remain
outside this monitor.

`strategies.funding_rate.order` is the explicit manual execution boundary for
testing each leg. It loads only a fresh `READY` plan, verifies the saved funding
timestamp, fetches current account/rules/book state, and composes the existing
maker-price, quantity-normalization, pre-trade-risk and execution services.
Perpetual preparation fails when the position is non-flat or another order is
open. The preview reports a leverage difference; the gated live submit updates
and reads back the symbol leverage before placing the maker. Spot preparation
accepts an explicit test quantity no larger than the allocation. Preview is the
default; live submission remains behind both CLI confirmation and
`LiveTradingGuard`.

This manual harness deliberately does not treat a direct Spot test as a
perpetual hedge. `strategies.funding_rate.main` owns the automatic strategy
sequence: fresh scan, maker preparation, WebSocket synchronization, maker
submission, committed fill consumption, and Spot hedging. Generic process
mechanics remain in `app.runtime`; the strategy imports and composes them rather
than putting Funding-specific sequencing in `app/`.

## Funding execution components

Funding-specific economics stay inside the strategy package without leaking
order sequence into the generic engine:

- `allocation.py` computes matched pre-filter base quantities from capital,
  Spot price, perpetual price and leverage.
- `hedge.py` is a pure calculator for confirmed net Spot, pending reservations,
  uncovered delta, tradable quantity and dust.
- `execution_policy.py` decides whether to submit a hedge, cancel/reconcile the
  maker, mark the session open, pause or enter recovery.
- `session.py` defines durable funding sessions and idempotent actions.
- `worker.py` reloads committed order truth, invokes the calculator/policy and
  dispatches persisted actions with stable client IDs. Before restart recovery
  it also backfills missing Spot commission events through the read-only fill
  gateway, so a WebSocket gap cannot overstate net Spot exposure. Fee-incomplete
  terminal fills remain `HEDGING` and are retried periodically instead of being
  marked `OPEN`.

The first policy is perpetual-maker / Spot-taker. A future Spot-maker or
simultaneous policy can replace it without changing the calculator, engine or
Binance adapter.

## Runtime safety defaults

- Live trading is disabled unless `CHOXR_LIVE_TRADING=true` is set explicitly.
- API fund collection is additionally an explicitly confirmed manual-recovery
  action. Binance UI Auto Aggregate Balances is the normal collection path.
- API credentials come from environment variables and are never stored in the
  repository.
- Side-effect request timeouts produce an unknown outcome and are reconciled by
  client order ID before any resend.
- An authoritative venue error produces a terminal `REJECTED` transition with
  the rejection reason; only indeterminate delivery outcomes become `UNKNOWN`.
- WebSocket events are the normal order-state input; REST polling is a bounded
  recovery mechanism, not the engine's main control loop.
- Binance stream lifecycle is separate from order events. A connection is not
  considered synchronized until REST reconciliation finishes without
  unresolved orders.
- REST reconciliation and WebSocket events are serialized per client order ID;
  unrelated orders do not share one global execution lock.
- Restart recovery reconciles order snapshots first, then REST fill history,
  and only then resumes durable funding actions.
- SQLite production wiring atomically commits each normalized event with its
  materialized order snapshot, so a crash cannot persist only half a transition.
- Latency-sensitive execution paths use `ExecutionTimingTrace` backed by a
  monotonic nanosecond clock. It measures local end-to-end spans and
  milestone gaps without depending on wall-clock or exchange clock offsets.
- Critical hedge sequencing does not wait for optional price enrichment. If a
  terminal MARKET response omits the average price, an explicit read-only
  reconciliation can enrich that terminal snapshot later without changing its
  state or cumulative fill.
- Price, quantity, balances and rates use `Decimal` end to end.

The offline funding vertical slice calls `engine.risk` before each submit. The
next production milestone must make that approval a required app-level submit
contract, so a caller cannot accidentally bypass it while live trading is
enabled.
