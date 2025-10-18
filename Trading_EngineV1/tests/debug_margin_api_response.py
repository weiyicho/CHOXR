#!/usr/bin/env python3
"""
Debug script to check the actual Binance margin order API response structure.
This will place a small test order and show the complete API response.
"""

import sys
import os
import json
import time
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.binance_sdk import BinanceFuturesClient
from util.utils import load_config


def debug_margin_api_response():
    """Debug the actual margin order API response structure."""
    
    try:
        # Setup client
        config = load_config("config/api.json")
        binance_config = config.get("binance", {})
        mock_exchange = type('MockExchange', (), {'id': 'binance'})()
        client = BinanceFuturesClient(binance_config, mock_exchange)
        
        print("🔍 Debugging Margin Order API Response Structure")
        print("=" * 60)
        
        # Get current price
        current_price = client.get_spot_price("DOGEUSDT")
        current_price = float(current_price)
        print(f"Current DOGEUSDT price: ${current_price:.4f}")
        
        # Calculate test order that meets minimum notional requirements
        min_notional = 5.0  # $5 minimum for DOGEUSDT
        test_quantity = int(min_notional / current_price) + 1  # Add 1 to ensure we meet minimum
        test_value = test_quantity * current_price
        print(f"Test order: {test_quantity} DOGE = ${test_value:.2f} (min notional: ${min_notional})")
        
        print("\n⚠️ This will place a REAL small test order on testnet")
        print("Proceeding automatically for debugging...")
        
        # Place small margin market order
        print(f"\n🚀 Placing test margin market BUY order...")
        order_result = client.place_margin_market_order(
            symbol="DOGEUSDT",
            side="BUY",
            quantity=test_quantity
        )
        
        print("✅ Test order placed successfully!")
        print(f"Order ID: {order_result.get('orderId', 'N/A')}")
        
        # Show the complete order placement response
        print("\n📊 COMPLETE ORDER PLACEMENT RESPONSE:")
        print("=" * 50)
        for key, value in order_result.items():
            print(f"  {key}: {value}")
        
        # Wait for order to process
        time.sleep(3)
        
        # Get order status
        order_id = order_result.get('orderId')
        if order_id:
            print(f"\n🔍 Getting order status for Order ID: {order_id}")
            order_status = client.get_margin_order_status(
                symbol="DOGEUSDT",
                order_id=order_id
            )
            
            print("\n📊 COMPLETE ORDER STATUS RESPONSE:")
            print("=" * 50)
            for key, value in order_status.items():
                print(f"  {key}: {value}")
            
            # Check specifically for price-related fields
            print("\n💰 PRICE-RELATED FIELDS:")
            print("=" * 30)
            price_fields = ['avgPrice', 'avg_price', 'price', 'averagePrice', 'cummulativeQuoteQty', 'executedQty']
            for field in price_fields:
                if field in order_status:
                    print(f"  {field}: {order_status[field]}")
                else:
                    print(f"  {field}: NOT FOUND")
            
            # Calculate average price if possible
            executed_qty = order_status.get('executedQty', 0)
            cummulative_quote_qty = order_status.get('cummulativeQuoteQty', 0)
            
            if executed_qty and cummulative_quote_qty:
                calculated_avg_price = float(cummulative_quote_qty) / float(executed_qty)
                print(f"\n🧮 CALCULATED AVERAGE PRICE:")
                print(f"  cummulativeQuoteQty / executedQty = {calculated_avg_price:.4f}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error debugging margin order response: {e}")
        return False


if __name__ == "__main__":
    debug_margin_api_response()
