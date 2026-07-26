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
├── persistence/  in-memory and SQLite order/event repositories
└── discord_notifier.py  outbound monitoring notifications

strategies/
└── funding_rate/ opportunity scanning, capital split and leg coordination

app/              generic environment, safety, runtime and dependency wiring
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
- Read-only Binance funding-rate scanner with positive-rate, annualized-return
  and 24-hour-liquidity filters plus executable Spot/perpetual entry basis.
- Local monitor entry point with hourly Top-10 console and responsive Discord
  PNG table reports.
- Incremental Spot hedge planning for every new perpetual partial fill.
- Binance Spot/USD-M public market data and Classic Portfolio Margin order,
  account, position, funding-income and user-stream boundaries. Margin-asset
  and USD-M orders use separate product gateways behind one engine-facing
  trading router.
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

Copy `.env.example` to `.env` and fill in the local values. The funding monitor
loads that file automatically. Never commit credentials.

```text
BINANCE_API_KEY
BINANCE_API_SECRET
BINANCE_ACCOUNT_MODE=CLASSIC_PORTFOLIO_MARGIN
CHOXR_LIVE_TRADING=false
DISCORD_WEBHOOK_URL=
CHOXR_DISCORD_NOTIFICATIONS=false
CHOXR_FUNDING_SCAN_INTERVAL_SECONDS=3600
CHOXR_FUNDING_MIN_ANNUALIZED_RATE=0.10
CHOXR_FUNDING_MIN_QUOTE_VOLUME_24H=3000000
CHOXR_FUNDING_TOP_N=10
CHOXR_FUNDING_CAPITAL=50
CHOXR_FUNDING_LEVERAGE=5
```

Constructing the application does not start a stream or send a request. Runtime
preflight and read-only smoke tests must pass before live trading is enabled.

Run one public, read-only funding scan:

```bash
python3 -m strategies.funding_rate.monitor --once
```

Run the continuous monitor:

```bash
python3 -m strategies.funding_rate.monitor
```

The monitor sends each successful report when Discord notifications are
explicitly enabled; `--once` needs no additional notification flag. It does not
construct private account, WebSocket or order-execution components and does not
require Binance API credentials. Continuous mode scans once per hour by default
and sends one complete Discord report after every successful scan.

Every successful scan also atomically replaces
`strategies/funding_rate/runtime/order_plan.json`. The plan stores only the
highest-ranked candidate that has executable Spot ask and perpetual bid prices,
then records a matched Spot BUY and perpetual SELL allocation. The current
planning baseline uses 50 USDT and 5x perpetual leverage, matching the legacy
strategy defaults. `READY` means the snapshot has a candidate and calculated
quantities; `NO_CANDIDATE` deliberately clears the selected-symbol list so a
future consumer cannot accidentally reuse the previous scan.

This JSON is a planning snapshot, not an executable order. Quantities have not
yet passed Binance symbol filters or risk validation, and this monitor never
submits them.

Preview each entry leg using fresh private account reads:

```bash
python3 -m strategies.funding_rate.order perp-maker
python3 -m strategies.funding_rate.order spot-taker --quantity 0.01
```

Both commands run Classic Portfolio Margin preflight, read current account
capital, symbol rules and order books, and require pre-trade risk approval.
Preview is the default and never submits. The perpetual preview additionally
requires a flat symbol and no existing perpetual order. It reports both the
current Binance leverage and `CHOXR_FUNDING_LEVERAGE`, but never changes account
configuration.

A real mutation requires all three explicit gates: `--submit`, a matching
`--confirm-symbol`, and `CHOXR_LIVE_TRADING=true`. Perpetual orders are
post-only SELL limits routed as Binance `GTX`. Immediately before a perpetual
submit, the order executor rechecks that the symbol is flat and has no open
order, changes that symbol's Binance USD-M initial leverage to the plan value
when needed, and reads it back before placing the order. A failed verification
stops the order. The manual Spot test is a MARKET BUY with `NO_SIDE_EFFECT`, so
it never auto-borrows.

Submitted orders are durably recorded in
`strategies/funding_rate/runtime/orders.sqlite3`. A hanging maker can be checked
or canceled with the same idempotent client order ID:

```bash
python3 -m strategies.funding_rate.order order-status \
  --client-order-id <CLIENT_ORDER_ID>
python3 -m strategies.funding_rate.order cancel-order \
  --client-order-id <CLIENT_ORDER_ID>
```

Cancellation is also preview-only unless `--submit`, `--confirm-symbol` and the
live-trading environment gate are all present.

The strategy now has one orchestration entry point. Its default mode performs a
fresh scan, replaces `order_plan.json`, runs private-account preflight, and
prints the Perp maker preview without mutating the exchange:

```bash
python3 -m strategies.funding_rate.main
```

To run the complete live entry and hedge loop, use the same three explicit
gates as the manual order harness:

```bash
CHOXR_LIVE_TRADING=true python3 -m strategies.funding_rate.main \
  --submit \
  --confirm-symbol BNBUSDT
```

When no active session exists, the strategy scans first, prepares the selected
Perp maker, connects the WebSocket, completes REST reconciliation, and only then
submits the maker. Every actual or partial Perp fill drives an idempotent Spot
MARKET hedge for the uncovered base-asset quantity. When an active session
already exists, the same command resumes it without scanning or submitting a
duplicate maker. Replayed events and unknown submissions reuse durable action
and client-order IDs. A local hedge-preparation failure cancels and reconciles
the remaining maker before pausing the session.

The same `orders.sqlite3` contains generic `orders` / `order_events` plus
strategy-specific `funding_sessions` / `funding_actions`. Fill-level commission
metadata is journaled so fees charged in the Spot base asset reduce confirmed
net Spot exposure. After a restart or WebSocket gap, the worker backfills
missing Spot trade fees through Binance's read-only fill history before making
another hedge decision. An active SQLite session takes precedence over an
expired JSON plan; pass `--execution-id` only when more than one active session
matches the confirmed symbol. If Binance fill history is briefly
eventually-consistent, the active worker retries it every five seconds and
remains `HEDGING` until fee-complete fills are available. Runtime JSON and
SQLite files remain ignored by Git.

The live process prints every operator-relevant step immediately to stdout.
Messages use stable prefixes such as:

```text
[FUNDING][WEBSOCKET] CONNECTED sequence=1
[FUNDING][RECONCILIATION] COMPLETE reconciled_orders=1 unresolved_orders=0
[FUNDING][EVENT] funding order identified role=MAKER kind=TRADE
[FUNDING][CALC] hedge result net_delta=-0.01 tradable=0.01
[FUNDING][DECISION] policy command command=SUBMIT_HEDGE quantity=0.01
[FUNDING][ORDER] Spot hedge submit returned state=FILLED
```

Startup, listen-key keepalive, reconnect, fill reconciliation, pending-action
recovery, ignored/no-action decisions, rejection recovery and shutdown are also
printed. Credentials, listen-key values, WebSocket URLs and webhook URLs are
never included.

## Still required before real capital

- Add a process-level restart integration test that kills the worker between
  Spot submission and local completion, then proves same-ID reconciliation
  against a simulated accepted exchange order. Unit coverage already verifies
  the same state transition.
- Add a bounded retry/report policy for unresolved UNKNOWN orders instead of
  leaving the strategy paused after the first failed recovery cycle.
- Complete the exit/unwind policy; current entry recovery cancels the remaining
  maker and pauses safely, but does not automatically flatten an already
  acquired two-leg position.
- Complete a manually approved, extremely small-notional production smoke test.

The repository is therefore structurally executable and offline-tested, but it
is not declared ready for unattended live trading.
