"""
Pytest configuration and fixtures for Trading Engine tests.
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch

from src.binance_sdk import BinanceFuturesClient


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    return {
        "api_key": "test_api_key",
        "api_secret": "test_api_secret",
        "timeout": 30,
        "testnet": True
    }


@pytest.fixture
def mock_exchange():
    """Mock exchange object for testing."""
    exchange = Mock()
    exchange.id = "binance"
    exchange.load_markets.return_value = {
        "BTCUSDT": {
            "swap": True,
            "contract": True,
            "base": "BTC",
            "quote": "USDT"
        }
    }
    return exchange


@pytest.fixture
def temp_config_file(mock_config):
    """Create temporary configuration file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(mock_config, f)
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def mock_binance_client(mock_config, mock_exchange):
    """Mock Binance client for testing."""
    with patch('src.binance_sdk.BinanceFuturesClient.__init__', return_value=None):
        client = BinanceFuturesClient.__new__(BinanceFuturesClient)
        client._api_key = mock_config["api_key"]
        client._api_secret = mock_config["api_secret"]
        client.config = mock_config
        client._timeout = mock_config["timeout"]
        client._session = Mock()
        return client


@pytest.fixture
def sample_market_data():
    """Sample market data for testing."""
    return {
        "symbol": "BTCUSDT",
        "price": "45000.00",
        "volume": "1000.50",
        "timestamp": 1640995200000
    }


@pytest.fixture
def sample_order_data():
    """Sample order data for testing."""
    return {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "LIMIT",
        "quantity": "0.01",
        "price": "45000.00",
        "timeInForce": "GTC"
    }
