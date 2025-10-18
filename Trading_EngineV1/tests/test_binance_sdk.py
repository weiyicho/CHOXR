"""
Unit tests for the enhanced Binance Futures Client.
"""

import pytest
import requests
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from src.binance_sdk import BinanceFuturesClient


class TestBinanceFuturesClient:
    """Test the enhanced Binance Futures Client."""
    
    @pytest.fixture
    def mock_config(self):
        """Mock configuration for testing."""
        return {
            "api_key": "test_api_key",
            "api_secret": "test_api_secret",
            "timeout": 30,
            "testnet": True
        }
    
    @pytest.fixture
    def mock_exchange(self):
        """Mock exchange object for testing."""
        exchange = Mock()
        exchange.id = "binance"
        return exchange
    
    @pytest.fixture
    def binance_client(self, mock_config, mock_exchange):
        """Create Binance client instance for testing."""
        with patch('src.binance_sdk.BinanceFuturesClient.__init__', return_value=None):
            client = BinanceFuturesClient.__new__(BinanceFuturesClient)
            client._api_key = mock_config["api_key"]
            client._api_secret = mock_config["api_secret"]
            client.config = mock_config
            client._timeout = mock_config["timeout"]
            client._session = Mock()
            client._market_endpoint = 'https://fapi.binance.com'
            client._private_endpoint = 'https://papi.binance.com'
            client.header = {"X-MBX-APIKEY": client._api_key}
            return client
    
    def test_generate_signature(self, binance_client):
        """Test signature generation."""
        params = {'symbol': 'BTCUSDT', 'side': 'BUY'}
        signed_params = binance_client._generate_signature(params)
        
        assert 'timestamp' in signed_params
        assert 'recvWindow' in signed_params
        assert 'signature' in signed_params
        assert signed_params['symbol'] == 'BTCUSDT'
        assert signed_params['side'] == 'BUY'
    
    def test_process_api_response_success(self, binance_client):
        """Test successful API response processing."""
        mock_response = Mock()
        mock_response.json.return_value = {'result': 'success'}
        
        result = binance_client._process_api_response(mock_response)
        assert result == {'result': 'success'}
    
    def test_process_api_response_with_code(self, binance_client):
        """Test API response processing with code."""
        mock_response = Mock()
        mock_response.json.return_value = {'code': 200, 'msg': 'Success'}
        
        result = binance_client._process_api_response(mock_response)
        assert result == 'Success'
    
    def test_process_api_response_error(self, binance_client):
        """Test API response processing with error."""
        mock_response = Mock()
        mock_response.json.return_value = {'code': 400, 'msg': 'Bad Request'}
        
        with pytest.raises(Exception):
            binance_client._process_api_response(mock_response)
    
    def test_convert_to_timestamp_datetime(self, binance_client):
        """Test timestamp conversion with datetime object."""
        dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        timestamp = binance_client._convert_to_timestamp(dt)
        assert isinstance(timestamp, int)
        assert timestamp > 0
    
    def test_convert_to_timestamp_string(self, binance_client):
        """Test timestamp conversion with string."""
        timestamp = binance_client._convert_to_timestamp("2023-01-01 12:00:00")
        assert isinstance(timestamp, int)
        assert timestamp > 0
    
    def test_convert_to_timestamp_none(self, binance_client):
        """Test timestamp conversion with None."""
        timestamp = binance_client._convert_to_timestamp(None)
        assert timestamp is None
    
    def test_convert_to_timestamp_invalid_type(self, binance_client):
        """Test timestamp conversion with invalid type."""
        with pytest.raises(ValueError):
            binance_client._convert_to_timestamp(123)
    
    @patch('requests.get')
    def test_get_klines(self, mock_get, binance_client):
        """Test getting klines data."""
        mock_response = Mock()
        mock_response.json.return_value = [['1640995200000', '45000', '46000', '44000', '45500', '100']]
        mock_get.return_value = mock_response
        
        result = binance_client.get_klines('BTCUSDT', '1h')
        
        mock_get.assert_called_once()
        assert isinstance(result, list)
    
    @patch('requests.get')
    def test_get_order_book(self, mock_get, binance_client):
        """Test getting order book data."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'bids': [['45000', '1.5']],
            'asks': [['45001', '2.0']]
        }
        mock_get.return_value = mock_response
        
        result = binance_client.get_order_book('BTCUSDT')
        
        mock_get.assert_called_once()
        assert 'bids' in result
        assert 'asks' in result
    
    @patch('requests.get')
    def test_get_recent_trades(self, mock_get, binance_client):
        """Test getting recent trades."""
        mock_response = Mock()
        mock_response.json.return_value = [{'price': '45000', 'qty': '0.1', 'time': 1640995200000}]
        mock_get.return_value = mock_response
        
        result = binance_client.get_recent_trades('BTCUSDT')
        
        mock_get.assert_called_once()
        assert isinstance(result, list)
    
    @patch('requests.get')
    def test_get_spot_price(self, mock_get, binance_client):
        """Test getting spot price."""
        mock_response = Mock()
        mock_response.json.return_value = {'price': '45000.00'}
        mock_get.return_value = mock_response
        
        result = binance_client.get_spot_price('BTCUSDT')
        
        assert result == '45000.00'
    
    @patch('requests.post')
    def test_place_market_order(self, mock_post, binance_client):
        """Test placing market order."""
        mock_response = Mock()
        mock_response.json.return_value = {'orderId': 12345, 'status': 'FILLED'}
        mock_post.return_value = mock_response
        
        result = binance_client.place_market_order('BTCUSDT', 'BUY', 0.01)
        
        mock_post.assert_called_once()
        assert 'orderId' in result
    
    @patch('requests.post')
    def test_place_limit_order(self, mock_post, binance_client):
        """Test placing limit order."""
        mock_response = Mock()
        mock_response.json.return_value = {'orderId': 12346, 'status': 'NEW'}
        mock_post.return_value = mock_response
        
        result = binance_client.place_limit_order('BTCUSDT', 'BUY', 45000, 0.01)
        
        mock_post.assert_called_once()
        assert 'orderId' in result
    
    @patch('requests.get')
    def test_get_order_status(self, mock_get, binance_client):
        """Test getting order status."""
        mock_response = Mock()
        mock_response.json.return_value = {'orderId': 12345, 'status': 'FILLED', 'symbol': 'BTCUSDT'}
        mock_get.return_value = mock_response
        
        result = binance_client.get_order_status('BTCUSDT', 12345)
        
        mock_get.assert_called_once()
        assert result['orderId'] == 12345
    
    @patch('requests.get')
    def test_get_open_orders(self, mock_get, binance_client):
        """Test getting open orders."""
        mock_response = Mock()
        mock_response.json.return_value = [{'orderId': 12345, 'status': 'NEW', 'symbol': 'BTCUSDT'}]
        mock_get.return_value = mock_response
        
        result = binance_client.get_open_orders()
        
        mock_get.assert_called_once()
        assert isinstance(result, list)
    
    @patch('requests.delete')
    def test_cancel_order(self, mock_delete, binance_client):
        """Test canceling order."""
        mock_response = Mock()
        mock_response.json.return_value = {'orderId': 12345, 'status': 'CANCELED'}
        mock_delete.return_value = mock_response
        
        result = binance_client.cancel_order('BTCUSDT', order_id=12345)
        
        mock_delete.assert_called_once()
        assert result['status'] == 'CANCELED'
    
    @patch('requests.get')
    def test_get_positions(self, mock_get, binance_client):
        """Test getting positions."""
        mock_response = Mock()
        mock_response.json.return_value = [{'symbol': 'BTCUSDT', 'positionAmt': '0.01', 'entryPrice': '45000'}]
        mock_get.return_value = mock_response
        
        result = binance_client.get_positions()
        
        mock_get.assert_called_once()
        assert isinstance(result, list)
    
    @patch('requests.get')
    def test_get_account_info(self, mock_get, binance_client):
        """Test getting account info."""
        mock_response = Mock()
        mock_response.json.return_value = {'totalWalletBalance': '10000', 'totalUnrealizedPnl': '100'}
        mock_get.return_value = mock_response
        
        result = binance_client.get_account_info()
        
        mock_get.assert_called_once()
        assert 'totalWalletBalance' in result
    
    @patch('requests.get')
    def test_get_balances(self, mock_get, binance_client):
        """Test getting balances."""
        mock_response = Mock()
        mock_response.json.return_value = [{'asset': 'USDT', 'free': '10000', 'locked': '0'}]
        mock_get.return_value = mock_response
        
        result = binance_client.get_balances()
        
        mock_get.assert_called_once()
        assert isinstance(result, list)
    
    @patch('requests.get')
    def test_get_trade_history(self, mock_get, binance_client):
        """Test getting trade history."""
        mock_response = Mock()
        mock_response.json.return_value = [{'price': '45000', 'qty': '0.01', 'commission': '0.001'}]
        mock_get.return_value = mock_response
        
        result = binance_client.get_trade_history('BTCUSDT')
        
        mock_get.assert_called_once()
        assert isinstance(result, list)
    
    @patch('requests.post')
    def test_change_leverage(self, mock_post, binance_client):
        """Test changing leverage."""
        mock_response = Mock()
        mock_response.json.return_value = {'leverage': 10, 'maxNotionalValue': '1000000'}
        mock_post.return_value = mock_response
        
        result = binance_client.change_leverage('BTCUSDT', 10)
        
        mock_post.assert_called_once()
        assert result['leverage'] == 10


# Integration tests (marked as slow)
@pytest.mark.slow
class TestBinanceSDKIntegration:
    """Integration tests for Binance SDK (requires network access)."""
    
    def test_public_endpoints_connectivity(self):
        """Test that public endpoints are accessible."""
        # This would require actual network access and should be mocked in CI
        pass
    
    def test_authentication_flow(self):
        """Test authentication flow with testnet."""
        # This would require actual API keys and should be mocked in CI
        pass
