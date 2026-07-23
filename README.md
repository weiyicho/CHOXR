# CHOXR Order Engine

CHOXR is an exchange-agnostic order planning and execution engine. Binance
Classic Portfolio Margin is the first exchange adapter, and positive-funding
arbitrage is the first strategy using the engine.

The active code keeps four responsibilities separate:

```text
Strategy   decides what position to build and how its legs relate
Planning   calculates capital, maker price, quantity and exchange-rule rounding
Execution  owns one order's lifecycle, idempotency and reconciliation
Adapter    signs and translates requests for one concrete exchange
```

## Active structure

```text
engine/
├── domain/       generic instruments, accounts, orders, events and state machine
├── ports/        trading, market-data, account, stream and repository interfaces
├── planning/     account-aware sizing, OBI/OBIV maker pricing and normalization
├── risk/         mandatory fail-closed pre-trade decisions
└── execution/    submit, cancel, event handling and bounded reconciliation

adapters/
├── binance/      Classic Portfolio Margin REST/WebSocket adapter
└── persistence/  in-memory and SQLite order/event repositories

strategies/
└── funding_rate/ capital split and maker-perpetual/taker-Spot coordination

app/              environment settings, safety guard and dependency wiring
legacy/           original prototype; active code never imports it
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for ownership and dependency
rules.

Explicitly authorized live smoke-test results are recorded in
[`docs/LIVE_EXECUTION_LOG.md`](docs/LIVE_EXECUTION_LOG.md).

## Implemented vertical slice

- Exchange-neutral `OrderIntent`, `OrderRecord`, order events and lifecycle.
- Durable SQLite order state and append-only normalized event journal.
- Atomic SQLite event + order-snapshot transition commits.
- Unknown submission outcomes reconcile by the same client order ID; they are
  not blindly resubmitted.
- Authoritative exchange submission errors are atomically persisted as
  terminal `REJECTED` orders with their rejection reason.
- Real Portfolio Margin WebSocket production with listen-key keepalive,
  reconnect lifecycle signals and REST reconciliation after connection gaps.
- Runtime readiness remains false until reconciliation completes without
  unresolved orders.
- Monotonic execution timing traces measure REST round trips, fill-confirmation
  latency, inter-leg gaps and total orchestration latency.
- Account-aware capital sizing from a fresh `AccountSnapshot`.
- Order-book maker pricing with OBI/OBIV and configurable depth/pressure.
- Decimal tick-size, step-size, min-quantity and min-notional enforcement.
- Generic exact-quantity market-order planning for taker hedges.
- Funding allocation that matches Spot and perpetual notional.
- Incremental Spot hedge planning for every new perpetual partial fill.
- Binance Spot/USD-M public market data and Classic Portfolio Margin order,
  account, position, funding-income and user-stream boundaries.
- Live submit/cancel is disabled unless `CHOXR_LIVE_TRADING=true` is explicitly
  set in the environment.
- Binance API fund collection is not automatic because Auto Aggregate Balances
  is enabled; the fallback requires the live flag plus explicit manual recovery
  confirmation.

## Tests

All default tests are offline. They use deterministic data and mocked HTTP
responses; they do not send real Binance requests.

```bash
python3 -m pytest
```

The suite is organized as:

```text
tests/unit/              domain, planning, risk, execution, persistence, strategy
tests/contract/binance/ mocked Binance transport, endpoint and payload contracts
tests/integration/       offline vertical-slice simulations
```

## Configuration

Copy `.env.example` values into your local environment or `.env` loader. Never
commit credentials.

```text
BINANCE_API_KEY
BINANCE_API_SECRET
BINANCE_ACCOUNT_MODE=CLASSIC_PORTFOLIO_MARGIN
CHOXR_LIVE_TRADING=false
```

Constructing the application does not start a stream or send a request. Runtime
preflight and read-only smoke tests must pass before live trading is enabled.

## Still required before real capital

- Make the production app submit entry point require a fresh, approved
  pre-trade risk decision instead of relying on the strategy caller to invoke
  the existing fail-closed risk check.
- Add a durable exchange-neutral order-progress outbox so WebSocket fills and
  fills recovered by REST reconciliation drive the same downstream outcome.
- Persist funding-strategy hedge progress and wire that progress outbox to the
  funding entry controller; the current coordinator is still called manually
  in the offline vertical slice.
- Add restart integration tests covering a fill recovered during a WebSocket
  gap, its Spot hedge, and delayed event replay without duplicate hedging.
- Add a bounded retry/report policy for unresolved UNKNOWN orders instead of
  requiring a process restart after the first failed recovery cycle.
- Add explicit recovery policy for Spot hedge rejection and emergency unwind.
- Complete a manually approved, extremely small-notional production smoke test.

The repository is therefore structurally executable and offline-tested, but it
is not declared ready for unattended live trading.
