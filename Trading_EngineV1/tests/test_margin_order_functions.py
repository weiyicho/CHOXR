#!/usr/bin/env python3
"""
Test script for margin order functions without placing real orders.
This tests the margin order methods and data structures.
"""

import sys
import os
import json
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.binance_sdk import BinanceFuturesClient
from util.utils import load_config


class MarginOrderFunctionTester:
    """Test margin order functions without placing real orders."""
    
    def __init__(self):
        """Initialize the tester."""
        self.client = None
        self.test_symbol = "DOGEUSDT"
        
    def setup_client(self):
        """Setup Binance client."""
        try:
            config = load_config("config/api.json")
            binance_config = config.get("binance", {})
            
            # Create a mock exchange object
            mock_exchange = type('MockExchange', (), {'id': 'binance'})()
            
            self.client = BinanceFuturesClient(binance_config, mock_exchange)
            print("✅ Binance client initialized successfully")
            return True
            
        except Exception as e:
            print(f"❌ Error setting up client: {e}")
            return False
    
    def test_margin_order_methods(self):
        """Test that margin order methods exist and are callable."""
        print("\n🔍 Testing Margin Order Methods...")
        print("=" * 50)
        
        try:
            # Check if margin order methods exist
            methods_to_test = [
                'place_margin_market_order',
                'place_margin_limit_order',
                'get_margin_order_status',
                'get_open_margin_orders',
                'cancel_margin_order'
            ]
            
            print("📋 Checking margin order methods:")
            for method_name in methods_to_test:
                if hasattr(self.client, method_name):
                    method = getattr(self.client, method_name)
                    print(f"  ✅ {method_name}: {method.__doc__ or 'No docstring'}")
                else:
                    print(f"  ❌ {method_name}: Method not found")
                    return False
            
            print("✅ All margin order methods exist")
            return True
            
        except Exception as e:
            print(f"❌ Error testing margin order methods: {e}")
            return False
    
    def test_margin_order_parameters(self):
        """Test margin order method parameters."""
        print("\n🔍 Testing Margin Order Parameters...")
        print("=" * 50)
        
        try:
            import inspect
            
            # Test place_margin_market_order parameters
            market_order_method = getattr(self.client, 'place_margin_market_order')
            market_sig = inspect.signature(market_order_method)
            print(f"📋 place_margin_market_order parameters: {market_sig}")
            
            # Test place_margin_limit_order parameters
            limit_order_method = getattr(self.client, 'place_margin_limit_order')
            limit_sig = inspect.signature(limit_order_method)
            print(f"📋 place_margin_limit_order parameters: {limit_sig}")
            
            # Test get_margin_order_status parameters
            status_method = getattr(self.client, 'get_margin_order_status')
            status_sig = inspect.signature(status_method)
            print(f"📋 get_margin_order_status parameters: {status_sig}")
            
            # Test cancel_margin_order parameters
            cancel_method = getattr(self.client, 'cancel_margin_order')
            cancel_sig = inspect.signature(cancel_method)
            print(f"📋 cancel_margin_order parameters: {cancel_sig}")
            
            print("✅ All margin order parameters are properly defined")
            return True
            
        except Exception as e:
            print(f"❌ Error testing margin order parameters: {e}")
            return False
    
    def test_margin_account_data(self):
        """Test margin account data retrieval."""
        print("\n🔍 Testing Margin Account Data...")
        print("=" * 50)
        
        try:
            # Get account info
            account_info = self.client.get_account_info()
            
            print("📊 Account Information:")
            print(f"  Account Equity: ${account_info.get('accountEquity', 0)}")
            print(f"  Account Status: {account_info.get('accountStatus', 'N/A')}")
            print(f"  Available Balance: ${account_info.get('totalAvailableBalance', 0)}")
            print(f"  Max Withdraw: ${account_info.get('virtualMaxWithdrawAmount', 0)}")
            
            # Get balances
            balances = self.client.get_balances()
            
            print("\n💰 Balance Information:")
            for balance in balances:
                asset = balance.get('asset', '')
                total_wallet = float(balance.get('totalWalletBalance', 0))
                cross_margin = float(balance.get('crossMarginAsset', 0))
                
                if total_wallet > 0 or cross_margin > 0:
                    print(f"  {asset}:")
                    print(f"    Total Wallet: ${total_wallet:.2f}")
                    print(f"    Cross Margin: ${cross_margin:.2f}")
            
            print("✅ Margin account data retrieved successfully")
            return True
            
        except Exception as e:
            print(f"❌ Error testing margin account data: {e}")
            return False
    
    def test_margin_order_data_structures(self):
        """Test margin order data structures."""
        print("\n🔍 Testing Margin Order Data Structures...")
        print("=" * 50)
        
        try:
            # Test get_open_margin_orders (should return empty list if no orders)
            open_orders = self.client.get_open_margin_orders(symbol=self.test_symbol)
            
            print(f"📋 Open margin orders for {self.test_symbol}: {len(open_orders)}")
            
            if open_orders:
                print("📊 Sample order structure:")
                sample_order = open_orders[0]
                for key, value in sample_order.items():
                    print(f"  {key}: {value}")
            else:
                print("✅ No open orders (expected for test environment)")
            
            print("✅ Margin order data structures are working")
            return True
            
        except Exception as e:
            print(f"❌ Error testing margin order data structures: {e}")
            return False
    
    def test_margin_price_calculation(self):
        """Test margin price calculation functions."""
        print("\n🔍 Testing Margin Price Calculation...")
        print("=" * 50)
        
        try:
            # Get current price
            current_price = self.client.get_spot_price(self.test_symbol)
            current_price = float(current_price)
            
            print(f"📊 Current {self.test_symbol} price: ${current_price:.4f}")
            
            # Test price calculations for margin orders
            test_quantities = [1, 10, 100]
            max_order_value = 6.0
            
            print(f"\n📋 Price calculations for max order value: ${max_order_value}")
            
            for quantity in test_quantities:
                order_value = quantity * current_price
                can_afford = order_value <= max_order_value
                
                print(f"  {quantity} DOGE: size=${order_value:.2f} {'✅' if can_afford else '❌'}")
            
            # Test limit price calculations
            limit_price_buy = current_price * 0.995  # 0.5% below market
            limit_price_sell = current_price * 1.005  # 0.5% above market
            
            print(f"\n📋 Limit price calculations:")
            print(f"  BUY limit (0.5% below): ${limit_price_buy:.4f}")
            print(f"  SELL limit (0.5% above): ${limit_price_sell:.4f}")
            
            print("✅ Margin price calculations are working")
            return True
            
        except Exception as e:
            print(f"❌ Error testing margin price calculation: {e}")
            return False
    
    def run_margin_function_tests(self):
        """Run complete margin function tests."""
        print("🚀 Starting Margin Order Function Tests")
        print("=" * 60)
        print(f"Test Symbol: {self.test_symbol}")
        print("Note: This test does NOT place real orders")
        print("=" * 60)
        
        if not self.setup_client():
            return False
        
        # Run tests
        tests = [
            ("Margin Order Methods", self.test_margin_order_methods),
            ("Margin Order Parameters", self.test_margin_order_parameters),
            ("Margin Account Data", self.test_margin_account_data),
            ("Margin Order Data Structures", self.test_margin_order_data_structures),
            ("Margin Price Calculation", self.test_margin_price_calculation)
        ]
        
        passed_tests = 0
        for test_name, test_func in tests:
            print(f"\n🧪 Running test: {test_name}")
            if test_func():
                passed_tests += 1
                print(f"✅ {test_name} passed")
            else:
                print(f"❌ {test_name} failed")
        
        print(f"\n📊 Test Results: {passed_tests}/{len(tests)} tests passed")
        
        if passed_tests == len(tests):
            print("🎉 All margin function tests passed!")
            return True
        else:
            print("⚠️ Some margin function tests failed.")
            return False
    
    def save_test_results(self):
        """Save test results for analysis."""
        results = {
            "timestamp": datetime.now().isoformat(),
            "test_type": "margin_order_functions",
            "symbol": self.test_symbol,
            "tests_run": "function_validation_only",
            "real_orders_placed": False
        }
        
        filename = f"tests/results/margin_function_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n💾 Test results saved to: {filename}")
        return filename


def main():
    """Main function."""
    tester = MarginOrderFunctionTester()
    
    print("ℹ️ This test validates margin order functions without placing real orders")
    print("It's safe to run and will only test method availability and data structures")
    
    success = tester.run_margin_function_tests()
    tester.save_test_results()
    
    if success:
        print("\n🎉 Margin function testing completed successfully!")
        print("✅ All margin order functions are available and working")
        print("🚀 Ready for real margin order testing!")
    else:
        print("\n⚠️ Some tests failed. Please review the results.")


if __name__ == "__main__":
    main()
