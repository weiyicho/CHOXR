# Trading Engine Testing Guide

## Quick Start

### 1. Setup Configuration
```bash
# Setup API Keys
python3 tests/setup_api_config.py

# Setup Discord Webhook (Optional but recommended)
python3 tests/setup_discord_webhook.py
```
Follow the interactive prompts to enter your credentials.

### 2. Run Core Tests
```bash
# Test Binance SDK Connectivity
python3 tests/test_binance_sdk.py

# Test Monitoring System
python3 tests/test_monitoring_system.py
```

### 3. Advanced Testing
```bash
# Test Margin Trading Logic
python3 tests/test_margin_orders.py

# Test Risk Management Integration
python3 tests/test_risk_manager_integration.py

# Test Real Trading (DOGE/USDT - Small amounts)
python3 tests/test_dogeusdt_trading.py
```

## What Gets Tested

### Core Infrastructure
- ✅ Exchange information & Connectivity
- ✅ Account authentication & Balances
- ✅ Discord Webhook integration (`test_discord_realtime.py`)
- ✅ Position Monitoring (`test_position_monitor.py`)

### Trading Logic
- ✅ Limit Orders (`test_limit_orders.py`)
- ✅ Market Orders
- ✅ Margin Trading (`test_margin_orders.py`)
- ✅ Order Management & Tracking (`test_order_manager.py`)

### Risk Management
- ✅ Position Limits
- ✅ Leverage Checks
- ✅ Exposure Monitoring
- ✅ Risk Integration (`test_risk_manager_integration.py`)

## Configuration

The API configuration is stored in `config/api.json`:

```json
{
  "binance": {
    "api_key": "your_api_key",
    "api_secret": "your_api_secret",
    "testnet": false,
    "timeout": 30,
    "base_url": "https://api.binance.com",
    "futures_url": "https://fapi.binance.com"
  },
  "bybit": {
    "api_key": "YOUR_BYBIT_API_KEY_HERE",
    "api_secret": "YOUR_BYBIT_API_SECRET_HERE",
    "testnet": true,
    "timeout": 30,
    "base_url": "https://api-testnet.bybit.com"
  }
}
```

## Security Notes

- 🔒 Use testnet for development (set `"testnet": true`)
- 🔒 Never commit real API keys to version control
- 🔒 The `.gitignore` file excludes `config/api.json` from being committed
- 🔒 API secrets are hidden during input
- 💰 Order testing limited to maximum $6 per order for safety
- 🐕 Uses DOGE/USDT pair for better precision and lower costs
- 🔄 Immediate buy/sell cycle to minimize risk
- 📊 Real-time P&L tracking for trade analysis

## Troubleshooting

### Common Issues

1. **Import Errors**: Make sure you're in the correct directory
2. **Authentication Errors**: Verify your API keys are correct
3. **Network Errors**: Check your internet connection and Binance API status
4. **Insufficient Balance**: Some tests may fail if you don't have enough balance

### Getting Binance Testnet API Keys

1. Go to [Binance Testnet](https://testnet.binance.vision/)
2. Sign up for a testnet account
3. Generate API keys in the API Management section
4. Use these testnet keys for safe testing

## Test Results

The test script provides detailed feedback on:
- ✅ Which functions work correctly
- ❌ Which functions failed and why
- 📊 Performance metrics
- 🔍 Error details for debugging
