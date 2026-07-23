import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# Add project root to path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from strategy.strategy1.order_engine import RealTradingBot

class TestRealTradingBot:
    
    @pytest.fixture
    def mock_bot(self):
        """
        Fixture to create a RealTradingBot instance with mocked dependencies.
        This runs before each test method.
        """
        # Patch the configuration loaders to avoid file I/O
        with patch('strategy.strategy1.order_engine.get_api_config') as mock_get_api, \
             patch('strategy.strategy1.order_engine.get_strategy_config') as mock_get_strategy, \
             patch('strategy.strategy1.order_engine.setup_logging'):
            
            # Setup mock return values
            mock_get_api.return_value = {"binance": {"api_key": "test", "api_secret": "test"}}
            mock_get_strategy.return_value = {"order": {"position": 100, "leverage": 5}}
            
            # Initialize bot
            bot = RealTradingBot()
            bot.load_configuration()
            
            # Mock the client and order manager directly
            bot.client = MagicMock()
            bot.order_manager = MagicMock()
            
            # Mock specific attributes needed for calculations
            bot.order_manager.calculate_margin.return_value = (100.0, 20.0)  # spot=100, margin=20
            bot.order_manager.leverage = 5
            
            return bot

    def test_calculate_order_quantity(self, mock_bot):
        """
        Test that order quantity is calculated correctly based on spot balance and price.
        """
        # Arrange
        limit_price = 0.50
        mock_bot.spot = 100.0  # $100 available
        
        # Act
        quantity = mock_bot.calculate_order_quantity(limit_price)
        
        # Assert
        # Expected: 100 / 0.50 = 200
        assert quantity == 200.0
        assert isinstance(quantity, int) # Should be floored to integer

    def test_check_position_limits_allow(self, mock_bot):
        """
        Test that check_position_limits returns True when under the limit.
        """
        # Arrange
        mock_bot.symbol = "DOGEUSDT"
        
        # Mock get_positions response (empty or small position)
        mock_bot.client.get_positions.return_value = [
            {'symbol': 'DOGEUSDT', 'positionAmt': '10', 'markPrice': '0.1'} # Value = $1
        ]
        
        # Act
        # Order value $6 + Existing $1 = $7 < Limit $50
        result = mock_bot.check_position_limits(order_value=6.0)
        
        # Assert
        assert result is True

    def test_check_position_limits_deny(self, mock_bot):
        """
        Test that check_position_limits returns False when over the limit.
        """
        # Arrange
        mock_bot.symbol = "DOGEUSDT"
        
        # Mock get_positions response (large existing position)
        mock_bot.client.get_positions.return_value = [
            {'symbol': 'DOGEUSDT', 'positionAmt': '500', 'markPrice': '0.1'} # Value = $50
        ]
        
        # Act
        # Order value $6 + Existing $50 = $56 > Limit $50
        result = mock_bot.check_position_limits(order_value=6.0)
        
        # Assert
        assert result is False

    def test_limit_order_execution_flow(self, mock_bot):
        """
        Test the flow of placing a limit order without actually calling the API.
        """
        # Arrange
        mock_bot.check_position_limits = MagicMock(return_value=True)
        mock_bot.calculate_order_quantity = MagicMock(return_value=100)
        
        # Mock order book and calculation
        mock_bot.client.get_order_book.return_value = {'bids': [], 'asks': []}
        mock_bot.order_manager.calculate_limit_price.return_value = {'limit_price': 0.10}
        
        # Mock successful placement
        mock_bot.client.place_limit_order.return_value = {'orderId': 12345}
        
        # Mock monitoring to return success immediately
        mock_bot._monitor_order_execution = MagicMock(return_value={'status': 'FILLED'})

        # Act
        result = mock_bot.limit_order(symbol="DOGEUSDT", order_type="BUY", future=True)

        # Assert
        mock_bot.client.place_limit_order.assert_called_once()
        assert result['status'] == 'FILLED'
