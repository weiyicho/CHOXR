#!/usr/bin/env python3
"""
Test script for margin orders with RiskManager integration.
This tests margin orders with real-time risk monitoring and Discord notifications.
"""

import sys
import os
import json
import time
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.binance_sdk import BinanceFuturesClient
from risk.risks import RiskManager
from monitor.monitoring_system import MonitoringSystem
from util.utils import load_config


class MarginRiskIntegrationTester:
    """Test margin orders with RiskManager and monitoring integration."""
    
    def __init__(self):
        """Initialize the tester."""
        self.client = None
        self.risk_manager = None
        self.monitoring_system = None
        self.test_symbol = "DOGEUSDT"
        self.max_order_value = 6.0
        self.total_position_limit = 50.0
        
    def setup_components(self):
        """Setup all test components."""
        try:
            # Setup Binance client
            config = load_config("config/api.json")
            binance_config = config.get("binance", {})
            mock_exchange = type('MockExchange', (), {'id': 'binance'})()
            self.client = BinanceFuturesClient(binance_config, mock_exchange)
            
            # Setup monitoring system
            self.monitoring_system = MonitoringSystem("config/monitoring.json")
            self.monitoring_system.set_exchange_client(self.client)
            
            print("✅ All components initialized successfully")
            return True
            
        except Exception as e:
            print(f"❌ Error setting up components: {e}")
            return False
    
    def test_pre_order_risk_assessment(self):
        """Test risk assessment before placing margin orders."""
        print("\n🛡️ Testing Pre-Order Risk Assessment...")
        print("=" * 50)
        
        try:
            # Initialize RiskManager
            self.monitoring_system._initialize_risk_manager()
            self.risk_manager = self.monitoring_system.risk_manager
            
            if not self.risk_manager:
                print("❌ RiskManager not initialized")
                return False
            
            # Get current risk status
            risk_summary = self.risk_manager.get_risk_summary()
            
            print("📊 Current Risk Status:")
            print(f"  Account Status: {risk_summary['account_status']}")
            print(f"  Risk Level: {risk_summary['liquidation_risk']}")
            print(f"  Margin Ratio: {risk_summary['margin_ratio']}")
            print(f"  Is At Risk: {risk_summary['is_at_risk']}")
            print(f"  Available Balance: ${risk_summary['account_equity_usd']:.2f}")
            
            # Check if we can place orders
            can_trade = not risk_summary['is_at_risk']
            print(f"\n🚦 Can Place Orders: {'✅ Yes' if can_trade else '❌ No'}")
            
            if not can_trade:
                print("⚠️ Account is at risk - skipping order placement")
                return False
            
            return True
            
        except Exception as e:
            print(f"❌ Error in pre-order risk assessment: {e}")
            return False
    
    def test_margin_order_with_risk_monitoring(self):
        """Test margin order with real-time risk monitoring."""
        print("\n📈 Testing Margin Order with Risk Monitoring...")
        print("=" * 50)
        
        try:
            # Get current price
            current_price = self.client.get_spot_price(self.test_symbol)
            current_price = float(current_price)
            
            print(f"Current {self.test_symbol} price: ${current_price:.4f}")
            
            # Calculate order quantity
            quantity = int(self.max_order_value / current_price)
            quantity = max(1, quantity)
            
            print(f"Order quantity: {quantity} DOGE")
            print(f"Order value: ${quantity * current_price:.2f}")
            
            # Check risk before order
            print("\n🔍 Risk Check Before Order:")
            account_info_before = self.client.get_account_info()
            balance_before = float(account_info_before.get('totalAvailableBalance', 0))
            print(f"  Available Balance Before: ${balance_before:.2f}")
            
            # Place margin market order
            print(f"\n🚀 Placing margin market BUY order...")
            order_result = self.client.place_margin_market_order(
                symbol=self.test_symbol,
                side="BUY",
                quantity=quantity
            )
            
            print("✅ Margin order placed successfully!")
            print(f"Order ID: {order_result.get('orderId', 'N/A')}")
            
            # Wait for order to process
            time.sleep(3)
            
            # Check risk after order
            print("\n🔍 Risk Check After Order:")
            account_info_after = self.client.get_account_info()
            balance_after = float(account_info_after.get('totalAvailableBalance', 0))
            print(f"  Available Balance After: ${balance_after:.2f}")
            print(f"  Balance Change: ${balance_after - balance_before:.2f}")
            
            # Refresh RiskManager with new data
            self.monitoring_system._initialize_risk_manager()
            risk_summary_after = self.risk_manager.get_risk_summary()
            
            print(f"  Risk Level After: {risk_summary_after['liquidation_risk']}")
            print(f"  Is At Risk After: {risk_summary_after['is_at_risk']}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error testing margin order with risk monitoring: {e}")
            return False
    
    def test_margin_monitoring_integration(self):
        """Test margin orders with monitoring system integration."""
        print("\n📊 Testing Margin Monitoring Integration...")
        print("=" * 50)
        
        try:
            # Test accounts summary with margin data
            print("🔍 Testing accounts summary...")
            accounts_summary = self.monitoring_system.get_accounts_summary()
            
            if accounts_summary:
                print("✅ Accounts summary generated:")
                print(f"  Exchange: {accounts_summary['exchange']}")
                print(f"  Account Value: ${accounts_summary['account_value']:.2f}")
                print(f"  Available Balance: ${accounts_summary['available_balance']:.2f}")
                print(f"  Risk Level: {accounts_summary['risk_level']}")
            
            # Test positions summary
            print("\n🔍 Testing positions summary...")
            positions_summary = self.monitoring_system.get_positions_summary()
            
            if positions_summary:
                print("✅ Positions summary generated:")
                print(f"  Total Positions: {positions_summary['total_positions']}")
                print(f"  Total Unrealized P&L: ${positions_summary['total_unrealized_pnl']:.2f}")
            
            # Test Discord notifications (if configured)
            print("\n🔍 Testing Discord notifications...")
            try:
                accounts_sent = self.monitoring_system.send_accounts_summary()
                print(f"  Accounts summary sent: {'✅ Yes' if accounts_sent else '⚠️ Not configured'}")
                
                positions_sent = self.monitoring_system.send_positions_summary()
                print(f"  Positions summary sent: {'✅ Yes' if positions_sent else '⚠️ Not configured'}")
            except Exception as e:
                print(f"  Discord notifications: ⚠️ {e}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error testing margin monitoring integration: {e}")
            return False
    
    def test_margin_risk_alerts(self):
        """Test margin risk alerts and monitoring."""
        print("\n🚨 Testing Margin Risk Alerts...")
        print("=" * 50)
        
        try:
            # Check system health with RiskManager
            print("🔍 Testing system health monitoring...")
            self.monitoring_system._check_system_health()
            
            # Get current risk status
            risk_summary = self.risk_manager.get_risk_summary()
            
            print("📊 Current Risk Status:")
            print(f"  Account Status: {risk_summary['account_status']}")
            print(f"  Liquidation Risk: {risk_summary['liquidation_risk']}")
            print(f"  Margin Ratio: {risk_summary['margin_ratio']}")
            print(f"  Available Margin Ratio: {risk_summary['available_margin_ratio']}")
            
            # Check if alerts would be triggered
            risk_level = risk_summary['liquidation_risk']
            if risk_level in ['HIGH', 'CRITICAL']:
                print(f"⚠️ High risk detected: {risk_level}")
                print("🚨 Risk alerts would be sent to Discord")
            else:
                print(f"✅ Risk level is acceptable: {risk_level}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error testing margin risk alerts: {e}")
            return False
    
    def test_margin_position_management(self):
        """Test margin position management."""
        print("\n📋 Testing Margin Position Management...")
        print("=" * 50)
        
        try:
            # Get current positions
            positions = self.client.get_positions()
            margin_positions = [p for p in positions if float(p.get('positionAmt', 0)) != 0]
            
            print(f"Current margin positions: {len(margin_positions)}")
            
            if margin_positions:
                print("📊 Position Details:")
                for pos in margin_positions:
                    symbol = pos.get('symbol', '')
                    amount = pos.get('positionAmt', 0)
                    unrealized_pnl = pos.get('unrealizedProfit', 0)
                    print(f"  {symbol}: {amount} units, P&L: ${unrealized_pnl}")
                    
                    # Test position risk assessment
                    if float(unrealized_pnl) < -10:  # Loss threshold
                        print(f"  ⚠️ Position {symbol} has significant loss")
            else:
                print("No active margin positions")
            
            # Test position limits
            total_position_value = sum(float(p.get('notional', 0)) for p in margin_positions)
            print(f"\nTotal position value: ${total_position_value:.2f}")
            print(f"Position limit: ${self.total_position_limit:.2f}")
            
            if total_position_value > self.total_position_limit:
                print("⚠️ Total position value exceeds limit")
            else:
                print("✅ Total position value within limits")
            
            return True
            
        except Exception as e:
            print(f"❌ Error testing margin position management: {e}")
            return False
    
    def run_margin_risk_integration_tests(self):
        """Run complete margin risk integration tests."""
        print("🚀 Starting Margin Risk Integration Tests")
        print("=" * 60)
        print(f"Test Symbol: {self.test_symbol}")
        print(f"Max Order Value: ${self.max_order_value}")
        print(f"Total Position Limit: ${self.total_position_limit}")
        print("=" * 60)
        
        if not self.setup_components():
            return False
        
        # Run tests
        tests = [
            ("Pre-Order Risk Assessment", self.test_pre_order_risk_assessment),
            ("Margin Order with Risk Monitoring", self.test_margin_order_with_risk_monitoring),
            ("Margin Monitoring Integration", self.test_margin_monitoring_integration),
            ("Margin Risk Alerts", self.test_margin_risk_alerts),
            ("Margin Position Management", self.test_margin_position_management)
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
            print("🎉 All margin risk integration tests passed!")
            return True
        else:
            print("⚠️ Some margin risk integration tests failed.")
            return False
    
    def save_test_results(self):
        """Save test results for analysis."""
        results = {
            "timestamp": datetime.now().isoformat(),
            "test_type": "margin_risk_integration",
            "symbol": self.test_symbol,
            "max_order_value": self.max_order_value,
            "total_position_limit": self.total_position_limit,
            "risk_manager_integrated": self.risk_manager is not None,
            "monitoring_system_integrated": self.monitoring_system is not None
        }
        
        filename = f"tests/results/margin_risk_integration_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n💾 Test results saved to: {filename}")
        return filename


def main():
    """Main function."""
    tester = MarginRiskIntegrationTester()
    
    print("⚠️ WARNING: This test will place REAL orders on Binance testnet!")
    print("Make sure you're using testnet credentials in config/api.json")
    print("This test integrates margin orders with RiskManager and monitoring")
    
    response = input("\nDo you want to continue? (y/N): ")
    if response.lower() != 'y':
        print("Test cancelled.")
        return
    
    success = tester.run_margin_risk_integration_tests()
    tester.save_test_results()
    
    if success:
        print("\n🎉 Margin risk integration testing completed successfully!")
        print("✅ Margin orders work correctly with RiskManager and monitoring")
    else:
        print("\n⚠️ Some tests failed. Please review the results.")


if __name__ == "__main__":
    main()
