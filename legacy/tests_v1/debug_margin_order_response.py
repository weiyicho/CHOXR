#!/usr/bin/env python3
"""
Debug script to check the actual Binance margin order API response structure.
This will help identify the correct field names for average price.
"""

import sys
import os
import json
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.binance_sdk import BinanceFuturesClient
from util.utils import load_config


def debug_margin_order_response():
    """Debug the actual margin order API response structure."""
    
    try:
        # Setup client
        config = load_config("config/api.json")
        binance_config = config.get("binance", {})
        mock_exchange = type('MockExchange', (), {'id': 'binance'})()
        client = BinanceFuturesClient(binance_config, mock_exchange)
        
        print("🔍 Debugging Margin Order API Response Structure")
        print("=" * 60)
        
        # Get open margin orders to see the structure
        print("📋 Getting open margin orders structure...")
        open_orders = client.get_open_margin_orders(symbol="DOGEUSDT")
        
        print(f"Number of open orders: {len(open_orders)}")
        
        if open_orders:
            print("\n📊 Sample open order structure:")
            sample_order = open_orders[0]
            for key, value in sample_order.items():
                print(f"  {key}: {value} (type: {type(value).__name__})")
        else:
            print("No open orders found - this is expected")
        
        # If we have an order ID from recent test, check its status
        print("\n📋 Checking recent order status structure...")
        
        # Try to get order status for a recent order (you can replace with actual order ID)
        # For now, let's just check what fields are available in the API response
        
        print("\n💡 Expected field names for average price in Binance API:")
        print("  - avgPrice: Average execution price")
        print("  - price: Order price (for limit orders)")
        print("  - cummulativeQuoteQty: Total quote asset traded")
        print("  - executedQty: Total base asset traded")
        
        print("\n🔍 If avgPrice is N/A, it might be:")
        print("  1. Field name is different (e.g., 'avg_price' instead of 'avgPrice')")
        print("  2. Field exists but has null/empty value")
        print("  3. Field doesn't exist in margin order response")
        
        # Let's also check the place_margin_market_order response structure
        print("\n📋 Place margin market order response structure:")
        print("This would show the structure when placing an order")
        
        return True
        
    except Exception as e:
        print(f"❌ Error debugging margin order response: {e}")
        return False


if __name__ == "__main__":
    debug_margin_order_response()
