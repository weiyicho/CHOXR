#!/usr/bin/env python3
"""
Test script to explore Binance account data structure and available information.
This will help us understand what data is available for RiskManager integration.
"""

import sys
import os
import json
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.binance_sdk import BinanceFuturesClient
from util.utils import load_config


class BinanceAccountDataExplorer:
    """Explore Binance account data to understand available information."""
    
    def __init__(self):
        """Initialize the explorer."""
        self.client = None
        self.account_data = {}
        self.positions_data = {}
        self.balance_data = {}
        
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
    
    def explore_account_info(self):
        """Explore account information data structure."""
        print("\n🔍 Exploring Account Information...")
        print("=" * 50)
        
        try:
            # Get account information
            account_info = self.client.get_account_info()
            self.account_data = account_info
            
            print("📊 Account Information Structure:")
            print(f"Keys available: {list(account_info.keys())}")
            
            # Display key account metrics
            print("\n💰 Key Account Metrics:")
            for key, value in account_info.items():
                print(f"  {key}: {value}")
            
            return account_info
            
        except Exception as e:
            print(f"❌ Error getting account info: {e}")
            return {}
    
    def explore_positions(self):
        """Explore positions data structure."""
        print("\n🔍 Exploring Positions Data...")
        print("=" * 50)
        
        try:
            # Get positions
            positions = self.client.get_positions()
            self.positions_data = positions
            
            print(f"📈 Positions Data Structure:")
            print(f"Number of positions: {len(positions)}")
            
            if positions:
                print(f"Sample position keys: {list(positions[0].keys())}")
                
                print("\n📊 Position Details:")
                for i, pos in enumerate(positions[:3]):  # Show first 3 positions
                    print(f"\nPosition {i+1}:")
                    for key, value in pos.items():
                        if key in ['symbol', 'initialMargin', 'maintMargin', 'unrealizedProfit', 
                                  'positionInitialMargin', 'openOrderInitialMargin', 'crossWalletBalance',
                                  'crossUnPnl', 'positionSide', 'entryPrice', 'markPrice', 'positionAmt',
                                  'notional', 'isolatedWallet', 'updateTime']:
                            print(f"  {key}: {value}")
            
            return positions
            
        except Exception as e:
            print(f"❌ Error getting positions: {e}")
            return []
    
    def explore_balance(self):
        """Explore balance data structure."""
        print("\n🔍 Exploring Balance Data...")
        print("=" * 50)
        
        try:
            # Get balance
            balance = self.client.get_balances()
            self.balance_data = balance
            
            print(f"💳 Balance Data Structure:")
            print(f"Number of assets: {len(balance)}")
            
            if balance:
                print(f"Sample balance keys: {list(balance[0].keys())}")
                
                print("\n💰 Balance Details (all assets):")
                for asset in balance:
                    print(f"\nAsset: {asset.get('asset', 'N/A')}")
                    for key, value in asset.items():
                        print(f"  {key}: {value}")
            
            return balance
            
        except Exception as e:
            print(f"❌ Error getting balance: {e}")
            return []
    
    def explore_exchange_info(self):
        """Explore exchange info for symbol data."""
        print("\n🔍 Exploring Exchange Info...")
        print("=" * 50)
        
        try:
            # Get exchange info
            exchange_info = self.client.get_exchange_info()
            
            print(f"📊 Exchange Info Structure:")
            print(f"Keys available: {list(exchange_info.keys())}")
            
            if 'symbols' in exchange_info:
                print(f"Number of symbols: {len(exchange_info['symbols'])}")
                
                # Find DOGEUSDT symbol info
                doge_symbol = None
                for symbol in exchange_info['symbols']:
                    if symbol['symbol'] == 'DOGEUSDT':
                        doge_symbol = symbol
                        break
                
                if doge_symbol:
                    print(f"\n🐕 DOGEUSDT Symbol Info:")
                    for key, value in doge_symbol.items():
                        if key in ['symbol', 'status', 'baseAsset', 'quoteAsset', 'baseAssetPrecision',
                                  'quotePrecision', 'orderTypes', 'filters']:
                            if key == 'filters':
                                print(f"  {key}: {len(value)} filters")
                                for filter_info in value:
                                    if filter_info['filterType'] in ['LOT_SIZE', 'PRICE_FILTER', 'MIN_NOTIONAL']:
                                        print(f"    {filter_info['filterType']}: {filter_info}")
                            else:
                                print(f"  {key}: {value}")
            
            return exchange_info
            
        except Exception as e:
            print(f"❌ Error getting exchange info: {e}")
            return {}
    
    def analyze_data_for_risk_manager(self):
        """Analyze what data is available for RiskManager integration."""
        print("\n🔍 Analyzing Data for RiskManager Integration...")
        print("=" * 50)
        
        print("📋 Data Available for RiskManager:")
        
        # Account data analysis
        if self.account_data:
            print("\n✅ Account Data Available:")
            print("  - Total wallet balance")
            print("  - Total unrealized profit")
            print("  - Total margin balance")
            print("  - Total initial margin")
            print("  - Total maintenance margin")
            print("  - Available balance")
            print("  - Max withdraw amount")
        
        # Positions data analysis
        if self.positions_data:
            print("\n✅ Positions Data Available:")
            print("  - Individual position details")
            print("  - Position margins")
            print("  - Unrealized P&L per position")
            print("  - Position sizes and entry prices")
            print("  - Cross wallet balances")
        
        # Balance data analysis
        if self.balance_data:
            print("\n✅ Balance Data Available:")
            print("  - Asset balances")
            print("  - Cross wallet balances")
            print("  - Available balances per asset")
            print("  - Max withdraw amounts per asset")
        
        # Missing data analysis
        print("\n✅ Data Available for RiskManager:")
        print("  - Portfolio margin account status (accountStatus)")
        print("  - Unified maintenance margin rate (uniMMR)")
        print("  - Account equity and actual equity")
        print("  - Initial and maintenance margins")
        print("  - Available balance and max withdraw")
        print("  - Margin open loss")
        
        print("\n❌ Data Missing for RiskManager:")
        print("  - Individual position details (when positions exist)")
        print("  - Position-specific risk metrics")
        print("  - Historical performance data")
        print("  - Advanced liquidation risk calculations")
        
        print("\n💡 Recommendations:")
        print("  1. Use existing account data for basic risk calculations")
        print("  2. Add portfolio margin API calls for advanced risk metrics")
        print("  3. Implement position sizing logic in RiskManager")
        print("  4. Add account status monitoring")
    
    def save_data_sample(self):
        """Save sample data for analysis."""
        sample_data = {
            "timestamp": datetime.now().isoformat(),
            "account_data": self.account_data,
            "positions_data": self.positions_data,
            "balance_data": self.balance_data
        }
        
        filename = f"tests/results/binance_account_data_sample_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w') as f:
            json.dump(sample_data, f, indent=2, default=str)
        
        print(f"\n💾 Sample data saved to: {filename}")
        return filename
    
    def run_exploration(self):
        """Run complete data exploration."""
        print("🚀 Starting Binance Account Data Exploration")
        print("=" * 60)
        
        if not self.setup_client():
            return False
        
        # Explore all data types
        self.explore_account_info()
        self.explore_positions()
        self.explore_balance()
        self.explore_exchange_info()
        
        # Analyze for RiskManager integration
        self.analyze_data_for_risk_manager()
        
        # Save sample data
        self.save_data_sample()
        
        print("\n✅ Data exploration completed!")
        return True


def main():
    """Main function."""
    explorer = BinanceAccountDataExplorer()
    explorer.run_exploration()


if __name__ == "__main__":
    main()
