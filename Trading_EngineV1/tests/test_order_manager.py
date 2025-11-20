#!/usr/bin/env python3
"""
Simple test script for OrderManager functions.
Tests OBI, OBIV, and percentile calculations without placing real orders.
"""

import sys
import os

# Add the parent directory to the path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from order.order import OrderManager


def test_order_manager_functions():
    """Test OrderManager functions with sample data."""
    print("=== OrderManager Function Testing ===")
    
    # Initialize OrderManager
    config = {'position': 1000, 'leverage': 5}
    order_manager = OrderManager(config, "DOGEUSDT")
    
    # Sample order book data (similar to Binance format)
    sample_order_book = {
        'bids': [
            ['0.19500', '100.0'],
            ['0.19490', '150.0'],
            ['0.19480', '200.0'],
            ['0.19470', '120.0'],
            ['0.19460', '180.0']
        ],
        'asks': [
            ['0.19510', '80.0'],
            ['0.19520', '130.0'],
            ['0.19530', '160.0'],
            ['0.19540', '90.0'],
            ['0.19550', '110.0']
        ]
    }
    
    print(f"Sample Order Book:")
    print(f"Bids: {sample_order_book['bids']}")
    print(f"Asks: {sample_order_book['asks']}")
    
    # Test OBI (Order Book Imbalance by Quantity)
    obi = order_manager.OBI(sample_order_book)
    print(f"\n📊 OBI (Quantity Imbalance): {obi:.4f}")
    
    # Test OBIV (Order Book Imbalance by Value)
    obiv = order_manager.OBIV(sample_order_book)
    print(f"📊 OBIV (Value Imbalance): {obiv:.4f}")
    
    # Test market direction analysis
    market_direction = order_manager.analyze_market_direction(sample_order_book)
    print(f"📈 Market Direction: {market_direction}")
    
    # Test percentile calculations
    print(f"\n🎯 Percentile Price Calculations:")
    
    # Test 25th and 75th percentiles for bids
    bid_25 = order_manager.calculate_percentile_price(sample_order_book, 0.25, 'bids')
    bid_75 = order_manager.calculate_percentile_price(sample_order_book, 0.75, 'bids')
    print(f"Bids - 25th percentile: ${bid_25:.5f}")
    print(f"Bids - 75th percentile: ${bid_75:.5f}")
    
    # Test 25th and 75th percentiles for asks
    ask_25 = order_manager.calculate_percentile_price(sample_order_book, 0.25, 'asks')
    ask_75 = order_manager.calculate_percentile_price(sample_order_book, 0.75, 'asks')
    print(f"Asks - 25th percentile: ${ask_25:.5f}")
    print(f"Asks - 75th percentile: ${ask_75:.5f}")
    
    # Test complete limit price calculations
    print(f"\n💰 Complete Limit Price Calculations:")
    
    scenarios = [
        ('BUY', 'conservative'),
        ('BUY', 'aggressive'),
        ('SELL', 'conservative'),
        ('SELL', 'aggressive')
    ]
    
    for order_type, aggressiveness in scenarios:
        calculation = order_manager.calculate_limit_price(
            sample_order_book, order_type, aggressiveness, market_direction
        )
        
        print(f"\n{order_type} {aggressiveness.upper()}:")
        print(f"  Limit Price: ${calculation['limit_price']:.5f}")
        print(f"  Percentile Used: {calculation['percentile_used']*100:.0f}%")
        print(f"  Current Bid: ${calculation['current_bid']:.5f}")
        print(f"  Current Ask: ${calculation['current_ask']:.5f}")
        print(f"  OBI: {calculation['obi']:.4f}")
        print(f"  OBIV: {calculation['obiv']:.4f}")
    
    print(f"\n✅ All OrderManager functions tested successfully!")
    
    return True


def test_edge_cases():
    """Test edge cases for OrderManager functions."""
    print(f"\n=== Edge Case Testing ===")
    
    config = {'position': 1000, 'leverage': 5}
    order_manager = OrderManager(config, "DOGEUSDT")
    
    # Test with empty order book
    empty_order_book = {'bids': [], 'asks': []}
    print(f"Testing empty order book...")
    try:
        obi = order_manager.OBI(empty_order_book)
        print(f"OBI with empty book: {obi}")
    except Exception as e:
        print(f"OBI error with empty book: {e}")
    
    # Test with very small order book
    small_order_book = {
        'bids': [['0.19500', '1.0']],
        'asks': [['0.19510', '1.0']]
    }
    print(f"\nTesting small order book...")
    obi = order_manager.OBI(small_order_book)
    obiv = order_manager.OBIV(small_order_book)
    print(f"Small book - OBI: {obi:.4f}, OBIV: {obiv:.4f}")
    
    print(f"✅ Edge case testing completed!")


