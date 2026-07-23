#!/usr/bin/env python3
"""
Test script to verify RiskManager integration with actual Binance data.
This tests the enhanced RiskManager with real account, balance, and position data.
"""

import sys
import os
import json
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.binance_sdk import BinanceFuturesClient
from risk.risks import RiskManager, AccountStatus
from util.utils import load_config


class RiskManagerIntegrationTester:
    """Test RiskManager integration with real Binance data."""
    
    def __init__(self):
        """Initialize the tester."""
        self.client = None
        self.risk_manager = None
        self.account_data = {}
        self.positions_data = []
        self.balance_data = []
        
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
    
    def fetch_account_data(self):
        """Fetch account data from Binance."""
        print("\n📊 Fetching Account Data...")
        print("=" * 50)
        
        try:
            # Get account information
            self.account_data = self.client.get_account_info()
            print("✅ Account data fetched successfully")
            
            # Display key metrics
            print(f"  Account Equity: ${self.account_data.get('accountEquity', 0)}")
            print(f"  Account Status: {self.account_data.get('accountStatus', 'UNKNOWN')}")
            print(f"  UniMMR: {self.account_data.get('uniMMR', 0)}")
            print(f"  Available Balance: ${self.account_data.get('totalAvailableBalance', 0)}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error fetching account data: {e}")
            return False
    
    def fetch_positions_data(self):
        """Fetch positions data from Binance."""
        print("\n📈 Fetching Positions Data...")
        print("=" * 50)
        
        try:
            # Get positions
            self.positions_data = self.client.get_positions()
            print(f"✅ Positions data fetched successfully ({len(self.positions_data)} positions)")
            
            # Display active positions
            active_positions = [p for p in self.positions_data if float(p.get('positionAmt', 0)) != 0]
            if active_positions:
                print(f"  Active positions: {len(active_positions)}")
                for pos in active_positions:
                    symbol = pos.get('symbol', '')
                    amount = pos.get('positionAmt', 0)
                    unrealized_pnl = pos.get('unrealizedProfit', 0)
                    print(f"    {symbol}: {amount} units, P&L: ${unrealized_pnl}")
            else:
                print("  No active positions")
            
            return True
            
        except Exception as e:
            print(f"❌ Error fetching positions data: {e}")
            return False
    
    def fetch_balance_data(self):
        """Fetch balance data from Binance."""
        print("\n💳 Fetching Balance Data...")
        print("=" * 50)
        
        try:
            # Get balances
            self.balance_data = self.client.get_balances()
            print(f"✅ Balance data fetched successfully ({len(self.balance_data)} assets)")
            
            # Display non-zero balances
            non_zero_balances = [b for b in self.balance_data if float(b.get('totalWalletBalance', 0)) > 0]
            if non_zero_balances:
                print("  Non-zero balances:")
                for balance in non_zero_balances:
                    asset = balance.get('asset', '')
                    total_wallet = balance.get('totalWalletBalance', 0)
                    print(f"    {asset}: ${total_wallet}")
            else:
                print("  No non-zero balances")
            
            return True
            
        except Exception as e:
            print(f"❌ Error fetching balance data: {e}")
            return False
    
    def initialize_risk_manager(self):
        """Initialize RiskManager with account data."""
        print("\n🛡️ Initializing RiskManager...")
        print("=" * 50)
        
        try:
            self.risk_manager = RiskManager(self.account_data)
            print("✅ RiskManager initialized successfully")
            
            # Display risk metrics
            print(f"  Account Status: {self.risk_manager.get_account_status().value}")
            print(f"  Margin Ratio: {self.risk_manager.get_margin_ratio():.4f}")
            print(f"  Utilization Ratio: {self.risk_manager.get_utilization_ratio():.4f}")
            print(f"  Available Margin Ratio: {self.risk_manager.get_available_margin_ratio():.4f}")
            print(f"  Liquidation Risk: {self.risk_manager.get_liquidation_risk_level()}")
            print(f"  Is At Risk: {self.risk_manager.is_at_risk()}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error initializing RiskManager: {e}")
            return False
    
    def test_balance_processing(self):
        """Test balance data processing."""
        print("\n🔍 Testing Balance Data Processing...")
        print("=" * 50)
        
        try:
            balance_info = self.risk_manager.process_balance_data(self.balance_data)
            
            print("✅ Balance processing completed")
            print(f"  Number of assets: {balance_info['num_assets']}")
            print(f"  Total USD value: ${balance_info['total_usd_value']:.2f}")
            
            print("\n  Processed balances:")
            for asset, info in balance_info['balances'].items():
                if info['total_wallet_balance'] > 0:
                    print(f"    {asset}:")
                    print(f"      Total Wallet: ${info['total_wallet_balance']:.2f}")
                    print(f"      Cross Margin: ${info['cross_margin_balance']:.2f}")
                    print(f"      Futures: ${info['futures_balance']:.2f}")
                    print(f"      Unrealized P&L: ${info['unrealized_pnl']:.2f}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error processing balance data: {e}")
            return False
    
    def test_positions_processing(self):
        """Test positions data processing."""
        print("\n🔍 Testing Positions Data Processing...")
        print("=" * 50)
        
        try:
            position_info = self.risk_manager.process_positions_data(self.positions_data)
            
            print("✅ Positions processing completed")
            print(f"  Total positions: {position_info['total_positions']}")
            print(f"  Total unrealized P&L: ${position_info['total_unrealized_pnl']:.2f}")
            print(f"  Total position value: ${position_info['total_position_value']:.2f}")
            
            if position_info['positions']:
                print("\n  Processed positions:")
                for symbol, info in position_info['positions'].items():
                    print(f"    {symbol}:")
                    print(f"      Side: {info['side']}")
                    print(f"      Quantity: {info['quantity']}")
                    print(f"      Entry Price: ${info['entry_price']:.4f}")
                    print(f"      Mark Price: ${info['mark_price']:.4f}")
                    print(f"      Unrealized P&L: ${info['unrealized_pnl']:.2f}")
                    print(f"      P&L %: {info['pnl_percentage']:.2f}%")
            
            return True
            
        except Exception as e:
            print(f"❌ Error processing positions data: {e}")
            return False
    
    def test_accounts_summary(self):
        """Test accounts summary generation."""
        print("\n🔍 Testing Accounts Summary Generation...")
        print("=" * 50)
        
        try:
            accounts_summary = self.risk_manager.get_accounts_summary(
                self.balance_data, 
                self.positions_data
            )
            
            print("✅ Accounts summary generated successfully")
            print(f"  Exchange: {accounts_summary['exchange']}")
            print(f"  Account Value: ${accounts_summary['account_value']:.2f}")
            print(f"  Position Value: ${accounts_summary['position_value']:.2f}")
            print(f"  Leverage: {accounts_summary['leverage']:.2f}x")
            print(f"  Available Balance: ${accounts_summary['available_balance']:.2f}")
            print(f"  Unrealized P&L: ${accounts_summary['unrealized_pnl']:.2f}")
            print(f"  Margin Ratio: {accounts_summary['margin_ratio']:.4f}")
            print(f"  Risk Level: {accounts_summary['risk_level']}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error generating accounts summary: {e}")
            return False
    
    def test_positions_summary(self):
        """Test positions summary generation."""
        print("\n🔍 Testing Positions Summary Generation...")
        print("=" * 50)
        
        try:
            positions_summary = self.risk_manager.get_positions_summary(self.positions_data)
            
            print("✅ Positions summary generated successfully")
            print(f"  Total Positions: {positions_summary['total_positions']}")
            print(f"  Total Unrealized P&L: ${positions_summary['total_unrealized_pnl']:.2f}")
            print(f"  Total Position Value: ${positions_summary['total_position_value']:.2f}")
            
            if positions_summary['positions']:
                print("\n  Position Details:")
                for symbol, info in positions_summary['positions'].items():
                    print(f"    {symbol}: {info['side']} {info['quantity']} @ ${info['entry_price']:.4f}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error generating positions summary: {e}")
            return False
    
    def test_risk_assessment(self):
        """Test comprehensive risk assessment."""
        print("\n🔍 Testing Comprehensive Risk Assessment...")
        print("=" * 50)
        
        try:
            risk_summary = self.risk_manager.get_risk_summary()
            
            print("✅ Risk assessment completed")
            print("  Risk Summary:")
            for key, value in risk_summary.items():
                print(f"    {key}: {value}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error in risk assessment: {e}")
            return False
    
    def save_test_results(self):
        """Save test results for analysis."""
        results = {
            "timestamp": datetime.now().isoformat(),
            "account_data": self.account_data,
            "positions_data": self.positions_data,
            "balance_data": self.balance_data,
            "risk_summary": self.risk_manager.get_risk_summary() if self.risk_manager else {},
            "accounts_summary": self.risk_manager.get_accounts_summary(self.balance_data, self.positions_data) if self.risk_manager else {},
            "positions_summary": self.risk_manager.get_positions_summary(self.positions_data) if self.risk_manager else {}
        }
        
        filename = f"tests/results/risk_manager_integration_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n💾 Test results saved to: {filename}")
        return filename
    
    def run_integration_test(self):
        """Run complete integration test."""
        print("🚀 Starting RiskManager Integration Test")
        print("=" * 60)
        
        # Setup client
        if not self.setup_client():
            return False
        
        # Fetch data
        if not self.fetch_account_data():
            return False
        if not self.fetch_positions_data():
            return False
        if not self.fetch_balance_data():
            return False
        
        # Initialize RiskManager
        if not self.initialize_risk_manager():
            return False
        
        # Test all functionality
        tests = [
            ("Balance Processing", self.test_balance_processing),
            ("Positions Processing", self.test_positions_processing),
            ("Accounts Summary", self.test_accounts_summary),
            ("Positions Summary", self.test_positions_summary),
            ("Risk Assessment", self.test_risk_assessment)
        ]
        
        passed_tests = 0
        for test_name, test_func in tests:
            print(f"\n🧪 Running test: {test_name}")
            if test_func():
                passed_tests += 1
                print(f"✅ {test_name} passed")
            else:
                print(f"❌ {test_name} failed")
        
        # Save results
        self.save_test_results()
        
        print(f"\n📊 Test Results: {passed_tests}/{len(tests)} tests passed")
        print("✅ RiskManager integration test completed!")
        
        return passed_tests == len(tests)


def main():
    """Main function."""
    tester = RiskManagerIntegrationTester()
    success = tester.run_integration_test()
    
    if success:
        print("\n🎉 All tests passed! RiskManager is ready for integration with monitoring system.")
    else:
        print("\n⚠️ Some tests failed. Please review the results.")


if __name__ == "__main__":
    main()
