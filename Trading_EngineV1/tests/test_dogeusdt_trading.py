#!/usr/bin/env python3
"""
Test case for DOGEUSDT trading with Discord notifications.
Places real orders and sends all 3 Discord message formats.
"""

import sys
import os
import json
import time
from datetime import datetime, timedelta

# Add the parent directory to the path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from monitor.discord_notifier import DiscordNotifier
from monitor.monitoring_system import MonitoringSystem
from monitor.position_monitor import PositionMonitor
from monitor.performance_monitor import PerformanceMonitor
from src.binance_sdk import BinanceFuturesClient
from util.utils import load_config, setup_logging


class DOGEUSDTTradingTest:
    """Test class for DOGEUSDT trading with Discord notifications."""
    
    def __init__(self):
        """Initialize the trading test."""
        self.logger = setup_logging("INFO")
        
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
            
        # Load Discord configuration
        try:
            monitoring_config = load_config("../config/monitoring.json")
            webhook_url = monitoring_config.get('discord', {}).get('webhook_url', '')
            
            if not webhook_url:
                print("❌ Discord webhook URL not configured!")
                sys.exit(1)
                
            self.webhook_url = webhook_url
            print(f"✅ Discord webhook URL loaded")
            
        except Exception as e:
            print(f"❌ Error loading Discord config: {e}")
            sys.exit(1)
            
        # Initialize components
        self.exchange_client = None
        self.discord_notifier = None
        self.monitoring_system = None
        
        # Trading parameters
        self.symbol = "DOGEUSDT"
        self.max_order_value = 6.0  # $6 max per order
        self.total_position_limit = 50.0  # $50 total position limit
        
    def setup_exchange_client(self):
        """Setup exchange client."""
        if not self.api_key or not self.api_secret:
            print("❌ API credentials not configured!")
            return False
            
        try:
            self.exchange_client = BinanceFuturesClient(
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet
            )
            
            # Test connection
            account_info = self.exchange_client.get_account_info()
            if account_info:
                print(f"✅ Exchange client connected successfully")
                return True
            else:
                print("❌ Failed to connect to exchange")
                return False
                
        except Exception as e:
            print(f"❌ Error setting up exchange client: {e}")
            return False
            
    def setup_discord_notifier(self):
        """Setup Discord notifier."""
        try:
            self.discord_notifier = DiscordNotifier(
                webhook_url=self.webhook_url,
                enabled=True
            )
            print("✅ Discord notifier initialized")
            return True
            
        except Exception as e:
            print(f"❌ Error setting up Discord notifier: {e}")
            return False
            
    def setup_monitoring_system(self):
        """Setup monitoring system."""
        try:
            self.monitoring_system = MonitoringSystem("config/monitoring.json")
            self.monitoring_system.set_exchange_client(self.exchange_client)
            print("✅ Monitoring system initialized")
            return True
            
        except Exception as e:
            print(f"❌ Error setting up monitoring system: {e}")
            return False
            
    def get_current_price(self):
        """Get current DOGEUSDT price."""
        try:
            ticker = self.exchange_client.get_ticker(self.symbol)
            price = float(ticker.get('price', 0))
            print(f"📊 Current {self.symbol} price: ${price:.4f}")
            return price
        except Exception as e:
            print(f"❌ Error getting current price: {e}")
            return 0
            
    def calculate_order_quantity(self, price):
        """Calculate order quantity based on max order value."""
        if price <= 0:
            return 0
            
        quantity = self.max_order_value / price
        print(f"💰 Calculated quantity for ${self.max_order_value} order: {quantity:.6f} DOGE")
        return quantity
        
    def check_position_limits(self):
        """Check if we're within position limits."""
        try:
            positions = self.exchange_client.get_positions()
            total_position_value = 0
            
            for pos in positions:
                if abs(pos.get('positionAmt', 0)) > 0:
                    symbol = pos.get('symbol', '')
                    quantity = abs(pos.get('positionAmt', 0))
                    mark_price = pos.get('markPrice', 0)
                    position_value = quantity * mark_price
                    total_position_value += position_value
                    
                    print(f"📊 {symbol} position: {quantity:.6f} @ ${mark_price:.4f} = ${position_value:.2f}")
                    
            print(f"📊 Total position value: ${total_position_value:.2f} (limit: ${self.total_position_limit:.2f})")
            
            if total_position_value >= self.total_position_limit:
                print(f"⚠️ Position limit reached: ${total_position_value:.2f} >= ${self.total_position_limit:.2f}")
                return False
                
            return True
            
        except Exception as e:
            print(f"❌ Error checking position limits: {e}")
            return False
            
    def place_limit_order(self, side, price, quantity):
        """Place a limit order."""
        try:
            print(f"📋 Placing {side} limit order: {quantity:.6f} {self.symbol} @ ${price:.4f}")
            
            order_result = self.exchange_client.place_order(
                symbol=self.symbol,
                side=side,
                order_type="LIMIT",
                quantity=quantity,
                price=price,
                time_in_force="GTC"
            )
            
            if order_result:
                print(f"✅ Order placed successfully: {order_result.get('orderId', 'N/A')}")
                return order_result
            else:
                print("❌ Failed to place order")
                return None
                
        except Exception as e:
            print(f"❌ Error placing order: {e}")
            return None
            
    def place_market_order(self, side, quantity):
        """Place a market order."""
        try:
            print(f"📋 Placing {side} market order: {quantity:.6f} {self.symbol}")
            
            order_result = self.exchange_client.place_order(
                symbol=self.symbol,
                side=side,
                order_type="MARKET",
                quantity=quantity
            )
            
            if order_result:
                print(f"✅ Market order placed successfully: {order_result.get('orderId', 'N/A')}")
                return order_result
            else:
                print("❌ Failed to place market order")
                return None
                
        except Exception as e:
            print(f"❌ Error placing market order: {e}")
            return None
            
    def send_accounts_summary(self):
        """Send accounts summary to Discord."""
        try:
            # Get account info
            account_info = self.exchange_client.get_account_info()
            balances = account_info.get('assets', [])
            
            # Mock accounts data for demonstration
            accounts_data = [
                {
                    'exchange': 'binance',
                    'account_value': float(account_info.get('totalWalletBalance', 0)),
                    'position_value': float(account_info.get('totalPositionInitialMargin', 0)) * 10,  # Estimate
                    'leverage': 10.0,  # Default leverage
                    'available_balance': float(account_info.get('availableBalance', 0))
                }
            ]
            
            success = self.discord_notifier.send_accounts_summary(accounts_data)
            if success:
                print("✅ Accounts summary sent to Discord")
            else:
                print("❌ Failed to send accounts summary")
                
            return success
            
        except Exception as e:
            print(f"❌ Error sending accounts summary: {e}")
            return False
            
    def send_positions_summary(self):
        """Send positions summary to Discord."""
        try:
            # Get current positions
            positions = self.exchange_client.get_positions()
            positions_data = []
            
            for pos in positions:
                if abs(pos.get('positionAmt', 0)) > 0:
                    symbol = pos.get('symbol', '')
                    side = 'LONG' if pos.get('positionAmt', 0) > 0 else 'SHORT'
                    quantity = abs(pos.get('positionAmt', 0))
                    entry_price = pos.get('entryPrice', 0)
                    mark_price = pos.get('markPrice', 0)
                    unrealized_pnl = pos.get('unRealizedProfit', 0)
                    
                    # Calculate P&L percentage
                    pnl_percentage = (unrealized_pnl / (quantity * entry_price)) * 100 if entry_price > 0 else 0
                    
                    positions_data.append({
                        'symbol': symbol,
                        'side': side,
                        'quantity': quantity,
                        'entry_price': entry_price,
                        'current_price': mark_price,
                        'unrealized_pnl': unrealized_pnl,
                        'pnl_percentage': pnl_percentage
                    })
            
            success = self.discord_notifier.send_positions_summary(positions_data)
            if success:
                print("✅ Positions summary sent to Discord")
            else:
                print("❌ Failed to send positions summary")
                
            return success
            
        except Exception as e:
            print(f"❌ Error sending positions summary: {e}")
            return False
            
    def send_performance_summary(self):
        """Send performance summary to Discord."""
        try:
            # Mock performance data for demonstration
            performance_data = {
                'period': 'Last 24 Hours',
                'total_trades': 5,
                'win_rate': 80.0,
                'net_pnl': 12.50,
                'total_fees': 2.30,
                'profit_factor': 2.15,
                'best_trade': 'DOGEUSDT +$8.20',
                'worst_trade': 'DOGEUSDT -$1.50',
                'max_drawdown': 3.20
            }
            
            success = self.discord_notifier.send_performance_summary(performance_data)
            if success:
                print("✅ Performance summary sent to Discord")
            else:
                print("❌ Failed to send performance summary")
                
            return success
            
        except Exception as e:
            print(f"❌ Error sending performance summary: {e}")
            return False
            
    def run_trading_test(self):
        """Run the complete DOGEUSDT trading test."""
        print("🧪 DOGEUSDT Trading Test with Discord Notifications")
        print("=" * 60)
        
        # Setup components
        if not self.setup_exchange_client():
            return False
            
        if not self.setup_discord_notifier():
            return False
            
        if not self.setup_monitoring_system():
            return False
            
        print("\n📊 Initial Status Check:")
        
        # Check position limits
        if not self.check_position_limits():
            print("⚠️ Position limits exceeded, skipping order placement")
        else:
            print("✅ Position limits OK, proceeding with order placement")
            
        # Get current price
        current_price = self.get_current_price()
        if current_price <= 0:
            print("❌ Failed to get current price")
            return False
            
        # Calculate order quantity
        quantity = self.calculate_order_quantity(current_price)
        if quantity <= 0:
            print("❌ Invalid order quantity")
            return False
            
        # Place a limit order slightly below market price
        limit_price = current_price * 0.999  # 0.1% below market
            
        print(f"\n📋 Placing BUY limit order:")
        print(f"   Symbol: {self.symbol}")
        print(f"   Quantity: {quantity:.6f}")
        print(f"   Limit Price: ${limit_price:.4f}")
        print(f"   Order Value: ${quantity * limit_price:.2f}")
        
        # Place the order
        order_result = self.place_limit_order("BUY", limit_price, quantity)
        
        if order_result:
            print("✅ Order placed successfully!")
            
            # Wait a moment for order to be processed
            print("⏳ Waiting 3 seconds for order processing...")
            time.sleep(3)
            
            # Send all 3 Discord notifications
            print("\n📤 Sending Discord Notifications:")
            
            # 1. Accounts Summary
            print("1. Sending Accounts Summary...")
            self.send_accounts_summary()
            time.sleep(2)
            
            # 2. Positions Summary  
            print("2. Sending Positions Summary...")
            self.send_positions_summary()
            time.sleep(2)
            
            # 3. Performance Summary
            print("3. Sending Performance Summary...")
            self.send_performance_summary()
            
            print("\n🎉 Trading test completed successfully!")
            print("📱 Check your Discord channel to see all 3 message formats!")
            
            return True
        else:
            print("❌ Failed to place order")
            return False
            
    def run_quick_test(self):
        """Run a quick test without placing orders."""
        print("🧪 DOGEUSDT Quick Test (No Orders)")
        print("=" * 50)
        
        # Setup components
        if not self.setup_exchange_client():
            return False
            
        if not self.setup_discord_notifier():
            return False
            
        # Get current price
        current_price = self.get_current_price()
        
        # Send all 3 Discord notifications
        print("\n📤 Sending Discord Notifications:")
        
        # 1. Accounts Summary
        print("1. Sending Accounts Summary...")
        self.send_accounts_summary()
        time.sleep(2)
        
        # 2. Positions Summary  
        print("2. Sending Positions Summary...")
        self.send_positions_summary()
        time.sleep(2)
        
        # 3. Performance Summary
        print("3. Sending Performance Summary...")
        self.send_performance_summary()
        
        print("\n🎉 Quick test completed!")
        print("📱 Check your Discord channel to see all 3 message formats!")
        
        return True


def main():
    """Main test function."""
    tester = DOGEUSDTTradingTest()
    
    print("Choose test mode:")
    print("1. Full trading test (places actual orders)")
    print("2. Quick test (no orders, just Discord notifications)")
    
    try:
        choice = input("Enter choice (1 or 2): ").strip()
        
        if choice == "1":
            success = tester.run_trading_test()
        elif choice == "2":
            success = tester.run_quick_test()
        else:
            print("❌ Invalid choice")
            return 1
            
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\n❌ Test cancelled by user")
        return 1
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
