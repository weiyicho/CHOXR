#!/usr/bin/env python3
"""
Test script for the monitoring system.
Tests Discord notifications, position monitoring, and performance tracking.
"""

import sys
import os
import json
import time
from datetime import datetime, timedelta

# Add the parent directory to the path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from monitor.monitoring_system import MonitoringSystem
from monitor.discord_notifier import DiscordNotifier
from monitor.position_monitor import PositionMonitor, AlertLevel
from monitor.performance_monitor import PerformanceMonitor
from src.binance_sdk import BinanceFuturesClient
from util.utils import load_config, setup_logging


class MonitoringSystemTester:
    """Test class for the monitoring system."""
    
    def __init__(self):
        """Initialize the tester."""
        self.logger = setup_logging("MonitoringSystemTester")
        
        # Load API configuration
        try:
            api_config = load_config("../config/api.json")
            self.api_key = api_config.get('binance', {}).get('api_key', '')
            self.api_secret = api_config.get('binance', {}).get('api_secret', '')
            self.testnet = api_config.get('binance', {}).get('testnet', True)
        except Exception as e:
            self.logger.error(f"Error loading API config: {e}")
            self.api_key = ""
            self.api_secret = ""
            self.testnet = True
            
        # Initialize exchange client
        if self.api_key and self.api_secret:
            self.exchange_client = BinanceFuturesClient(
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet
            )
        else:
            self.exchange_client = None
            self.logger.warning("API credentials not configured, using mock client")
            
    def test_discord_notifications(self):
        """Test Discord notification system."""
        print("\n=== Testing Discord Notifications ===")
        
        # Load Discord webhook URL from config
        try:
            monitoring_config = load_config("../config/monitoring.json")
            webhook_url = monitoring_config.get('discord', {}).get('webhook_url', '')
            
            if not webhook_url or webhook_url == "YOUR_DISCORD_WEBHOOK_URL_HERE":
                print("❌ Discord webhook URL not configured")
                print("Please set your Discord webhook URL in config/monitoring.json")
                return False
                
        except Exception as e:
            print(f"❌ Error loading monitoring config: {e}")
            return False
            
        # Initialize Discord notifier
        notifier = DiscordNotifier(webhook_url=webhook_url, enabled=True)
        
        # Test basic message
        print("Testing basic message...")
        success = notifier.send_message("🧪 Testing Discord notifications from Trading Engine")
        print(f"Basic message: {'✅ Success' if success else '❌ Failed'}")
        
        # Test embed message
        print("Testing embed message...")
        success = notifier.send_embed(
            title="🧪 Test Notification",
            description="Testing Discord embed notifications",
            color=0x0099ff,
            fields=[
                {"name": "Test Field", "value": "Test Value", "inline": True},
                {"name": "Status", "value": "Testing", "inline": True}
            ]
        )
        print(f"Embed message: {'✅ Success' if success else '❌ Failed'}")
        
        # Test trade notification
        print("Testing trade notification...")
        success = notifier.notify_order_placed(
            symbol="DOGEUSDT",
            side="BUY",
            quantity=100.0,
            price=0.08,
            order_type="LIMIT",
            account_type="TEST"
        )
        print(f"Trade notification: {'✅ Success' if success else '❌ Failed'}")
        
        # Test order filled notification
        print("Testing order filled notification...")
        success = notifier.notify_order_filled(
            symbol="DOGEUSDT",
            side="BUY",
            quantity=100.0,
            avg_price=0.0801
        )
        print(f"Order filled notification: {'✅ Success' if success else '❌ Failed'}")
        
        return True
        
    def test_performance_monitor(self):
        """Test performance monitoring system."""
        print("\n=== Testing Performance Monitor ===")
        
        # Initialize performance monitor
        monitor = PerformanceMonitor("tests/results/performance_test.json")
        
        # Record some test trades
        print("Recording test trades...")
        
        base_time = datetime.now() - timedelta(hours=2)
        
        # Winning trade
        monitor.record_trade(
            symbol="DOGEUSDT",
            side="BUY",
            quantity=100.0,
            entry_price=0.08,
            exit_price=0.082,
            entry_time=base_time,
            exit_time=base_time + timedelta(minutes=30),
            fees=0.1,
            strategy="test_strategy"
        )
        
        # Losing trade
        monitor.record_trade(
            symbol="BTCUSDT",
            side="SELL",
            quantity=0.001,
            entry_price=45000.0,
            exit_price=44800.0,
            entry_time=base_time + timedelta(minutes=30),
            exit_time=base_time + timedelta(hours=1),
            fees=0.5,
            strategy="test_strategy"
        )
        
        # Another winning trade
        monitor.record_trade(
            symbol="ETHUSDT",
            side="BUY",
            quantity=0.1,
            entry_price=3000.0,
            exit_price=3020.0,
            entry_time=base_time + timedelta(hours=1),
            exit_time=base_time + timedelta(hours=1, minutes=45),
            fees=0.3,
            strategy="test_strategy"
        )
        
        print("✅ Test trades recorded")
        
        # Get performance metrics
        print("Getting performance metrics...")
        metrics = monitor.get_performance_metrics()
        
        print(f"Total Trades: {metrics.total_trades}")
        print(f"Win Rate: {metrics.win_rate:.1f}%")
        print(f"Net P&L: ${metrics.net_pnl:.2f}")
        print(f"Profit Factor: {metrics.profit_factor:.2f}")
        print(f"Max Drawdown: ${metrics.max_drawdown:.2f}")
        
        # Generate report
        print("Generating performance report...")
        report = monitor.generate_report()
        print("Performance Report:")
        print(report)
        
        # Export trades
        print("Exporting trades...")
        export_file = monitor.export_trades("tests/results/test_trades_export.csv")
        if export_file:
            print(f"✅ Trades exported to {export_file}")
        else:
            print("❌ Failed to export trades")
            
        return True
        
    def test_position_monitor(self):
        """Test position monitoring system."""
        print("\n=== Testing Position Monitor ===")
        
        if not self.exchange_client:
            print("❌ Exchange client not available, skipping position monitor test")
            return False
            
        # Initialize position monitor
        monitor = PositionMonitor(
            exchange_client=self.exchange_client,
            monitoring_interval=10
        )
        
        # Test alert callback
        def test_alert_callback(alert):
            print(f"Alert received: {alert.level.value} - {alert.message}")
            
        monitor.alert_callback = test_alert_callback
        
        # Get position summary
        print("Getting position summary...")
        summary = monitor.get_position_summary()
        
        print(f"Total Positions: {summary.get('total_positions', 0)}")
        print(f"Total Value: ${summary.get('total_value', 0):.2f}")
        print(f"Total P&L: ${summary.get('total_pnl', 0):.2f}")
        
        # Test risk thresholds
        print("Testing risk thresholds...")
        monitor.update_risk_thresholds({
            'max_pnl_loss_percent': -5.0,
            'max_position_value': 100.0
        })
        
        print("✅ Position monitor test completed")
        return True
        
    def test_monitoring_system(self):
        """Test the integrated monitoring system."""
        print("\n=== Testing Integrated Monitoring System ===")
        
        # Initialize monitoring system
        system = MonitoringSystem("../config/monitoring.json")
        
        # Set exchange client if available
        if self.exchange_client:
            system.set_exchange_client(self.exchange_client)
            print("✅ Exchange client set")
        else:
            print("⚠️ No exchange client available")
            
        # Get system status
        print("Getting system status...")
        status = system.get_system_status()
        
        print(f"Monitoring Active: {status['monitoring_active']}")
        print(f"Exchange Connected: {status['exchange_connected']}")
        print(f"Discord Enabled: {status['discord_enabled']}")
        print(f"Position Monitoring: {status['position_monitoring']}")
        
        # Test manual report
        print("Testing manual report...")
        if system.discord_notifier:
            success = system.send_manual_report()
            print(f"Manual report: {'✅ Success' if success else '❌ Failed'}")
        else:
            print("⚠️ Discord notifier not available")
            
        return True
        
    def run_all_tests(self):
        """Run all monitoring system tests."""
        print("🧪 Monitoring System Test Suite")
        print("=" * 50)
        
        tests = [
            ("Discord Notifications", self.test_discord_notifications),
            ("Performance Monitor", self.test_performance_monitor),
            ("Position Monitor", self.test_position_monitor),
            ("Integrated System", self.test_monitoring_system)
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
            print("🎉 All monitoring system tests passed!")
        else:
            print("⚠️ Some tests failed. Check the output above for details.")
            
        return passed == total


def main():
    """Main test function."""
    tester = MonitoringSystemTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
