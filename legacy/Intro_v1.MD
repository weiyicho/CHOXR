# Trading Engine — Technical Architecture Document

## Overview

This document defines the technical architecture and development conventions of the **Trading Engine Framework**. The framework is designed for modularity, scalability, and maintainability in algorithmic trading systems, supporting both cryptocurrency and traditional financial instruments.

It provides a clear separation of concerns between strategy logic, risk control, monitoring, and exchange interfaces.

---

## Directory Structure

```text
project_root/
├── src/
│   └── exchange1_sdk.py                # Exchange 1 SDK wrapper (REST/WebSocket adapters, unified API abstraction)
|── websocket/
│   └── websocket for xxx exchange
|
├── config/
│   ├── general_config/                 # Global environment configuration (API keys, credentials, network settings)
│   │   └── api_key.json
│   ├── strategy1_config/               # Strategy-specific configuration files
│   │   └── risk_order_config.json      # Risk and order-related parameters
│
├── risk/
│   └── risks.py                         # Centralized risk control module (exposure limits, validation, leverage rules)
│── order/
│   └── orders.py
├── monitor/
│   └── discord.py                      # Monitoring and alerting interface (Discord webhook notifications)
│
├── util/
│   └── utils.py                        # Shared helper utilities (logging, math ops, time utils, JSON/YAML parser)
│
└── strategy/
    └── strategy_1/                     # Implementation of Strategy 1 (signal generation, order logic, orchestration)
```

---

## Architectural Principles

1. **Layered Architecture**
   The system is structured in logical layers — *Config → Strategy → Risk → Exchange SDK → Monitor* — ensuring predictable data flow and dependency isolation.

2. **Loose Coupling & High Cohesion**
   Each module encapsulates a single responsibility and communicates through well-defined interfaces.

3. **Configuration-Driven Execution**
   All runtime parameters (e.g., API keys, risk thresholds, strategy parameters) are stored in YAML/JSON files.

4. **Dependency Directionality**
   Data flows top-down: **Strategy → Risk → Exchange SDK**, preventing cyclic dependencies.

5. **Observability**
   Trading and system events are logged, monitored, and optionally sent to external channels (Discord, Slack, Telegram).

6. **Extensibility & Testability**
   New exchanges and strategies can be added modularly; all core components are unit-testable and mockable.

---

## System Data Flow

```text
          ┌────────────────────┐
          │   Configuration    │
          │ (YAML / JSON)      │
          └────────┬───────────┘
                   │
                   ▼
           ┌──────────────┐
           │   Strategy    │
           │ (signal gen,  │
           │  orchestration)│
           └────────┬──────┘
                    │
                    ▼
           ┌──────────────┐
           │     Risk      │
           │ (validation,  │
           │  limits, caps)│
           └────────┬──────┘
                    │
                    ▼
           ┌──────────────┐
           │   Exchange    │
           │    SDK(s)     │
           │ (order exec,  │
           │  market data) │
           └────────┬──────┘
                    │
                    ▼
           ┌──────────────┐
           │   Monitor     │
           │ (alerts, logs)│
           └──────────────┘
```

---

## Module Responsibilities

| Module        | Responsibility                  |
| ------------- | ------------------------------- | 
| **src/**      | Exchange interface layer        | 
| **config/**   | Configuration management        | 
| **risk/**     | Trade and position validation   | 
| **monitor/**  | Alerting and event reporting    | 
| **util/**     | Shared internal utilities       | 
| **strategy/** | Trading logic and orchestration |

---

## Development Workflow

### 1. Implement a New Exchange SDK

* Create `src/exchangeX_sdk.py`
* Implement standardized interfaces:

  ```python
  get_order_book(symbol: str)
  place_order(symbol: str, side: str, qty: float, price: float)
  fetch_balance()
  ```
* Ensure all SDKs return unified data schemas for consistency.


### 2. develop Monitoring

* ensure it can send position info to discord
* ensure user can use discord to manage position if needed

### 3. risk
* develop risk calculation and monitor
* ensure it handles order status, position status, re-balance, adl, and hedge

### 4. order
* develop the price calculation for limit order 
* develop 回傳order status
* develop 掛單 多久要再掛一次


### 5. websocket
* develop websocket or snapshot to keep getting position symbol data

### 6. Test & Validate
* Mock SDK responses for simulation testing
* Validate strategy and risk workflows using synthetic data
* Integrate with CI/CD pipelines for regression testing

---

## Configuration Guidelines

* All configuration files must follow a consistent schema:
* Use environment variable overrides for production secrets.
* Keep sensitive credentials outside the repository.

---

## Testing Standards

* All new modules must include unit tests under `/tests/`
* Target minimum 80% coverage on core modules
* Mock exchange APIs for deterministic tests

---

## Future Extensions

* **Multi-Exchange Routing** — Abstracted order router for arbitrage/mirror execution.
* **Async Event Engine** — Replace polling loops with an `asyncio`-driven message pipeline.
* **Backtesting Framework** — Offline simulation engine with PnL and metrics output.
* **Metrics & Logging Service** — Integrate with Prometheus and Grafana.
* **State Persistence** — Save and restore open positions and session state.

---

## Summary

This trading engine is built for **robustness**, **maintainability**, and **scalability**. Each module can be independently developed, tested, or replaced, making the system ideal for iterative strategy research and live deployment.


**Some class or file has been created, don't change their main logic, but you can modify or delete function if needed or create new class if you think it is too complicated**

**binance sdk is really important, the function inside is already been tested, but if you think function name is not good, feel free to change it**
