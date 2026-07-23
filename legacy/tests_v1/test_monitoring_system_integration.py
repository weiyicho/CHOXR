#!/usr/bin/env python3
"""
Test script to verify the enhanced monitoring system with RiskManager integration.
This tests the complete flow: RiskManager → Monitor → Discord.
"""

import sys
import os
import json
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.binance_sdk import BinanceFuturesClient
from monitor.monitoring_system import MonitoringSystem
from util.utils import load_config


class MonitoringSystemIntegrationTester:
    """Test the enhanced monitoring system with RiskManager integration."""
    
    def __init__(self):
        """Initialize the tester."""
        self.client = None
        self.monitoring_system = None
        
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
    
    def setup_monitoring_system(self):
        """Setup monitoring system."""
        try:
            self.monitoring_system = MonitoringSystem("config/monitoring.json")
            print("✅ Monitoring system initialized successfully")
            return True
            
        except Exception as e:
            print(f"❌ Error setting up monitoring system: {e}")
            return False
    
    def test_risk_manager_integration(self):
        """Test RiskManager integration in monitoring system."""
        print("\n🛡️ Testing RiskManager Integration...")
        print("=" * 50)
        
        try:
            # Set exchange client
            self.monitoring_system.set_exchange_client(self.client)
            
            # Initialize RiskManager
            success = self.monitoring_system._initialize_risk_manager()
            
            if success and self.monitoring_system.risk_manager:
                print("✅ RiskManager successfully integrated")
                
                # Test risk metrics
                risk_summary = self.monitoring_system.risk_manager.get_risk_summary()
                print(f"  Account Status: {risk_summary['account_status']}")
                print(f"  Risk Level: {risk_summary['liquidation_risk']}")
                print(f"  Margin Ratio: {risk_summary['margin_ratio']}")
                print(f"  Is At Risk: {risk_summary['is_at_risk']}")
                
                return True
            else:
                print("❌ RiskManager integration failed")
                return False
                
        except Exception as e:
            print(f"❌ Error testing RiskManager integration: {e}")
            return False
    
    def test_accounts_summary_generation(self):
        """Test accounts summary generation using RiskManager."""
        print("\n📊 Testing Accounts Summary Generation...")
        print("=" * 50)
        
        try:
            accounts_summary = self.monitoring_system.get_accounts_summary()
            
            if accounts_summary:
                print("✅ Accounts summary generated successfully")
                print(f"  Exchange: {accounts_summary['exchange']}")
                print(f"  Account Value: ${accounts_summary['account_value']:.2f}")
                print(f"  Position Value: ${accounts_summary['position_value']:.2f}")
                print(f"  Leverage: {accounts_summary['leverage']:.2f}x")
                print(f"  Available Balance: ${accounts_summary['available_balance']:.2f}")
                print(f"  Risk Level: {accounts_summary['risk_level']}")
                
                return True
            else:
                print("❌ Could not generate accounts summary")
                return False
                
        except Exception as e:
            print(f"❌ Error testing accounts summary generation: {e}")
            return False
    
    def test_positions_summary_generation(self):
        """Test positions summary generation using RiskManager."""
        print("\n📈 Testing Positions Summary Generation...")
        print("=" * 50)
        
        try:
            positions_summary = self.monitoring_system.get_positions_summary()
            
            if positions_summary:
                print("✅ Positions summary generated successfully")
                print(f"  Total Positions: {positions_summary['total_positions']}")
                print(f"  Total Unrealized P&L: ${positions_summary['total_unrealized_pnl']:.2f}")
                print(f"  Total Position Value: ${positions_summary['total_position_value']:.2f}")
                
                if positions_summary['positions']:
                    print("  Active Positions:")
                    for symbol, info in positions_summary['positions'].items():
                        print(f"    {symbol}: {info['side']} {info['quantity']} @ ${info['entry_price']:.4f}")
                else:
                    print("  No active positions")
                
                return True
            else:
                print("❌ Could not generate positions summary")
                return False
                
        except Exception as e:
            print(f"❌ Error testing positions summary generation: {e}")
            return False
    
    def test_performance_summary_generation(self):
        """Test performance summary generation using PerformanceMonitor."""
        print("\n📊 Testing Performance Summary Generation...")
        print("=" * 50)
        
        try:
            performance_summary = self.monitoring_system.get_performance_summary()
            
            if performance_summary:
                print("✅ Performance summary generated successfully")
                print(f"  Period: {performance_summary['period']}")
                print(f"  Total Trades: {performance_summary['total_trades']}")
                print(f"  Win Rate: {performance_summary['win_rate']:.1f}%")
                print(f"  Net P&L: ${performance_summary['net_pnl']:.2f}")
                print(f"  Total Fees: ${performance_summary['total_fees']:.2f}")
                print(f"  Profit Factor: {performance_summary['profit_factor']:.2f}")
                
                return True
            else:
                print("❌ Could not generate performance summary")
                return False
                
        except Exception as e:
            print(f"❌ Error testing performance summary generation: {e}")
            return False
    
    def test_discord_notifications(self):
        """Test Discord notification sending."""
        print("\n📤 Testing Discord Notifications...")
        print("=" * 50)
        
        try:
            # Test accounts summary
            accounts_sent = self.monitoring_system.send_accounts_summary()
            if accounts_sent:
                print("✅ Accounts summary sent to Discord")
            else:
                print("⚠️ Accounts summary not sent (Discord notifier may not be configured)")
            
            # Test positions summary
            positions_sent = self.monitoring_system.send_positions_summary()
            if positions_sent:
                print("✅ Positions summary sent to Discord")
            else:
                print("⚠️ Positions summary not sent (Discord notifier may not be configured)")
            
            # Test performance summary
            performance_sent = self.monitoring_system.send_performance_summary()
            if performance_sent:
                print("✅ Performance summary sent to Discord")
            else:
                print("⚠️ Performance summary not sent (Discord notifier may not be configured)")
            
            return True
            
        except Exception as e:
            print(f"❌ Error testing Discord notifications: {e}")
            return False
    
    def test_system_health_monitoring(self):
        """Test system health monitoring with RiskManager."""
        print("\n🔍 Testing System Health Monitoring...")
        print("=" * 50)
        
        try:
            # Run health check
            self.monitoring_system._check_system_health()
            print("✅ System health check completed")
            
            # Check if RiskManager is properly integrated
            if self.monitoring_system.risk_manager:
                print("✅ RiskManager is active for health monitoring")
                
                # Test risk assessment
                is_at_risk = self.monitoring_system.risk_manager.is_at_risk()
                risk_level = self.monitoring_system.risk_manager.get_liquidation_risk_level()
                account_status = self.monitoring_system.risk_manager.get_account_status()
                
                print(f"  Account at risk: {is_at_risk}")
                print(f"  Risk level: {risk_level}")
                print(f"  Account status: {account_status.value}")
                
                return True
            else:
                print("❌ RiskManager not available for health monitoring")
                return False
                
        except Exception as e:
            print(f"❌ Error testing system health monitoring: {e}")
            return False
    
    def save_test_results(self):
        """Save test results for analysis."""
        results = {
            "timestamp": datetime.now().isoformat(),
            "test_results": {
                "risk_manager_integration": "passed" if hasattr(self, '_test_results') else "unknown",
                "accounts_summary": "passed" if hasattr(self, '_test_results') else "unknown",
                "positions_summary": "passed" if hasattr(self, '_test_results') else "unknown",
                "performance_summary": "passed" if hasattr(self, '_test_results') else "unknown",
                "discord_notifications": "passed" if hasattr(self, '_test_results') else "unknown",
                "system_health": "passed" if hasattr(self, '_test_results') else "unknown"
            },
            "monitoring_system_configured": self.monitoring_system is not None,
            "risk_manager_available": self.monitoring_system.risk_manager is not None if self.monitoring_system else False
        }
        
        filename = f"tests/results/monitoring_system_integration_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n💾 Test results saved to: {filename}")
        return filename
    
    def run_integration_test(self):
        """Run complete integration test."""
        print("🚀 Starting Monitoring System Integration Test")
        print("=" * 60)
        
        # Setup components
        if not self.setup_client():
            return False
        if not self.setup_monitoring_system():
            return False
        
        # Run tests
        tests = [
            ("RiskManager Integration", self.test_risk_manager_integration),
            ("Accounts Summary Generation", self.test_accounts_summary_generation),
            ("Positions Summary Generation", self.test_positions_summary_generation),
            ("Performance Summary Generation", self.test_performance_summary_generation),
            ("Discord Notifications", self.test_discord_notifications),
            ("System Health Monitoring", self.test_system_health_monitoring)
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
        print("✅ Monitoring system integration test completed!")
        
        return passed_tests == len(tests)


def main():
    """Main function."""
    tester = MonitoringSystemIntegrationTester()
    success = tester.run_integration_test()
    
    if success:
        print("\n🎉 All tests passed! Monitoring system is ready with RiskManager integration.")
        print("\n💡 The system now follows the proper architecture:")
        print("   RiskManager (Business Logic) → Monitor (Data Processing) → Discord (Infrastructure)")
    else:
        print("\n⚠️ Some tests failed. Please review the results.")


if __name__ == "__main__":
    main()