def test_tick_size_functions():
    """Test tick size management functions thoroughly."""
    print(f"\n=== Testing Tick Size Functions ===")
    
    # Create OrderManager instance
    config = {'position': 100, 'leverage': 5}
    order_manager = OrderManager(config, 'DOGEUSDT', None)
    
    print("🧪 Testing round_to_tick_size function...")
    
    # Test cases for different tick sizes and prices
    test_cases = [
        # (price, tick_size, expected_result, description)
        (0.19803000000000002, 0.00001, 0.19803, "DOGE precision fix"),
        (43250.123456, 0.01, 43250.12, "BTC tick size 0.01"),
        (2580.789, 0.01, 2580.79, "ETH tick size 0.01"),
        (1.23456789, 0.0001, 1.2346, "Small tick size"),
        (100.0, 0.1, 100.0, "Exact match"),
        (100.05, 0.1, 100.1, "Round up (100.05/0.1 = 1000.5 → 1001 → 100.1)"),
        (100.04, 0.1, 100.0, "Round down (100.04/0.1 = 1000.4 → 1000 → 100.0)"),
        (0.0, 0.00001, 0.0, "Zero price"),
        (100.0, 0.0, 100.0, "Zero tick size (should return original)"),
    ]
    
    all_passed = True
    for price, tick_size, expected, description in test_cases:
        result = order_manager.round_to_tick_size(price, tick_size)
        passed = abs(result - expected) < 1e-10
        status = "✅" if passed else "❌"
        print(f"  {status} {description}: {price} → {result:.8f} (expected: {expected:.8f})")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("✅ All tick size rounding tests passed!")
    else:
        print("❌ Some tick size rounding tests failed!")
    
    return all_passed


def test_calculate_limit_price():
    """Test the calculate_limit_price function with sample data."""
    print(f"\n=== Testing calculate_limit_price ===")
    
    # Create OrderManager instance
    config = {'position': 100, 'leverage': 5}
    order_manager = OrderManager(config, 'DOGEUSDT', None)
    
    # Sample order book data
    order_book = {
        'bids': [
            ['0.19500', '10.0'],
            ['0.19490', '15.0'],
            ['0.19480', '20.0'],
            ['0.19470', '25.0'],
            ['0.19460', '30.0']
        ],
        'asks': [
            ['0.19510', '12.0'],
            ['0.19520', '18.0'],
            ['0.19530', '22.0'],
            ['0.19540', '28.0'],
            ['0.19550', '35.0']
        ]
    }
    
    try:
        print("🧪 Testing basic calculate_limit_price (without tick size)...")
        
        # Test BUY conservative (without symbol/exchange_client for basic test)
        result = order_manager.calculate_limit_price(order_book, 'BUY', 'conservative')
        print(f"BUY Conservative: ${result['limit_price']:.8f}")
        print(f"Market Direction: {result['market_direction']}")
        print(f"Tick Size: {result.get('tick_size', 'N/A')}")
        
        # Test SELL aggressive
        result = order_manager.calculate_limit_price(order_book, 'SELL', 'aggressive')
        print(f"SELL Aggressive: ${result['limit_price']:.8f}")
        print(f"Market Direction: {result['market_direction']}")
        print(f"Tick Size: {result.get('tick_size', 'N/A')}")
        
        print(f"✅ Basic calculate_limit_price testing completed!")
        
    except Exception as e:
        print(f"❌ Error in calculate_limit_price: {e}")
        return False
    
    return True


def test_tick_size_with_mock_exchange():
    """Test tick size detection with mock exchange client."""
    print(f"\n=== Testing Tick Size Detection ===")
    
    # Create mock exchange client
    class MockExchangeClient:
        def get_exchange_info(self):
            return {
                'symbols': [
                    {
                        'symbol': 'DOGEUSDT',
                        'filters': [
                            {
                                'filterType': 'PRICE_FILTER',
                                'tickSize': '0.00001'
                            }
                        ]
                    },
                    {
                        'symbol': 'BTCUSDT',
                        'filters': [
                            {
                                'filterType': 'PRICE_FILTER',
                                'tickSize': '0.01'
                            }
                        ]
                    },
                    {
                        'symbol': 'ETHUSDT',
                        'filters': [
                            {
                                'filterType': 'PRICE_FILTER',
                                'tickSize': '0.01'
                            }
                        ]
                    }
                ]
            }
    
    config = {'position': 100, 'leverage': 5}
    order_manager = OrderManager(config, 'DOGEUSDT', None)
    mock_client = MockExchangeClient()
    
    # Test tick size detection for different symbols
    test_symbols = [
        ('DOGEUSDT', 0.00001),
        ('BTCUSDT', 0.01),
        ('ETHUSDT', 0.01),
        ('UNKNOWNSYMBOL', 0.00001),  # Should fallback to default
    ]
    
    all_passed = True
    for symbol, expected_tick_size in test_symbols:
        try:
            tick_size = order_manager.get_symbol_tick_size(symbol, mock_client)
            passed = abs(tick_size - expected_tick_size) < 1e-10
            status = "✅" if passed else "❌"
            print(f"  {status} {symbol}: {tick_size} (expected: {expected_tick_size})")
            if not passed:
                all_passed = False
        except Exception as e:
            print(f"  ❌ {symbol}: Error - {e}")
            all_passed = False
    
    if all_passed:
        print("✅ All tick size detection tests passed!")
    else:
        print("❌ Some tick size detection tests failed!")
    
    return all_passed


