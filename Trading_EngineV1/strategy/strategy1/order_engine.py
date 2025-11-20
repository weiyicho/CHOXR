#!/usr/bin/env python3
"""
Real trading engine for order execution and position management.
"""

import sys
import os
import json
import time
from datetime import datetime, timezone
import math
# Add project root to Python path
project_root = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, project_root)

# Import from the main project src directory
import sys
import os
main_src_path = os.path.join(os.path.dirname(__file__), '..', '..', 'src')
sys.path.insert(0, main_src_path)
from binance_sdk import BinanceFuturesClient
from order.order import OrderManager
from util.utils import load_config, setup_logging
from util.config_manager import get_api_config, get_strategy_config


class RealTradingBot():
    """Trading engine for order execution and position management."""
    
    def __init__(self, api_config_path: str = None, strategy_config_path: str = None, exchange: str = "binance", strategy_name: str = "strategy1"):
        """Initialize the trading engine."""
        if api_config_path is None:
            api_config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'api.json')
        if strategy_config_path is None:
            strategy_config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'strategy1', 'strategy1.json')
        
        self.api_config_path = api_config_path
        self.strategy_config_path = strategy_config_path
        self.api_config = None
        self.strategy_config = None
        self.client = None
        self.order_manager = None
        self.exchange = exchange
        self.strategy_name = strategy_name
        self.logger = setup_logging("INFO")
        self.test_results = []
        self.quantity = None
        self.symbol = "DOGEUSDT"  # Default symbol
    def load_configuration(self):
        """Load configurations using ConfigManager."""
        try:
            # Use ConfigManager for automatic path resolution
            self.api_config = get_api_config(self.exchange)
            self.strategy_config = get_strategy_config(self.strategy_name)
            self.logger.info("Configurations loaded successfully using ConfigManager")
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            return False
    
    def initialize_client(self, symbol: str = None):
        """Initialize client and order manager."""
        try:
            if symbol is None:
                symbol = self.symbol

            binance_config = self.api_config.get("binance", {})
            mock_exchange = type('MockExchange', (), {'id': 'binance'})()
            
            self.client = BinanceFuturesClient(binance_config, mock_exchange)
            
            order_config = self.strategy_config.get('order', {})
            
            # Set default order config if not provided
            if not order_config:
                order_config = {'position': 50, 'leverage': 5}
            
            self.order_manager = OrderManager(order_config, symbol)
            self.logger.info(f'Client initialized: symbol={symbol}, config={order_config}')
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize client: {e}")
            return False
    
    def calculate_order_quantity(self, limit_price: float) -> float:
        if not hasattr(self, 'spot') or self.spot is None:
            self.spot, self.margin = self.order_manager.calculate_margin()
        quantity = self.spot / limit_price
        self.logger.info(f"📊 Quantity Calculation: ${self.spot:.2f} / ${limit_price:.6f} = {quantity:.6f}")
        return math.floor(quantity)
    
    def get_position_info(self) -> dict:
        if not hasattr(self, 'spot') or self.spot is None:
            self.spot, self.margin = self.order_manager.calculate_margin()
        
        return {
            'spot': self.spot,
            'margin': self.margin,
            'total_position': self.spot + self.margin,
            'leverage': self.order_manager.leverage
        }
    
    ### Order Execution Methods ###
    def limit_order(self, symbol: str = None, order_type: str = "BUY", 
                                 aggressiveness: str = "conservative", timeout: int = 60,future=True):
        """Execute limit order with position closing."""
        
        order_book = self.client.get_order_book(symbol, limit=20)
        calculation = self.order_manager.calculate_limit_price(
            order_book, order_type, aggressiveness
        )
        self.spot, self.margin = self.order_manager.calculate_margin()
        self.quantity = self.calculate_order_quantity(calculation['limit_price'])
        order_value = calculation['limit_price'] * self.quantity
        
        if not self.check_position_limits(symbol, order_value):
            self.logger.warning("⏭️  Skipping order due to position limits")
            return None
        
        if future:
            limit_order_result = self.client.place_limit_order(
                symbol=symbol,
                side=order_type,
                price=calculation['limit_price'],
                quantity=self.quantity,
                time_in_force='GTC'
            )
        else:
            limit_order_result = self.client.place_margin_limit_order(
                symbol=symbol,
                side=order_type,
                price=calculation['limit_price'],
                quantity=self.quantity,
                time_in_force='GTC'
            )
        # Use the shared monitoring method with custom timeout and calculation data
        return self._monitor_order_execution(
            limit_order_result, 
            symbol, 
            order_type, 
            calculation=calculation,
            timeout=timeout
        )
    
    
    def market_order(self, symbol: str = None, order_type: str = "BUY", future=True):
        """Execute market order."""
        try:
            # Get current market price for quantity calculation
            order_book = self.client.get_order_book(symbol, limit=5)
            self.quantity = self.calculate_order_quantity(order_book['bids'][0][0])
            if future:
                market_order_result = self.client.place_market_order(
                    symbol=symbol,
                    side=order_type,
                    quantity=self.quantity,
                )
            else:
                market_order_result = self.client.place_margin_market_order(
                    symbol=symbol,
                    side=order_type,
                    quantity=self.quantity,
                )
            return self._monitor_order_execution(market_order_result, symbol, order_type)
        except Exception as e:
            self.logger.error(f"Market order failed: {e}")
            return None
        
    
    ### Position Management Methods ###
    def check_position_limits(self, symbol: str = None, order_value: float = 6.0):
        """Validate position limits."""
        if not symbol:
            symbol = self.symbol
            
        try:
            positions = self.client.get_positions(symbol)
            
            total_position_value = 0.0
            for position in positions:
                if position.get('symbol') == symbol and float(position.get('positionAmt', 0)) != 0:
                    position_value = abs(float(position.get('positionAmt', 0)) * float(position.get('markPrice', 0)))
                    total_position_value += position_value
            
            max_total_position = 50.0
            
            self.logger.info(f"📊 Position Check: ${total_position_value:.2f} + ${order_value:.2f} = ${total_position_value + order_value:.2f} (limit: ${max_total_position:.2f})")
            
            if total_position_value + order_value > max_total_position:
                self.logger.warning(f"❌ Order would exceed position limit: ${total_position_value + order_value:.2f} > ${max_total_position:.2f}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to check position limits: {e}")
            return False
    
    def deleverage_position(self, symbol: str = None,quantity:int=None):
        self.client.place_market_order(
            symbol=symbol,
            side="SELL",
            quantity=quantity,
        )
        self.client.place_margin_market_order(
            symbol=symbol,
            side="SELL",
            quantity=quantity,
        )
        self.logger.info(f"✅ Deleveraged position for {symbol}")
            
        
        
        
    def _monitor_order_execution(self, order_result, symbol, order_type, calculation=None, timeout=30):
        """Monitor order execution and return result."""
        self.logger.info(f"✅ Order placed: OrderID {order_result.get('orderId')}")
        
        if 'orderId' not in order_result:
            self.logger.error("Failed to get order ID from order placement")
            return None
            
        order_id = order_result['orderId']
        
        for attempt in range(timeout):
            time.sleep(1)
            order_status = self.client.get_order_status(symbol, order_id)
            status = order_status.get('status')
            
            if status == 'FILLED':
                self.logger.info(f"🎉 Order FILLED after {attempt + 1} seconds!")
                entry_price = float(order_status.get('avgPrice', 0))
                
                result = {
                    'symbol': symbol,
                    'order_type': order_type,
                    'entry_price': entry_price,
                    'quantity': self.quantity,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
                
                if calculation:
                    result.update({
                        'aggressiveness': calculation.get('aggressiveness', 'conservative'),
                        'market_direction': calculation.get('market_direction'),
                        'obi': calculation.get('obi'),
                        'obiv': calculation.get('obiv'),
                        'limit_price': calculation.get('limit_price')
                    })
                
                self.logger.info(f"📊 Trade: Entry ${entry_price:.6f}")
                return result
                
            elif status == 'CANCELED':
                self.logger.warning(f"❌ Order CANCELED after {attempt + 1} seconds")
                return None
            
        self.logger.warning("⏰ Order timeout, canceling...")
        try:
            self.client.cancel_order(symbol, order_id)
        except Exception as e:
            self.logger.error(f"Cancel failed: {e}")
        return None
    
    def get_account_info(self) -> dict:
        """Get account information."""
        return self.client.get_account_info()