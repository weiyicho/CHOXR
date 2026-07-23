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
│   └── funding_rate/       Spot/perpetual selection and leg coordination
├── app/                    configuration and dependency wiring
├── tests/                  unit, contract, integration and guarded live tests
├── docs/
└── legacy/                 reference-only V1; production code must not import it
```

## Dependency rules

- `engine` never imports `adapters`, `strategies`, or `app`.
- `engine` contains no Binance endpoint, Binance payload, or funding-rate rule.
- `adapters` implement interfaces declared in `engine.ports`.
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
| `strategies.funding_rate` | Capital split, maker-perpetual/taker-Spot coordination, strategy unwind | Generic order lifecycle |
| `app` | Settings, dependency construction, process lifecycle | Domain calculations |

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
