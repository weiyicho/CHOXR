# Binance SDK Testing Guide

## Quick Start

### 1. Setup API Configuration
```bash
python3 setup_api_config.py
```
Follow the interactive prompts to enter your Binance API credentials.

### 2. Test the SDK
```bash
python3 test_binance_sdk.py
```

## What Gets Tested

### Public Endpoints (No Authentication Required)
- ✅ Exchange information
- ✅ Order book data
- ✅ Recent trades
- ✅ Candlestick data (klines)
- ✅ Spot prices

### Private Endpoints (Authentication Required)
- ✅ Account information
- ✅ Account balances
- ✅ Current positions
- ✅ Open orders

### Order Operations
- ✅ Buy/Sell cycle testing with DOGE (max $6 value)
- ✅ Market orders for immediate execution
- ✅ Automatic precision handling
- ✅ Real-time P&L calculation
- ✅ Order status tracking

### Risk Management
- ✅ Change leverage
- ✅ Trade history

## Configuration

The API configuration is stored in `config/api.json`:

```json
{
  "binance": {
    "api_key": "your_api_key",
    "api_secret": "your_api_secret",
    "testnet": true,
    "timeout": 30
  }
}
```

## Security Notes

- 🔒 Use testnet API keys for development
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
