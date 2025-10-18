#!/usr/bin/env python3
"""
Test script for limit order price calculations and placement.
Tests OBI/OBIV analysis and dynamic limit order pricing.
"""

import sys
import os
import json
from datetime import datetime, timezone

# Add the parent directory to the path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.binance_sdk import BinanceFuturesClient
from order.order import OrderManager
from util.utils import load_config, setup_logging


class LimitOrderTester:
    """Test class for limit order price calculations and placement."""
    
    def __init__(self, config_path: str = "config/api.json"):
        """
        Initialize the tester.
        
        Args:
            config_path: Path to API configuration file
        """
        self.config_path = config_path
        self.config = None
        self.client = None
        self.order_manager = None
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
        """Initialize Binance client and OrderManager."""
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
            
            # Initialize OrderManager with default config
            order_config = {
                'position': 1000,  # Default position size
                'leverage': 5      # Default leverage
            }
            self.order_manager = OrderManager(order_config, "DOGEUSDT", self.client)
            
            self.logger.info("Binance client and OrderManager initialized successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize client: {e}")
            return False
    
    def get_order_book_analysis(self, symbol: str = "DOGEUSDT"):
        """Get order book and perform analysis."""
        try:
            self.logger.info(f"=== Analyzing Order Book for {symbol} ===")
            
            # Get order book data
            order_book = self.client.get_order_book(symbol, limit=20)
            self.logger.info(f"Order book retrieved: {len(order_book.get('bids', []))} bids, {len(order_book.get('asks', []))} asks")
            
            # Perform OBI/OBIV analysis
            obi = self.order_manager.OBI(order_book)
            obiv = self.order_manager.OBIV(order_book)
            market_direction = self.order_manager.analyze_market_direction(order_book)
            
            self.logger.info(f"📊 Market Analysis:")
            self.logger.info(f"   OBI (Quantity Imbalance): {obi:.4f}")
            self.logger.info(f"   OBIV (Value Imbalance): {obiv:.4f}")
            self.logger.info(f"   Market Direction: {market_direction}")
            
            # Show current prices
            current_bid = float(order_book['bids'][0][0]) if order_book['bids'] else None
            current_ask = float(order_book['asks'][0][0]) if order_book['asks'] else None
            spread = current_ask - current_bid if current_bid and current_ask else None
            
            self.logger.info(f"💰 Current Prices:")
            self.logger.info(f"   Bid: ${current_bid:.6f}")
            self.logger.info(f"   Ask: ${current_ask:.6f}")
            self.logger.info(f"   Spread: ${spread:.6f} ({spread/current_bid*100:.2f}%)")
            
            return {
                'order_book': order_book,
                'obi': obi,
                'obiv': obiv,
                'market_direction': market_direction,
                'current_bid': current_bid,
                'current_ask': current_ask,
                'spread': spread
            }
            
        except Exception as e:
            self.logger.error(f"Order book analysis failed: {e}")
            return None
    
    def test_price_calculations(self, symbol: str = "DOGEUSDT"):
        """Test all price calculation scenarios."""
        try:
            analysis = self.get_order_book_analysis(symbol)
            if not analysis:
                return False
            
            order_book = analysis['order_book']
            market_direction = analysis['market_direction']
            
            self.logger.info(f"\n=== Testing Price Calculations ===")
            
            # Test all combinations
            scenarios = [
                ('BUY', 'conservative'),
                ('BUY', 'aggressive'),
                ('SELL', 'conservative'),
                ('SELL', 'aggressive')
            ]
            
            results = {}
            for order_type, aggressiveness in scenarios:
                self.logger.info(f"\n--- {order_type} {aggressiveness.upper()} ---")
                
                calculation = self.order_manager.calculate_limit_price(
                    order_book, order_type, aggressiveness, market_direction, self.symbol, self.client
                )
                
                results[f"{order_type}_{aggressiveness}"] = calculation
                
                self.logger.info(f"Limit Price: ${calculation['limit_price']:.6f}")
                self.logger.info(f"Percentile Used: {calculation['percentile_used']*100:.0f}%")
                self.logger.info(f"Current Bid: ${calculation['current_bid']:.6f}")
                self.logger.info(f"Current Ask: ${calculation['current_ask']:.6f}")
                
                # Show price difference from market
                if order_type == 'BUY':
                    diff = calculation['limit_price'] - calculation['current_ask']
                    diff_pct = diff / calculation['current_ask'] * 100
                    self.logger.info(f"vs Ask: ${diff:.6f} ({diff_pct:.3f}%)")
                else:
                    diff = calculation['limit_price'] - calculation['current_bid']
                    diff_pct = diff / calculation['current_bid'] * 100
                    self.logger.info(f"vs Bid: ${diff:.6f} ({diff_pct:.3f}%)")
            
            return results
            
        except Exception as e:
            self.logger.error(f"Price calculation test failed: {e}")
            return False
    
    def test_limit_order_placement(self, symbol: str = "DOGEUSDT", max_order_value: float = 6.0):
        """Test actual limit order placement."""
        try:
            self.logger.info(f"\n=== Testing Limit Order Placement for {symbol} (Max ${max_order_value}) ===")
            
            # Get analysis
            analysis = self.get_order_book_analysis(symbol)
            if not analysis:
                return False
            
            order_book = analysis['order_book']
            current_price = (analysis['current_bid'] + analysis['current_ask']) / 2
            
            # Calculate safe quantity
            safe_quantity = max_order_value / current_price
            
            # Get exchange info for precision
            exchange_info = self.client.get_exchange_info()
            symbol_info = None
            for s in exchange_info.get('symbols', []):
                if s.get('symbol') == symbol:
                    symbol_info = s
                    break
            
            if symbol_info:
                lot_size_filter = next((f for f in symbol_info.get('filters', []) if f.get('filterType') == 'LOT_SIZE'), None)
                if lot_size_filter:
                    step_size = float(lot_size_filter.get('stepSize', '0.01'))
                    min_qty = float(lot_size_filter.get('minQty', '1.0'))
                    safe_quantity = round(safe_quantity / step_size) * step_size
                    safe_quantity = max(safe_quantity, min_qty)
            
            self.logger.info(f"Calculated quantity: {safe_quantity} {symbol}")
            
            # Let user choose scenario
            print(f"\nChoose limit order scenario:")
            print(f"1. BUY Conservative (25th percentile)")
            print(f"2. BUY Aggressive (75th percentile)")
            print(f"3. SELL Conservative (25th percentile)")
            print(f"4. SELL Aggressive (75th percentile)")
            print(f"5. Skip limit order test")
            
            choice = input("Enter choice (1-5): ").strip()
            
            if choice == '5':
                self.logger.info("Skipping limit order placement test")
                return True
            
            scenarios = {
                '1': ('BUY', 'conservative'),
                '2': ('BUY', 'aggressive'),
                '3': ('SELL', 'conservative'),
                '4': ('SELL', 'aggressive')
            }
            
            if choice not in scenarios:
                self.logger.error("Invalid choice")
                return False
            
            order_type, aggressiveness = scenarios[choice]
            
            # Calculate limit price
            calculation = self.order_manager.calculate_limit_price(
                order_book, order_type, aggressiveness, None, self.symbol, self.client
            )
            
            self.logger.info(f"\n🎯 Order Details:")
            self.logger.info(f"   Type: {order_type}")
            self.logger.info(f"   Aggressiveness: {aggressiveness}")
            self.logger.info(f"   Market Direction: {calculation['market_direction']}")
            self.logger.info(f"   Quantity: {safe_quantity}")
            self.logger.info(f"   Limit Price: ${calculation['limit_price']:.6f}")
            self.logger.info(f"   Total Value: ${safe_quantity * calculation['limit_price']:.2f}")
            
            # Confirm placement
            confirm = input(f"\nPlace this {order_type} limit order? (y/N): ").strip().lower()
            if confirm != 'y':
                self.logger.info("Order placement cancelled")
                return True
            
            # Place limit order
            self.logger.info("Placing limit order...")
            order_result = self.client.place_limit_order(
                symbol=symbol,
                side=order_type,
                price=calculation['limit_price'],
                quantity=safe_quantity,
                time_in_force='GTC'
            )
            
            self.logger.info(f"✅ Limit order placed: {order_result}")
            
            if 'orderId' in order_result:
                # Monitor order status
                import time
                time.sleep(2)
                
                order_status = self.client.get_order_status(symbol, order_result['orderId'])
                self.logger.info(f"Order status: {order_status}")
                
                # Option to cancel
                if order_status.get('status') == 'NEW':
                    cancel_choice = input("Cancel the order? (y/N): ").strip().lower()
                    if cancel_choice == 'y':
                        cancel_result = self.client.cancel_order(symbol, order_result['orderId'])
                        self.logger.info(f"Order cancelled: {cancel_result}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Limit order placement test failed: {e}")
            return False
    
    def run_interactive_test(self):
        """Run interactive testing interface."""
        self.logger.info("=== Limit Order Testing Interface ===")
        
        if not self.load_configuration():
            return False
        
        if not self.initialize_client():
            return False
        
        while True:
            print(f"\n{'='*50}")
            print("Limit Order Testing Menu")
            print("1. Test Order Book Analysis (OBI/OBIV)")
            print("2. Test Price Calculations (All Scenarios)")
            print("3. Test Limit Order Placement")
            print("4. Run All Tests")
            print("5. Exit")
            
            choice = input("\nEnter your choice (1-5): ").strip()
            
            if choice == '1':
                self.get_order_book_analysis()
            elif choice == '2':
                self.test_price_calculations()
            elif choice == '3':
                self.test_limit_order_placement()
            elif choice == '4':
                self.get_order_book_analysis()
                self.test_price_calculations()
                self.test_limit_order_placement()
            elif choice == '5':
                print("Exiting...")
                break
            else:
                print("Invalid choice. Please try again.")
    
    def run_automated_test(self, symbol: str = "DOGEUSDT"):
        """Run automated test of all scenarios."""
        self.logger.info("=== Automated Limit Order Testing ===")
        
        if not self.load_configuration():
            return False
        
        if not self.initialize_client():
            return False
        
        # Run all tests
        tests = [
            ("Order Book Analysis", lambda: self.get_order_book_analysis(symbol)),
            ("Price Calculations", lambda: self.test_price_calculations(symbol)),
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
    print("Limit Order Testing System")
    print("=" * 30)
    print()
    print("This system tests:")
    print("- Order Book Imbalance analysis (OBI/OBIV)")
    print("- Dynamic limit order price calculations")
    print("- Actual limit order placement")
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
    
    tester = LimitOrderTester(config_path)
    
    print("Choose test mode:")
    print("1. Interactive mode (step by step)")
    print("2. Automated mode (run all tests)")
    print("3. Exit")
    
    mode = input("Enter choice (1-3): ").strip()
    
    if mode == '1':
        tester.run_interactive_test()
    elif mode == '2':
        success = tester.run_automated_test()
        if success:
            print("\n🎉 All tests passed!")
        else:
            print("\n❌ Some tests failed. Check the logs above for details.")
    elif mode == '3':
        print("Exiting...")
    else:
        print("Invalid choice!")


if __name__ == "__main__":
    main()
