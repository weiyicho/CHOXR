#!/usr/bin/env python3
"""
Test script for the new simple Discord formatting.
Tests the 3 preferred formats: Accounts, Positions, and Performance Summary.
"""

import sys
import os
import json
from datetime import datetime, timedelta

# Add the parent directory to the path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from monitor.discord_notifier import DiscordNotifier
from util.utils import load_config, setup_logging


class NewSimpleFormatTester:
    """Test class for the new simple Discord formatting."""
    
    def __init__(self):
        """Initialize the tester."""
        self.logger = setup_logging("INFO")
        
        # Load Discord configuration
        try:
            monitoring_config = load_config("config/monitoring.json")
            webhook_url = monitoring_config.get('discord', {}).get('webhook_url', '')
            
            if not webhook_url:
                print("❌ Discord webhook URL not configured!")
                sys.exit(1)
                
            self.webhook_url = webhook_url
            print(f"✅ Discord webhook URL loaded")
            
        except Exception as e:
            print(f"❌ Error loading Discord config: {e}")
            sys.exit(1)
            
        # Initialize Discord notifier
        self.notifier = DiscordNotifier(webhook_url=self.webhook_url, enabled=True)
        print("✅ Discord notifier initialized")
        
    def test_accounts_summary(self):
        """Test accounts summary format."""
        print("\n📤 Testing Accounts Summary Format...")
        
        # Mock accounts data
        accounts_data = [
            {
                'exchange': 'binance',
                'account_value': 2084.56,
                'position_value': 3205.40,
                'leverage': 1.54,
                'available_balance': 963.73
            },
            {
                'exchange': 'bybit',
                'account_value': 1964.23,
                'position_value': 4157.69,
                'leverage': 2.12,
                'available_balance': 3699.21
            },
            {
                'exchange': 'bitget',
                'account_value': 2064.08,
                'position_value': 3073.37,
                'leverage': 1.49,
                'available_balance': 5182.95
            }
        ]
        
        success = self.notifier.send_accounts_summary(accounts_data)
        
        if success:
            print("✅ Accounts summary sent successfully!")
        else:
            print("❌ Failed to send accounts summary")
            
        return success
        
    def test_positions_summary(self):
        """Test positions summary format."""
        print("\n📤 Testing Positions Summary Format...")
        
        # Mock positions data
        positions_data = [
            {
                'symbol': 'DOGEUSDT',
                'side': 'LONG',
                'quantity': 100.00,
                'entry_price': 0.0800,
                'current_price': 0.0820,
                'unrealized_pnl': 0.20,
                'pnl_percentage': 2.50
            },
            {
                'symbol': 'BTCUSDT',
                'side': 'SHORT',
                'quantity': 0.001,
                'entry_price': 45000.00,
                'current_price': 44800.00,
                'unrealized_pnl': 0.20,
                'pnl_percentage': 0.44
            },
            {
                'symbol': 'ETHUSDT',
                'side': 'LONG',
                'quantity': 0.100,
                'entry_price': 3000.00,
                'current_price': 3020.00,
                'unrealized_pnl': 2.00,
                'pnl_percentage': 0.67
            }
        ]
        
        success = self.notifier.send_positions_summary(positions_data)
        
        if success:
            print("✅ Positions summary sent successfully!")
        else:
            print("❌ Failed to send positions summary")
            
        return success
        
    def test_performance_summary(self):
        """Test performance summary format."""
        print("\n📤 Testing Performance Summary Format...")
        
        # Mock performance data
        performance_data = {
            'period': 'Last 24 Hours',
            'total_trades': 15,
            'win_rate': 73.3,
            'net_pnl': 45.20,
            'total_fees': 12.50,
            'profit_factor': 2.15,
            'best_trade': 'DOGEUSDT +$12.50',
            'worst_trade': 'BTCUSDT -$3.20',
            'max_drawdown': 8.50
        }
        
        success = self.notifier.send_performance_summary(performance_data)
        
        if success:
            print("✅ Performance summary sent successfully!")
        else:
            print("❌ Failed to send performance summary")
            
        return success
        
    def run_all_tests(self):
        """Run all simple format tests."""
        print("🧪 New Simple Discord Format Test Suite")
        print("=" * 50)
        
        tests = [
            ("Accounts Summary", self.test_accounts_summary),
            ("Positions Summary", self.test_positions_summary),
            ("Performance Summary", self.test_performance_summary)
        ]
        
        results = {}
        
        for test_name, test_func in tests:
            print(f"\n🔍 Running {test_name} test...")
            try:
                result = test_func()
                results[test_name] = result
                status = "✅ PASSED" if result else "❌ FAILED"
                print(f"{test_name}: {status}")
                
            except Exception as e:
                print(f"❌ {test_name} failed with error: {e}")
                results[test_name] = False
                
        # Summary
        print("\n" + "=" * 50)
        print("📊 Test Results Summary:")
        
        passed = sum(1 for result in results.values() if result)
        total = len(results)
        
        for test_name, result in results.items():
            status = "✅ PASSED" if result else "❌ FAILED"
            print(f"  {test_name}: {status}")
            
        print(f"\nOverall: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All simple format tests passed!")
            print("📱 Check your Discord channel to see the clean formats!")
        else:
            print("⚠️ Some tests failed. Check the output above for details.")
            
        return passed == total


def main():
    """Main test function."""
    tester = NewSimpleFormatTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
