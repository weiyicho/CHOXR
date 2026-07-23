#!/usr/bin/env python3
"""
Test script for Binance SDK functions.
This script allows you to test various Binance SDK methods including order operations.
"""

import sys
import os
import json
from datetime import datetime, timezone

# Add the parent directory to the path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.binance_sdk import BinanceFuturesClient
from util.utils import load_config, setup_logging


class BinanceSDKTester:
    """Test class for Binance SDK functions."""
    
    def __init__(self, config_path: str = "config/api.json"):
        """
        Initialize the tester.
        
        Args:
            config_path: Path to API configuration file
        """
        self.config_path = config_path
        self.config = None
        self.client = None
        self.logger = setup_logging("INFO")
        
    def load_configuration(self):
        """Load API configuration."""
        try:
            self.config = load_config(self.config_path)
            self.logger.info("Configuration loaded successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            return False
    
    def initialize_client(self):
        """Initialize Binance client."""
        try:
            if not self.config:
                self.logger.error("Configuration not loaded")
                return False
            
            binance_config = self.config.get("binance", {})
            if not binance_config:
                self.logger.error("Binance configuration not found")
                return False
            
            # Create a mock exchange object
            mock_exchange = type('MockExchange', (), {'id': 'binance'})()
            
            self.client = BinanceFuturesClient(binance_config, mock_exchange)
            self.logger.info("Binance client initialized successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize client: {e}")
            return False
    
    def test_public_endpoints(self):
        """Test public endpoints (no authentication required)."""
        self.logger.info("=== Testing Public Endpoints ===")
        
        try:
            # Test getting exchange info
            self.logger.info("Testing get_exchange_info()...")
            exchange_info = self.client.get_exchange_info()
            self.logger.info(f"Exchange info retrieved: {len(exchange_info.get('symbols', []))} symbols")
            
            # Test getting order book
            self.logger.info("Testing get_order_book()...")
            order_book = self.client.get_order_book("BTCUSDT", limit=5)
            self.logger.info(f"Order book retrieved: {len(order_book.get('bids', []))} bids, {len(order_book.get('asks', []))} asks")
            
            # Test getting recent trades
            self.logger.info("Testing get_recent_trades()...")
            trades = self.client.get_recent_trades("BTCUSDT", limit=5)
            self.logger.info(f"Recent trades retrieved: {len(trades)} trades")
            
            # Test getting klines
            self.logger.info("Testing get_klines()...")
            klines = self.client.get_klines("BTCUSDT", "1m", limit=5)
            self.logger.info(f"Klines retrieved: {len(klines)} candles")
            
            # Test getting spot price
            self.logger.info("Testing get_spot_price()...")
            spot_price = self.client.get_spot_price("BTCUSDT")
            self.logger.info(f"Spot price: {spot_price}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Public endpoint test failed: {e}")
            return False
    
    def test_private_endpoints(self):
        """Test private endpoints (authentication required)."""
        self.logger.info("=== Testing Private Endpoints ===")
        
        try:
            # Test getting account info
            self.logger.info("Testing get_account_info()...")
            account_info = self.client.get_account_info()
            self.logger.info(f"Account info retrieved: Balance: {account_info.get('totalWalletBalance', 'N/A')}")
            
            # Test getting balances
            self.logger.info("Testing get_balances()...")
            balances = self.client.get_balances()
            self.logger.info(f"Balances retrieved: {len(balances)} assets")
            
            # Test getting positions
            self.logger.info("Testing get_positions()...")
            positions = self.client.get_positions()
            self.logger.info(f"Positions retrieved: {len(positions)} positions")
            
            # Test getting open orders
            self.logger.info("Testing get_open_orders()...")
            open_orders = self.client.get_open_orders()
            self.logger.info(f"Open orders retrieved: {len(open_orders)} orders")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Private endpoint test failed: {e}")
            return False
    
    def test_order_operations(self, symbol: str = "DOGEUSDT", max_order_value: float = 6.0):
        """Test order operations with immediate buy/sell cycle."""
        self.logger.info(f"=== Testing Order Operations for {symbol} (${max_order_value} Buy/Sell) ===")
        
        try:
            # Get current market price and exchange info for precision rules
            self.logger.info("Getting current market price and symbol info...")
            try:
                spot_price = float(self.client.get_spot_price(symbol))
                self.logger.info(f"Current {symbol} price: ${spot_price}")
                
                # Get exchange info to find precision rules
                exchange_info = self.client.get_exchange_info()
                symbol_info = None
                for s in exchange_info.get('symbols', []):
                    if s.get('symbol') == symbol:
                        symbol_info = s
                        break
                
                if symbol_info:
                    # Get quantity precision from symbol filters
                    lot_size_filter = next((f for f in symbol_info.get('filters', []) if f.get('filterType') == 'LOT_SIZE'), None)
                    if lot_size_filter:
                        step_size = float(lot_size_filter.get('stepSize', '0.00001'))
                        min_qty = float(lot_size_filter.get('minQty', '0.00001'))
                        self.logger.info(f"Symbol precision: min_qty={min_qty}, step_size={step_size}")
                    else:
                        step_size = 0.01  # Default for DOGE
                        min_qty = 1.0
                else:
                    step_size = 0.01  # Default for DOGE
                    min_qty = 1.0
                
                # Calculate quantity respecting precision rules
                raw_quantity = max_order_value / spot_price
                # Round to step size
                safe_quantity = round(raw_quantity / step_size) * step_size
                # Ensure minimum quantity
                safe_quantity = max(safe_quantity, min_qty)
                
                # Calculate actual order value
                order_value = safe_quantity * spot_price
                self.logger.info(f"Calculated quantity: {safe_quantity} {symbol} = ${order_value:.2f}")
                
            except Exception as price_error:
                self.logger.warning(f"Could not get current price: {price_error}")
                # Fallback for DOGE
                safe_quantity = 100.0  # DOGE fallback
                spot_price = 0.06  # DOGE fallback price
                self.logger.info(f"Using fallback: {safe_quantity} {symbol} at ${spot_price}")
            
            # Test immediate buy/sell cycle
            self.logger.info("=== Starting Buy/Sell Cycle ===")
            
            # Step 1: Buy order (market order for immediate execution)
            self.logger.info("Step 1: Placing BUY market order...")
            try:
                buy_order_result = self.client.place_market_order(
                    symbol=symbol,
                    side="BUY",
                    quantity=safe_quantity
                )
                self.logger.info(f"✅ BUY order placed: {buy_order_result}")
                
                if 'orderId' in buy_order_result:
                    # Wait a moment for order to fill
                    import time
                    time.sleep(2)
                    
                    # Check buy order status
                    buy_status = self.client.get_order_status(symbol, buy_order_result['orderId'])
                    self.logger.info(f"BUY order status: {buy_status}")
                    
                    # Step 2: Immediate sell order
                    if buy_status.get('status') in ['FILLED', 'PARTIALLY_FILLED']:
                        self.logger.info("Step 2: Placing SELL market order...")
                        
                        # Get actual filled quantity
                        filled_qty = float(buy_status.get('executedQty', safe_quantity))
                        self.logger.info(f"Selling {filled_qty} {symbol}")
                        
                        sell_order_result = self.client.place_market_order(
                            symbol=symbol,
                            side="SELL",
                            quantity=filled_qty
                        )
                        self.logger.info(f"✅ SELL order placed: {sell_order_result}")
                        
                        # Check sell order status
                        if 'orderId' in sell_order_result:
                            time.sleep(2)
                            sell_status = self.client.get_order_status(symbol, sell_order_result['orderId'])
                            self.logger.info(f"SELL order status: {sell_status}")
                            
                            # Calculate P&L
                            if sell_status.get('status') in ['FILLED', 'PARTIALLY_FILLED']:
                                buy_price = float(buy_status.get('avgPrice', spot_price))
                                sell_price = float(sell_status.get('avgPrice', spot_price))
                                pnl = (sell_price - buy_price) * filled_qty
                                self.logger.info(f"📊 Trade P&L: ${pnl:.4f} (Buy: ${buy_price:.4f}, Sell: ${sell_price:.4f})")
                    
                    else:
                        self.logger.warning(f"BUY order not filled: {buy_status}")
                
            except Exception as order_error:
                self.logger.error(f"Buy/Sell cycle failed: {order_error}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Order operations test failed: {e}")
            return False
    
    def test_leverage_operations(self, symbol: str = "DOGEUSDT"):
        """Test leverage operations."""
        self.logger.info(f"=== Testing Leverage Operations for {symbol} ===")
        
        try:
            # Test changing leverage (use correct FAPI endpoint)
            self.logger.info("Testing change_leverage()...")
            leverage_result = self.client.change_leverage(symbol, 5)
            self.logger.info(f"Leverage changed: {leverage_result}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Leverage operations test failed: {e}")
            return False
    
    def run_all_tests(self):
        """Run all tests."""
        self.logger.info("Starting Binance SDK tests...")
        
        if not self.load_configuration():
            return False
        
        if not self.initialize_client():
            return False
        
        # Run tests
        tests = [
            ("Public Endpoints", self.test_public_endpoints),
            ("Private Endpoints", self.test_private_endpoints),
            ("Order Operations", lambda: self.test_order_operations()),
            ("Leverage Operations", lambda: self.test_leverage_operations()),
        ]
        
        results = {}
        for test_name, test_func in tests:
            self.logger.info(f"\n--- Running {test_name} Test ---")
            try:
                results[test_name] = test_func()
            except Exception as e:
                self.logger.error(f"{test_name} test failed with exception: {e}")
                results[test_name] = False
        
        # Print summary
        self.logger.info("\n=== Test Summary ===")
        for test_name, result in results.items():
            status = "PASSED" if result else "FAILED"
            self.logger.info(f"{test_name}: {status}")
        
        return all(results.values())


def main():
    """Main function."""
    print("Binance SDK Tester")
    print("=================")
    print()
    print("Before running this test, make sure to:")
    print("1. Update config/api.json with your Binance API credentials")
    print("2. Use testnet API keys for safety")
    print("3. Ensure you have sufficient balance for testing")
    print()
    
    # Check if config file exists and has content
    config_path = "config/api.json"
    if not os.path.exists(config_path):
        print(f"Error: Configuration file {config_path} not found!")
        return
    
    with open(config_path, 'r') as f:
        config_content = f.read().strip()
        if not config_content or config_content == "{}":
            print(f"Error: Configuration file {config_path} is empty!")
            print("Please add your API credentials to the configuration file.")
            return
    
    # Ask user for confirmation
    response = input("Do you want to proceed with the test? (y/N): ").strip().lower()
    if response != 'y':
        print("Test cancelled.")
        return
    
    # Run tests
    tester = BinanceSDKTester(config_path)
    success = tester.run_all_tests()
    
    if success:
        print("\n🎉 All tests passed!")
    else:
        print("\n❌ Some tests failed. Check the logs above for details.")


if __name__ == "__main__":
    main()
