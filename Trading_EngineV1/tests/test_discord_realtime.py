#!/usr/bin/env python3
"""
Real-time Discord notification testing script.
Sends actual messages to Discord to test formatting and functionality.
"""

import sys
import os
import json
import time
from datetime import datetime, timedelta

# Add the parent directory to the path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from monitor.discord_notifier import DiscordNotifier
from util.utils import load_config, setup_logging


class DiscordRealtimeTester:
    """Test class for real-time Discord notifications."""
    
    def __init__(self):
        """Initialize the tester."""
        self.logger = setup_logging("INFO")
        
        # Load Discord configuration
        try:
            monitoring_config = load_config("config/monitoring.json")
            webhook_url = monitoring_config.get('discord', {}).get('webhook_url', '')
            
            if not webhook_url or webhook_url == "YOUR_DISCORD_WEBHOOK_URL_HERE":
                print("❌ Discord webhook URL not configured!")
                print("Please set your Discord webhook URL in config/monitoring.json")
                print("\nTo get a Discord webhook URL:")
                print("1. Go to your Discord server")
                print("2. Server Settings → Integrations → Webhooks")
                print("3. Create New Webhook")
                print("4. Copy the webhook URL")
                print("5. Update config/monitoring.json")
                sys.exit(1)
                
            self.webhook_url = webhook_url
            print(f"✅ Discord webhook URL loaded: {webhook_url[:50]}...")
            
        except Exception as e:
            print(f"❌ Error loading Discord config: {e}")
            sys.exit(1)
            
        # Initialize Discord notifier
        self.notifier = DiscordNotifier(webhook_url=self.webhook_url, enabled=True)
        print("✅ Discord notifier initialized")
        
    def test_basic_message(self):
        """Test basic text message."""
        print("\n📤 Testing Basic Text Message...")
        
        success = self.notifier.send_message(
            content="🧪 **Testing Discord Integration**\n\nThis is a test message from the Trading Engine monitoring system!",
            username="Trading Engine Test"
        )
        
        if success:
            print("✅ Basic message sent successfully!")
        else:
            print("❌ Failed to send basic message")
            
        return success
        
    def test_embed_message(self):
        """Test rich embed message."""
        print("\n📤 Testing Rich Embed Message...")
        
        success = self.notifier.send_embed(
            title="🎯 Trading Engine Status",
            description="System is running and monitoring positions",
            color=0x00ff00,  # Green
            fields=[
                {"name": "Status", "value": "🟢 Online", "inline": True},
                {"name": "Uptime", "value": "2 hours 15 minutes", "inline": True},
                {"name": "Version", "value": "v1.0.0", "inline": True},
                {"name": "Active Strategies", "value": "3 strategies running", "inline": False}
            ]
        )
        
        if success:
            print("✅ Embed message sent successfully!")
        else:
            print("❌ Failed to send embed message")
            
        return success
        
    def test_trade_notification(self):
        """Test trade execution notification."""
        print("\n📤 Testing Trade Execution Notification...")
        
        success = self.notifier.notify_order_placed(
            symbol="DOGEUSDT",
            side="BUY",
            quantity=100.0,
            price=0.082,
            order_type="LIMIT",
            account_type="TEST"
        )
        
        if success:
            print("✅ Trade notification sent successfully!")
        else:
            print("❌ Failed to send trade notification")
            
        return success
        
    def test_order_filled_notification(self):
        """Test order filled notification."""
        print("\n📤 Testing Order Filled Notification...")
        
        success = self.notifier.notify_order_filled(
            symbol="DOGEUSDT",
            side="BUY",
            quantity=100.0,
            avg_price=0.0821
        )
        
        if success:
            print("✅ Order filled notification sent successfully!")
        else:
            print("❌ Failed to send order filled notification")
            
        return success
        
    def test_risk_warning(self):
        """Test risk warning notification."""
        print("\n📤 Testing Risk Warning Notification...")
        
        success = self.notifier.notify_risk_warning(
            risk_level="HIGH",
            message="Position P&L loss exceeded 10% threshold. Current loss: -12.5%"
        )
        
        if success:
            print("✅ Risk warning sent successfully!")
        else:
            print("❌ Failed to send risk warning")
            
        return success
        
    def test_performance_report(self):
        """Test performance report notification."""
        print("\n📤 Testing Performance Report Notification...")
        
        success = self.notifier.send_embed(
            title="📊 Daily Performance Report",
            description="Trading performance summary for today",
            color=0x0099ff,  # Blue
            fields=[
                {"name": "Total Trades", "value": "15", "inline": True},
                {"name": "Win Rate", "value": "73.3%", "inline": True},
                {"name": "Net P&L", "value": "$45.20", "inline": True},
                {"name": "Best Trade", "value": "DOGEUSDT: +$12.50", "inline": True},
                {"name": "Worst Trade", "value": "BTCUSDT: -$3.20", "inline": True},
                {"name": "Profit Factor", "value": "2.15", "inline": True},
                {"name": "Active Positions", "value": "2 positions", "inline": False}
            ]
        )
        
        if success:
            print("✅ Performance report sent successfully!")
        else:
            print("❌ Failed to send performance report")
            
        return success
        
    def test_strategy_status(self):
        """Test strategy status notification."""
        print("\n📤 Testing Strategy Status Notification...")
        
        account_summary = {
            'account': {
                'equity': 1250.75,
                'margin_ratio': 0.35,
                'available': 800.50
            },
            'risk': {
                'level': 'MEDIUM',
                'effective_leverage': 2.8
            },
            'positions': {
                'total_positions': 3,
                'total_unrealized_pnl': 25.30
            }
        }
        
        success = self.notifier.notify_strategy_status(
            strategy_id="FUNDING_ARBITRAGE_V1",
            active_symbols=["DOGEUSDT", "BTCUSDT", "ETHUSDT"],
            account_summary=account_summary
        )
        
        if success:
            print("✅ Strategy status sent successfully!")
        else:
            print("❌ Failed to send strategy status")
            
        return success
        
    def test_error_notification(self):
        """Test error notification."""
        print("\n📤 Testing Error Notification...")
        
        success = self.notifier.notify_error(
            error_message="Connection timeout to Binance API. Retrying in 30 seconds..."
        )
        
        if success:
            print("✅ Error notification sent successfully!")
        else:
            print("❌ Failed to send error notification")
            
        return success
        
    def test_position_alert(self):
        """Test position alert notification."""
        print("\n📤 Testing Position Alert Notification...")
        
        success = self.notifier.send_embed(
            title="⚠️ Position Alert - CRITICAL",
            description="DOGEUSDT position has exceeded risk thresholds",
            color=0xff0000,  # Red
            fields=[
                {"name": "Symbol", "value": "DOGEUSDT", "inline": True},
                {"name": "Alert Type", "value": "P&L Loss Threshold", "inline": True},
                {"name": "Current P&L", "value": "-15.2%", "inline": True},
                {"name": "Position Value", "value": "$125.50", "inline": True},
                {"name": "Entry Price", "value": "$0.0800", "inline": True},
                {"name": "Current Price", "value": "$0.0678", "inline": True},
                {"name": "Action Required", "value": "Consider closing position or adjusting stop loss", "inline": False}
            ]
        )
        
        if success:
            print("✅ Position alert sent successfully!")
        else:
            print("❌ Failed to send position alert")
            
        return success
        
    def test_scan_result_notification(self):
        """Test funding rate scan result notification."""
        print("\n📤 Testing Funding Rate Scan Result...")
        
        # Mock opportunities
        opportunities = [
            {
                'symbol': 'DOGEUSDT',
                'annual_fr': 0.125,  # 12.5%
                'position': 1  # LONG
            },
            {
                'symbol': 'BTCUSDT',
                'annual_fr': -0.08,  # -8%
                'position': -1  # SHORT
            },
            {
                'symbol': 'ETHUSDT',
                'annual_fr': 0.095,  # 9.5%
                'position': 1  # LONG
            }
        ]
        
        success = self.notifier.notify_scan_result(opportunities)
        
        if success:
            print("✅ Scan result notification sent successfully!")
        else:
            print("❌ Failed to send scan result notification")
            
        return success
        
    def run_all_tests(self):
        """Run all Discord notification tests."""
        print("🧪 Discord Real-time Notification Test Suite")
        print("=" * 60)
        print("⚠️  This will send actual messages to your Discord channel!")
        print("=" * 60)
        
        # Ask for confirmation
        response = input("\nDo you want to proceed? (y/N): ").strip().lower()
        if response not in ['y', 'yes']:
            print("❌ Test cancelled by user")
            return False
            
        tests = [
            ("Basic Message", self.test_basic_message),
            ("Rich Embed Message", self.test_embed_message),
            ("Trade Notification", self.test_trade_notification),
            ("Order Filled Notification", self.test_order_filled_notification),
            ("Risk Warning", self.test_risk_warning),
            ("Performance Report", self.test_performance_report),
            ("Strategy Status", self.test_strategy_status),
            ("Error Notification", self.test_error_notification),
            ("Position Alert", self.test_position_alert),
            ("Scan Result", self.test_scan_result_notification)
        ]
        
        results = {}
        
        for i, (test_name, test_func) in enumerate(tests, 1):
            print(f"\n🔍 Running test {i}/{len(tests)}: {test_name}")
            try:
                result = test_func()
                results[test_name] = result
                status = "✅ PASSED" if result else "❌ FAILED"
                print(f"{test_name}: {status}")
                
                # Add delay between tests to avoid rate limiting
                if i < len(tests):
                    print("⏳ Waiting 2 seconds before next test...")
                    time.sleep(2)
                    
            except Exception as e:
                print(f"❌ {test_name} failed with error: {e}")
                results[test_name] = False
                
        # Summary
        print("\n" + "=" * 60)
        print("📊 Test Results Summary:")
        
        passed = sum(1 for result in results.values() if result)
        total = len(results)
        
        for test_name, result in results.items():
            status = "✅ PASSED" if result else "❌ FAILED"
            print(f"  {test_name}: {status}")
            
        print(f"\nOverall: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All Discord notification tests passed!")
            print("📱 Check your Discord channel to see the message formats!")
        else:
            print("⚠️ Some tests failed. Check the output above for details.")
            
        return passed == total


def main():
    """Main test function."""
    tester = DiscordRealtimeTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
