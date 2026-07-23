#!/usr/bin/env python3
"""
Test script for Binance margin orders (cross margin only).
This tests margin market orders, limit orders, and order management.
"""

import sys
import os
import json
import time
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.binance_sdk import BinanceFuturesClient
from util.utils import load_config


class MarginOrderTester:
    """Test Binance margin orders with cross margin."""
    
    def __init__(self):
        """Initialize the tester."""
        self.client = None
        self.test_symbol = "DOGEUSDT"  # Using DOGEUSDT for margin testing
        self.max_order_value = 6.0  # $6 max per order
        self.total_position_limit = 50.0  # $50 total position limit
        
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
    
    def get_current_price(self):
        """Get current market price for test symbol."""
        try:
            price = self.client.get_spot_price(self.test_symbol)
            return float(price)
        except Exception as e:
            print(f"❌ Error getting current price: {e}")
            return None
    
    def calculate_order_quantity(self, price, max_value):
        """Calculate order quantity based on max value."""
        try:
            # Calculate quantity to stay under max_value
            quantity = max_value / price
            
            # Round down to avoid precision issues
            quantity = int(quantity)  # For DOGE, we want whole numbers
            
            return max(1, quantity)  # Minimum 1 DOGE
        except Exception as e:
            print(f"❌ Error calculating quantity: {e}")
            return 1
    
    def test_margin_market_order(self):
        """Test margin market order."""
        print("\n📈 Testing Margin Market Order...")
        print("=" * 50)
        
        try:
            # Get current price
            current_price = self.get_current_price()
            if not current_price:
                print("❌ Could not get current price")
                return False
            
            print(f"Current {self.test_symbol} price: ${current_price:.4f}")
            
            # Calculate quantity
            quantity = self.calculate_order_quantity(current_price, self.max_order_value)
            print(f"Order quantity: {quantity} DOGE")
            print(f"Order value: ${quantity * current_price:.2f}")
            
            # Place margin market BUY order
            print(f"\n🚀 Placing margin market BUY order...")
            order_result = self.client.place_margin_market_order(
                symbol=self.test_symbol,
                side="BUY",
                quantity=quantity
            )
            
            print("✅ Margin market order placed successfully!")
            print(f"Order ID: {order_result.get('orderId', 'N/A')}")
            print(f"Status: {order_result.get('status', 'N/A')}")
            
            # Wait a moment for order to fill
            time.sleep(2)
            
            # Check order status
            order_id = order_result.get('orderId')
            if order_id:
                order_status = self.client.get_margin_order_status(
                    symbol=self.test_symbol,
                    order_id=order_id
                )
                print(f"\n📊 Order Status:")
                print(f"  Status: {order_status.get('status', 'N/A')}")
                print(f"  Filled Quantity: {order_status.get('executedQty', '0')}")
                
                # Calculate average price manually (avgPrice field doesn't exist in margin orders)
                executed_qty = float(order_status.get('executedQty', 0))
                cummulative_quote_qty = float(order_status.get('cummulativeQuoteQty', 0))
                if executed_qty > 0 and cummulative_quote_qty > 0:
                    avg_price = cummulative_quote_qty / executed_qty
                    print(f"  Avg Price: ${avg_price:.4f}")
                else:
                    print(f"  Avg Price: N/A")
            
            return True
            
        except Exception as e:
            print(f"❌ Error testing margin market order: {e}")
            return False
    
    def test_margin_limit_order(self):
        """Test margin limit order."""
        print("\n📈 Testing Margin Limit Order...")
        print("=" * 50)
        
        try:
            # Get current price
            current_price = self.get_current_price()
            if not current_price:
                print("❌ Could not get current price")
                return False
            
            print(f"Current {self.test_symbol} price: ${current_price:.4f}")
            
            # Calculate limit price (slightly below market for BUY)
            limit_price = current_price * 0.995  # 0.5% below market
            limit_price = round(limit_price, 4)  # Round to 4 decimal places
            
            # Calculate quantity
            quantity = self.calculate_order_quantity(limit_price, self.max_order_value)
            print(f"Limit price: ${limit_price:.4f}")
            print(f"Order quantity: {quantity} DOGE")
            print(f"Order value: ${quantity * limit_price:.2f}")
            
            # Place margin limit BUY order
            print(f"\n🚀 Placing margin limit BUY order...")
            order_result = self.client.place_margin_limit_order(
                symbol=self.test_symbol,
                side="BUY",
                quantity=quantity,
                price=limit_price
            )
            
            print("✅ Margin limit order placed successfully!")
            print(f"Order ID: {order_result.get('orderId', 'N/A')}")
            print(f"Status: {order_result.get('status', 'N/A')}")
            
            # Wait a moment
            time.sleep(2)
            
            # Check order status
            order_id = order_result.get('orderId')
            if order_id:
                order_status = self.client.get_margin_order_status(
                    symbol=self.test_symbol,
                    order_id=order_id
                )
                print(f"\n📊 Order Status:")
                print(f"  Status: {order_status.get('status', 'N/A')}")
                print(f"  Filled Quantity: {order_status.get('executedQty', '0')}")
                
                # Calculate average price manually (avgPrice field doesn't exist in margin orders)
                executed_qty = float(order_status.get('executedQty', 0))
                cummulative_quote_qty = float(order_status.get('cummulativeQuoteQty', 0))
                if executed_qty > 0 and cummulative_quote_qty > 0:
                    avg_price = cummulative_quote_qty / executed_qty
                    print(f"  Avg Price: ${avg_price:.4f}")
                else:
                    print(f"  Avg Price: N/A")
                
                # Cancel the order if it's still open
                if order_status.get('status') in ['NEW', 'PARTIALLY_FILLED']:
                    print(f"\n🛑 Canceling open order...")
                    cancel_result = self.client.cancel_margin_order(
                        symbol=self.test_symbol,
                        order_id=order_id
                    )
                    print(f"Cancel result: {cancel_result.get('status', 'N/A')}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error testing margin limit order: {e}")
            return False
    
    def test_margin_order_management(self):
        """Test margin order management functions."""
        print("\n📋 Testing Margin Order Management...")
        print("=" * 50)
        
        try:
            # Test get open margin orders
            print("🔍 Getting open margin orders...")
            open_orders = self.client.get_open_margin_orders(symbol=self.test_symbol)
            
            print(f"Open margin orders for {self.test_symbol}: {len(open_orders)}")
            
            for i, order in enumerate(open_orders[:3]):  # Show first 3 orders
                print(f"  Order {i+1}:")
                print(f"    ID: {order.get('orderId', 'N/A')}")
                print(f"    Symbol: {order.get('symbol', 'N/A')}")
                print(f"    Side: {order.get('side', 'N/A')}")
                print(f"    Type: {order.get('type', 'N/A')}")
                print(f"    Quantity: {order.get('origQty', 'N/A')}")
                print(f"    Price: {order.get('price', 'N/A')}")
                print(f"    Status: {order.get('status', 'N/A')}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error testing margin order management: {e}")
            return False
    
    def test_margin_account_info(self):
        """Test margin account information."""
        print("\n💳 Testing Margin Account Information...")
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
            
            return True
            
        except Exception as e:
            print(f"❌ Error testing margin account info: {e}")
            return False
    
    def test_margin_risk_scenarios(self):
        """Test margin risk scenarios."""
        print("\n⚠️ Testing Margin Risk Scenarios...")
        print("=" * 50)
        
        try:
            # Test position limits
            print("🔍 Testing position limits...")
            
            # Get current account info
            account_info = self.client.get_account_info()
            available_balance = float(account_info.get('totalAvailableBalance', 0))
            
            print(f"Available Balance: ${available_balance:.2f}")
            print(f"Max Order Value: ${self.max_order_value:.2f}")
            print(f"Total Position Limit: ${self.total_position_limit:.2f}")
            
            # Check if we're within limits
            if self.max_order_value > available_balance:
                print("⚠️ Warning: Max order value exceeds available balance")
            
            if self.total_position_limit > available_balance:
                print("⚠️ Warning: Total position limit exceeds available balance")
            
            # Test margin requirements
            current_price = self.get_current_price()
            if current_price:
                max_quantity = self.max_order_value / current_price
                print(f"Max quantity at current price: {int(max_quantity)} DOGE")
            
            return True
            
        except Exception as e:
            print(f"❌ Error testing margin risk scenarios: {e}")
            return False
    
    def run_margin_order_tests(self):
        """Run complete margin order tests."""
        print("🚀 Starting Binance Margin Order Tests")
        print("=" * 60)
        print(f"Test Symbol: {self.test_symbol}")
        print(f"Max Order Value: ${self.max_order_value}")
        print(f"Total Position Limit: ${self.total_position_limit}")
        print("=" * 60)
        
        if not self.setup_client():
            return False
        
        # Run tests
        tests = [
            ("Margin Account Info", self.test_margin_account_info),
            ("Margin Risk Scenarios", self.test_margin_risk_scenarios),
            ("Margin Order Management", self.test_margin_order_management),
            ("Margin Market Order", self.test_margin_market_order),
            ("Margin Limit Order", self.test_margin_limit_order)
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
            print("🎉 All margin order tests passed!")
            return True
        else:
            print("⚠️ Some margin order tests failed.")
            return False
    
    def save_test_results(self):
        """Save test results for analysis."""
        results = {
            "timestamp": datetime.now().isoformat(),
            "test_type": "margin_orders",
            "symbol": self.test_symbol,
            "max_order_value": self.max_order_value,
            "total_position_limit": self.total_position_limit,
            "margin_type": "cross_margin"
        }
        
        filename = f"tests/results/margin_order_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n💾 Test results saved to: {filename}")
        return filename


def main():
    """Main function."""
    tester = MarginOrderTester()
    
    print("⚠️ WARNING: This test will place REAL orders on Binance testnet!")
    print("Make sure you're using testnet credentials in config/api.json")
    
    response = input("\nDo you want to continue? (y/N): ")
    if response.lower() != 'y':
        print("Test cancelled.")
        return
    
    success = tester.run_margin_order_tests()
    tester.save_test_results()
    
    if success:
        print("\n🎉 Margin order testing completed successfully!")
        print("✅ Cross margin orders are working correctly")
    else:
        print("\n⚠️ Some tests failed. Please review the results.")


if __name__ == "__main__":
    main()
