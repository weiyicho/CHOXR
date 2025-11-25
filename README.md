# CHOXR Trading Engine V1

A robust, modular quantitative trading engine designed for crypto futures markets. This system features a layered architecture separating strategy logic, risk management, order execution, and exchange connectivity.

## 🌟 Features

- **Multi-Exchange Support**: Unified interface for Binance and Bybit.
- **Risk Management**: Built-in portfolio margin checks, position limits, and exposure monitoring.
- **Order Execution**: Smart order routing with tick size abstraction and limit price optimization.
- **Real-time Monitoring**: Discord integration for trade alerts, position updates, and P&L tracking.
- **Modular Strategy**: Plug-and-play architecture for developing and testing different strategies.

## 📂 Project Structure

```
Trading_EngineV1/
├── config/                 # Configuration files (API keys, strategy params)
├── monitor/                # Discord notifications and monitoring system
├── order/                  # Order execution logic and price calculations
├── risk/                   # Risk management and validation modules
├── src/                    # Exchange SDKs (Binance, Bybit)
├── strategy/               # Strategy implementations (e.g., strategy1)
├── tests/                  # Unit and integration tests
└── util/                   # Utility functions and helpers
```

## 🚀 Getting Started

### Prerequisites

- Python 3.8+
- pip

### Installation

1. **Clone the repository** (if applicable) or navigate to the project root.
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Setup Configuration**:
   - Copy `config/api.json.example` to `config/api.json` (if it exists, otherwise create it).
   - Enter your API keys (use Testnet keys for development!).

### Running the Strategy

To run the default strategy (`strategy1`):

```bash
python strategy/strategy1/main.py
```

### Running Tests

Validate the system before deploying:

```bash
# Run all tests
pytest tests/

# Run specific test for order engine
pytest tests/test_order_engine_example.py
```

## 🛡️ Safety First

- **Testnet Default**: The system is configured to use Testnet by default.
- **Position Limits**: Hardcoded safety limits prevent excessive exposure.
- **Stop Loss**: Ensure your strategies implement stop-loss logic.

## 🤝 Contributing

1. Create a new branch (`git checkout -b feat/new-feature`).
2. Commit your changes (`git commit -m 'feat: add new feature'`).
3. Push to the branch (`git push origin feat/new-feature`).
4. Open a Pull Request.
