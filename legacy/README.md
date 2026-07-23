# Legacy Trading Engine V1

This directory is a recoverable archive of the original prototype. It is not
part of the active execution engine and must not be imported by new code.

Archived components include:

- funding-rate research and the B2B strategy;
- the original Binance Portfolio Margin SDK wrapper;
- the original order, risk, monitor, and websocket modules;
- operational scripts and historical tests;
- generated research data and result artifacts.

The active engine is rebuilt under `engine/` around immutable order intents,
exchange reconciliation, order state machines, and recoverable execution.

Do not run files under `legacy/tests_v1/` without reviewing them first. Several
are manual integration scripts that can call authenticated exchange or Discord
APIs and some can place real orders.

The original Portfolio Margin fund sweep is preserved at:

`legacy/binance_sdk_v1/binance_sdk.py::BinanceFuturesClient.auto_allocation`

It called `POST /papi/v1/auto-collection`. The active Binance adapter preserves
this behavior as `collect_futures_funds()`, but the app exposes it only as an
explicitly confirmed manual-recovery command. Binance UI Auto Aggregate
Balances is the normal collection path.
