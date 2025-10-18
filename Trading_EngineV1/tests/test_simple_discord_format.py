#!/usr/bin/env python3
"""
Test script for simple Discord notification formatting.
Tests the clean, table-style format you prefer.
"""

import sys
import os
import json
from datetime import datetime, timedelta

# Add the parent directory to the path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from monitor.discord_notifier import DiscordNotifier
from util.utils import load_config, setup_logging


class SimpleDiscordTester:
    """Test class for simple Discord notification formatting."""
    
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
        
    def format_account_summary(self):
        """Format account summary in simple table style."""
        message = """Accounts:
exchange    | account_value | position_value | leverage | available_balance
---------------------------------------------------------------------------
binance     |      2,084.56 |       3,205.40 |     1.54 |            963.73
bybit       |      1,964.23 |       4,157.69 |     2.12 |          3,699.21
bitget      |      2,064.08 |       3,073.37 |     1.49 |          5,182.95
---------------------------------------------------------------------------
     TOTAL  |      6,112.87 |      10,436.46 |     1.71 |          9,845.90"""
        
        return message
        
    def format_funding_rates(self):
        """Format funding rates in simple style."""
        message = """Funding Rates:
Weighted Funding Rate (8h): -132.4160%
Weighted Funding Rate (24h): 43.7187%
Weighted Funding Rate (72h): 158.1542%
Levered WFR (8h): -231.2319%
Levered WFR (24h): 35.5262%
Levered WFR (72h): 226.0747%"""
        
        return message
        
    def format_position_status(self):
        """Format position status in simple table style."""
        message = """Positions:
symbol      | side | quantity | entry_price | current_price | pnl | pnl_pct
---------------------------------------------------------------------------
DOGEUSDT    | LONG |   100.00 |      0.0800 |        0.0820 | 0.20 |   2.50%
BTCUSDT     | SHORT|     0.001|    45000.00 |      44800.00 | 0.20 |   0.44%
ETHUSDT     | LONG |     0.100|     3000.00 |       3020.00 | 2.00 |   0.67%
---------------------------------------------------------------------------
     TOTAL  |      |          |             |               | 2.40 |   1.87%"""
        
        return message
        
    def format_trade_notification(self):
        """Format trade notification in simple style."""
        message = """Trade Executed:
Symbol: DOGEUSDT
Side: BUY
Quantity: 100.00
Price: $0.0820
Order Type: LIMIT
Time: 2025-10-18 12:25:30
P&L: +$0.20 (+2.50%)"""
        
        return message
        
    def format_risk_alert(self):
        """Format risk alert in simple style."""
        message = """Risk Alert:
Symbol: DOGEUSDT
Alert Type: P&L Loss Threshold
Current P&L: -15.2%
Threshold: -10.0%
Position Value: $125.50
Entry Price: $0.0800
Current Price: $0.0678
Action: Consider closing position"""
        
        return message
        
    def format_performance_summary(self):
        """Format performance summary in simple style."""
        message = """Performance Summary:
Period: Last 24 Hours
Total Trades: 15
Win Rate: 73.3%
Net P&L: $45.20
Total Fees: $12.50
Profit Factor: 2.15
Best Trade: DOGEUSDT +$12.50
Worst Trade: BTCUSDT -$3.20
Max Drawdown: $8.50"""
        
        return message
        
    def test_simple_formats(self):
        """Test all simple format styles."""
        print("\n🧪 Testing Simple Discord Format Styles")
        print("=" * 50)
        
        tests = [
            ("Account Summary", self.format_account_summary),
            ("Funding Rates", self.format_funding_rates),
            ("Position Status", self.format_position_status),
            ("Trade Notification", self.format_trade_notification),
            ("Risk Alert", self.format_risk_alert),
            ("Performance Summary", self.format_performance_summary)
        ]
        
        for i, (test_name, format_func) in enumerate(tests, 1):
            print(f"\n📤 Test {i}: {test_name}")
            
            try:
                message = format_func()
                print(f"Message preview:\n{message[:100]}...")
                
                success = self.notifier.send_message(
                    content=f"```\n{message}\n```",
                    username="Trading Engine"
                )
                
                if success:
                    print(f"✅ {test_name} sent successfully!")
                else:
                    print(f"❌ Failed to send {test_name}")
                    
            except Exception as e:
                print(f"❌ {test_name} failed with error: {e}")
                
        print(f"\n🎉 Simple format testing completed!")
        print("📱 Check your Discord channel to see the clean table formats!")
        
        return True


def main():
    """Main test function."""
    tester = SimpleDiscordTester()
    success = tester.test_simple_formats()
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