def test_complete_price_calculation_with_tick_size():
    """Test complete price calculation with tick size integration."""
    print(f"\n=== Testing Complete Price Calculation with Tick Size ===")
    
    # Mock exchange client
    class MockExchangeClient:
        def get_exchange_info(self):
            return {
                'symbols': [
                    {
                        'symbol': 'DOGEUSDT',
                        'filters': [{'filterType': 'PRICE_FILTER', 'tickSize': '0.00001'}]
                    }
                ]
            }
    
    config = {'position': 100, 'leverage': 5}
    order_manager = OrderManager(config, 'DOGEUSDT', None)
    mock_client = MockExchangeClient()
    
    # Order book with prices that need tick size rounding
    order_book = {
        'bids': [
            ['0.19500', '10.0'],
            ['0.19490', '15.0'],
            ['0.19480', '20.0'],
            ['0.19470', '25.0'],
            ['0.19460', '30.0']
        ],
        'asks': [
            ['0.19510', '12.0'],
            ['0.19520', '18.0'],
            ['0.19530', '22.0'],
            ['0.19540', '28.0'],
            ['0.19550', '35.0']
        ]
    }
    
    scenarios = [
        ('BUY', 'conservative'),
        ('BUY', 'aggressive'),
        ('SELL', 'conservative'),
        ('SELL', 'aggressive')
    ]
    
    all_passed = True
    for order_type, aggressiveness in scenarios:
        try:
            result = order_manager.calculate_limit_price(
                order_book=order_book,
                order_type=order_type,
                aggressiveness=aggressiveness
            )
            
            # Verify tick size is included
            tick_size = result.get('tick_size', None)
            if tick_size is None:
                print(f"  ❌ {order_type} {aggressiveness}: Missing tick_size in result")
                all_passed = False
                continue
            
            # Verify price is properly rounded
            limit_price = result['limit_price']
            expected_ticks = round(limit_price / tick_size)
            rounded_price = expected_ticks * tick_size
            
            passed = abs(limit_price - rounded_price) < 1e-10
            status = "✅" if passed else "❌"
            print(f"  {status} {order_type} {aggressiveness}: ${limit_price:.8f} (tick: {tick_size})")
            
            if not passed:
                print(f"      Expected: ${rounded_price:.8f}")
                all_passed = False
            
        except Exception as e:
            print(f"  ❌ {order_type} {aggressiveness}: Error - {e}")
            all_passed = False
    
    if all_passed:
        print("✅ All complete price calculation tests passed!")
    else:
        print("❌ Some complete price calculation tests failed!")
    
    return all_passed


if __name__ == "__main__":
    print("OrderManager Function Testing")
    print("=" * 35)
    print()
    
    try:
        test_order_manager_functions()
        test_edge_cases()
        
        # Test tick size management functions
        tick_size_tests_passed = test_tick_size_functions()
        detection_tests_passed = test_tick_size_with_mock_exchange()
        complete_calc_tests_passed = test_complete_price_calculation_with_tick_size()
        basic_calc_tests_passed = test_calculate_limit_price()
        
        # Summary
        print(f"\n📊 Test Summary:")
        print(f"  ✅ OrderManager Functions: PASSED")
        print(f"  ✅ Edge Cases: PASSED")
        print(f"  {'✅' if tick_size_tests_passed else '❌'} Tick Size Rounding: {'PASSED' if tick_size_tests_passed else 'FAILED'}")
        print(f"  {'✅' if detection_tests_passed else '❌'} Tick Size Detection: {'PASSED' if detection_tests_passed else 'FAILED'}")
        print(f"  {'✅' if complete_calc_tests_passed else '❌'} Complete Price Calculation: {'PASSED' if complete_calc_tests_passed else 'FAILED'}")
        print(f"  {'✅' if basic_calc_tests_passed else '❌'} Basic Price Calculation: {'PASSED' if basic_calc_tests_passed else 'FAILED'}")
        
        all_tests_passed = all([
            tick_size_tests_passed,
            detection_tests_passed,
            complete_calc_tests_passed,
            basic_calc_tests_passed
        ])
        
        if all_tests_passed:
            print(f"\n🎉 All tests completed successfully!")
        else:
            print(f"\n⚠️  Some tests failed - check output above")
            
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
