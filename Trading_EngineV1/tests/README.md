# Testing Framework

This directory contains all testing files and results for the Trading Engine.

## 📁 Directory Structure

```
tests/
├── README.md                    # This file
├── setup_api_config.py         # API configuration setup script
├── test_binance_sdk.py         # Binance SDK functionality tests
├── test_limit_orders.py        # Limit order price calculation tests
├── test_order_manager.py       # OrderManager unit tests
├── test_real_trading.py        # Real trading integration tests
├── results/                    # Test results and logs
│   ├── trading_test_results_*.json
│   └── ...
└── __init__.py                 # Package initialization
```

## 🧪 Test Files

### **Core Testing Scripts**

- **`test_binance_sdk.py`** - Tests Binance API connectivity and functions
- **`test_order_manager.py`** - Unit tests for price calculation functions
- **`test_limit_orders.py`** - Integration tests for limit order placement
- **`test_real_trading.py`** - Real trading tests with actual order execution

### **Configuration**

- **`setup_api_config.py`** - Interactive API key setup script

## 🚀 Running Tests

### **From Trading_EngineV1 directory:**

```bash
# Test Binance SDK
python3 tests/test_binance_sdk.py

# Test OrderManager functions
python3 tests/test_order_manager.py

# Test limit order calculations
python3 tests/test_limit_orders.py

# Real trading tests (requires API keys)
python3 tests/test_real_trading.py
```

### **From tests directory:**

```bash
cd tests

# Test Binance SDK
python3 test_binance_sdk.py

# Test OrderManager functions
python3 test_order_manager.py

# Test limit order calculations
python3 test_limit_orders.py

# Real trading tests (requires API keys)
python3 test_real_trading.py
```

## 📊 Test Results

All test results are automatically saved to `tests/results/` with timestamps:
- `trading_test_results_YYYYMMDD_HHMMSS.json`

## ⚙️ Setup

1. **Configure API keys:**
   ```bash
   python3 tests/setup_api_config.py
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## 🔒 Safety Features

- **Testnet by default** - All tests use Binance testnet
- **Position limits** - $50 total, $6 per order for DOGE/USDT
- **Automatic cleanup** - Orders are automatically closed after execution
- **Comprehensive logging** - All operations are logged with timestamps

## 📈 Performance Analysis

The real trading tests include detailed timing analysis:
- Order book analysis time
- Price calculation time
- Order placement time
- Order fill time
- Total cycle time
- P&L analysis
