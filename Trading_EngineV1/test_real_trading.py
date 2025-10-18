#!/usr/bin/env python3
"""
Real trading test script that sends actual orders to the market.
Tests limit order execution timing and automatically closes positions.
"""

import sys
import os
import json
import time
from datetime import datetime, timezone

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.binance_sdk import BinanceFuturesClient
from order.order import OrderManager
from util.utils import load_config, setup_logging


class RealTradingTester:
    """Real trading test with actual order placement and timing analysis."""
    
    def __init__(self, config_path: str = "config/api.json", symbol: str = "DOGEUSDT"):
        """Initialize the real trading tester."""
        self.config_path = config_path
        self.symbol = symbol
        self.config = None
        self.client = None
        self.order_manager = None
        self.logger = setup_logging("INFO")
        self.test_results = []
        
    def load_configuration(self):
        """Load API configuration."""
        try:
            self.config = load_config(self.config_path)
            self.logger.info("Configuration loaded successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            return False
    
    def initialize_client(self):
        """Initialize Binance client and OrderManager."""
        try:
            binance_config = self.config.get("binance", {})
            mock_exchange = type('MockExchange', (), {'id': 'binance'})()
            
            self.client = BinanceFuturesClient(binance_config, mock_exchange)
            
            order_config = {'position': 50, 'leverage': 5}
            self.order_manager = OrderManager(order_config, self.symbol, self.client)
            
            self.logger.info("Binance client and OrderManager initialized successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize client: {e}")
            return False
    
    def analyze_order_book_and_calculate_price(self, symbol: str = None):
        """Analyze order book and calculate optimal limit price."""
        if not symbol:
            symbol = self.symbol
        
        start_time = time.time()
        
        # Get order book data
        order_book = self.client.get_order_book(symbol, limit=20)
        ob_book_time = time.time()
        
        # Perform analysis
        obi = self.order_manager.OBI(order_book)
        obiv = self.order_manager.OBIV(order_book)
        market_direction = self.order_manager.analyze_market_direction(order_book)
        analysis_time = time.time()
        
        # Calculate current market price for quantity calculation
        current_bid = float(order_book['bids'][0][0])
        current_ask = float(order_book['asks'][0][0])
        current_price = (current_bid + current_ask) / 2
        
        # Calculate safe quantity ($6 max per order, $50 total position limit)
        max_order_value = 6.0
        max_total_position = 50.0
        safe_quantity = max_order_value / current_price
        
        # Get precision rules
        exchange_info = self.client.get_exchange_info()
        symbol_info = None
        for s in exchange_info.get('symbols', []):
            if s.get('symbol') == symbol:
                symbol_info = s
                break
        
        if symbol_info:
            lot_size_filter = next((f for f in symbol_info.get('filters', []) if f.get('filterType') == 'LOT_SIZE'), None)
            if lot_size_filter:
                step_size = float(lot_size_filter.get('stepSize', '1.0'))
                min_qty = float(lot_size_filter.get('minQty', '1.0'))
                safe_quantity = round(safe_quantity / step_size) * step_size
                safe_quantity = max(safe_quantity, min_qty)
        
        precision_time = time.time()
        
        self.logger.info(f"📊 Market Analysis:")
        self.logger.info(f"   OBI: {obi:.4f}, OBIV: {obiv:.4f}")
        self.logger.info(f"   Market Direction: {market_direction}")
        self.logger.info(f"   Current Price: ${current_price:.6f}")
        self.logger.info(f"   Quantity: {safe_quantity}")
        
        timing = {
            'order_book_time': ob_book_time - start_time,
            'analysis_time': analysis_time - ob_book_time,
            'precision_time': precision_time - analysis_time,
            'total_analysis_time': precision_time - start_time
        }
        
        return {
            'order_book': order_book,
            'obi': obi,
            'obiv': obiv,
            'market_direction': market_direction,
            'current_bid': current_bid,
            'current_ask': current_ask,
            'current_price': current_price,
            'quantity': safe_quantity,
            'timing': timing
        }
    
    def execute_limit_order_cycle(self, symbol: str = None, order_type: str = "BUY", 
                                 aggressiveness: str = "conservative"):
        """Execute complete limit order cycle with timing analysis."""
        if not symbol:
            symbol = self.symbol
            
        self.logger.info(f"\n🚀 Starting {order_type} {aggressiveness} Limit Order Cycle")
        
        cycle_start_time = time.time()
        
        # Step 1: Analyze market and calculate price
        analysis_start = time.time()
        analysis = self.analyze_order_book_and_calculate_price(symbol)
        analysis_end = time.time()
        
        # Step 2: Calculate limit price
        price_calc_start = time.time()
        calculation = self.order_manager.calculate_limit_price(
            analysis['order_book'], order_type, aggressiveness, analysis['market_direction'], self.symbol, self.client
        )
        price_calc_end = time.time()
        
        self.logger.info(f"🎯 Calculated Limit Price: ${calculation['limit_price']:.6f}")
        self.logger.info(f"   vs Current Ask: ${calculation['current_ask']:.6f}")
        self.logger.info(f"   vs Current Bid: ${calculation['current_bid']:.6f}")
        
        # Step 3: Check position limits before placing order
        order_value = analysis['quantity'] * calculation['limit_price']
        if not self.check_position_limits(symbol, order_value):
            self.logger.warning("⏭️  Skipping order due to position limits")
            return None
        
        # Step 4: Place limit order
        order_place_start = time.time()
        self.logger.info(f"📤 Placing {order_type} limit order...")
        self.logger.info(f"   Order Value: ${order_value:.2f}")
        
        limit_order_result = self.client.place_limit_order(
            symbol=symbol,
            side=order_type,
            price=calculation['limit_price'],
            quantity=analysis['quantity'],
            time_in_force='GTC'
        )
        order_place_end = time.time()
        
        self.logger.info(f"✅ Limit order placed: OrderID {limit_order_result.get('orderId')}")
        
        # Step 5: Monitor order until filled
        if 'orderId' not in limit_order_result:
            self.logger.error("Failed to get order ID from limit order placement")
            return None
        
        order_id = limit_order_result['orderId']
        monitor_start = time.time()
        filled_time = None
        
        self.logger.info(f"👀 Monitoring order status...")
        
        for attempt in range(30):  # Monitor for up to 30 seconds
            time.sleep(1)
            
            order_status = self.client.get_order_status(symbol, order_id)
            status = order_status.get('status')
            
            if status == 'FILLED':
                filled_time = time.time()
                self.logger.info(f"🎉 Order FILLED after {attempt + 1} seconds!")
                self.logger.info(f"   Filled Price: ${order_status.get('avgPrice', 'N/A')}")
                self.logger.info(f"   Filled Quantity: {order_status.get('executedQty', 'N/A')}")
                break
            elif status == 'CANCELED':
                self.logger.warning(f"❌ Order CANCELED after {attempt + 1} seconds")
                break
            else:
                self.logger.info(f"   Status: {status} (attempt {attempt + 1}/30)")
        
        if not filled_time:
            self.logger.warning("⏰ Order did not fill within 30 seconds, canceling...")
            try:
                cancel_result = self.client.cancel_order(symbol, order_id)
                self.logger.info(f"Order canceled: {cancel_result}")
            except Exception as e:
                self.logger.error(f"Failed to cancel order: {e}")
            return None
        
        # Step 6: Close position with market order
        close_start = time.time()
        filled_quantity = float(order_status.get('executedQty', analysis['quantity']))
        
        # Determine opposite order type
        close_order_type = 'SELL' if order_type == 'BUY' else 'BUY'
        
        self.logger.info(f"🔄 Closing position with {close_order_type} market order...")
        self.logger.info(f"   Closing quantity: {filled_quantity}")
        
        close_order_result = self.client.place_market_order(
            symbol=symbol,
            side=close_order_type,
            quantity=filled_quantity
        )
        
        # Wait for close order to fill
        time.sleep(2)
        close_status = self.client.get_order_status(symbol, close_order_result.get('orderId'))
        close_end = time.time()
        
        self.logger.info(f"✅ Position closed: {close_status.get('status')}")
        self.logger.info(f"   Close Price: ${close_status.get('avgPrice', 'N/A')}")
        
        # Calculate timing results
        cycle_end_time = time.time()
        
        timing_results = {
            'total_cycle_time': cycle_end_time - cycle_start_time,
            'analysis_time': analysis_end - analysis_start,
            'price_calculation_time': price_calc_end - price_calc_start,
            'order_placement_time': order_place_end - order_place_start,
            'order_fill_time': filled_time - order_place_end,
            'close_order_time': close_end - close_start,
            'total_execution_time': close_end - cycle_start_time
        }
        
        # Calculate P&L
        entry_price = float(order_status.get('avgPrice', 0))
        exit_price = float(close_status.get('avgPrice', 0))
        
        if order_type == 'BUY':
            pnl = (exit_price - entry_price) * filled_quantity
        else:
            pnl = (entry_price - exit_price) * filled_quantity
        
        result = {
            'symbol': symbol,
            'order_type': order_type,
            'aggressiveness': aggressiveness,
            'market_direction': analysis['market_direction'],
            'obi': analysis['obi'],
            'obiv': analysis['obiv'],
            'limit_price': calculation['limit_price'],
            'entry_price': entry_price,
            'exit_price': exit_price,
            'quantity': filled_quantity,
            'pnl': pnl,
            'timing': timing_results,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        self.logger.info(f"\n📊 Trade Summary:")
        self.logger.info(f"   Entry: ${entry_price:.6f}")
        self.logger.info(f"   Exit: ${exit_price:.6f}")
        self.logger.info(f"   P&L: ${pnl:.4f}")
        self.logger.info(f"   Fill Time: {timing_results['order_fill_time']:.2f}s")
        self.logger.info(f"   Total Cycle: {timing_results['total_cycle_time']:.2f}s")
        
        return result
    
    def check_position_limits(self, symbol: str = None, order_value: float = 6.0):
        """Check if we're within position limits before placing orders."""
        if not symbol:
            symbol = self.symbol
            
        try:
            # Get current positions
            positions = self.client.get_positions(symbol)
            
            total_position_value = 0.0
            for position in positions:
                if position.get('symbol') == symbol and float(position.get('positionAmt', 0)) != 0:
                    position_value = abs(float(position.get('positionAmt', 0)) * float(position.get('markPrice', 0)))
                    total_position_value += position_value
            
            max_total_position = 50.0
            
            self.logger.info(f"📊 Position Check:")
            self.logger.info(f"   Current Position Value: ${total_position_value:.2f}")
            self.logger.info(f"   Max Total Position: ${max_total_position:.2f}")
            self.logger.info(f"   Order Value: ${order_value:.2f}")
            self.logger.info(f"   Would Result In: ${total_position_value + order_value:.2f}")
            
            if total_position_value + order_value > max_total_position:
                self.logger.warning(f"❌ Order would exceed position limit!")
                self.logger.warning(f"   Current: ${total_position_value:.2f} + Order: ${order_value:.2f} = ${total_position_value + order_value:.2f}")
                self.logger.warning(f"   Limit: ${max_total_position:.2f}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to check position limits: {e}")
            return False
    
    def run_comprehensive_test(self, symbol: str = None):
        """Run comprehensive test of all scenarios."""
        if not symbol:
            symbol = self.symbol
            
        self.logger.info("🎯 Starting Comprehensive Real Trading Test")
        self.logger.info("💰 Position Limits: $50 total, $6 per order")
        self.logger.info("=" * 60)
        
        scenarios = [
            ('BUY', 'conservative'),
            ('BUY', 'aggressive'),
            ('SELL', 'conservative'),
            ('SELL', 'aggressive')
        ]
        
        results = []
        
        for i, (order_type, aggressiveness) in enumerate(scenarios, 1):
            self.logger.info(f"\n{'='*20} Test {i}/4: {order_type} {aggressiveness.upper()} {'='*20}")
            
            try:
                result = self.execute_limit_order_cycle(symbol, order_type, aggressiveness)
                if result:
                    results.append(result)
                    self.test_results.append(result)
                else:
                    self.logger.warning(f"Test {i} failed - order did not execute")
                
                # Wait between tests to avoid rate limits
                if i < len(scenarios):
                    self.logger.info("⏳ Waiting 5 seconds before next test...")
                    time.sleep(5)
                    
            except Exception as e:
                self.logger.error(f"Test {i} failed with exception: {e}")
        
        # Generate summary report
        self.generate_summary_report(results)
        
        return results
    
    def generate_summary_report(self, results):
        """Generate comprehensive summary report."""
        if not results:
            self.logger.warning("No results to summarize")
            return
        
        self.logger.info(f"\n{'='*60}")
        self.logger.info("📊 COMPREHENSIVE TEST SUMMARY")
        self.logger.info(f"{'='*60}")
        
        total_pnl = sum(r['pnl'] for r in results)
        avg_fill_time = sum(r['timing']['order_fill_time'] for r in results) / len(results)
        avg_cycle_time = sum(r['timing']['total_cycle_time'] for r in results) / len(results)
        
        self.logger.info(f"Total Tests: {len(results)}")
        self.logger.info(f"Total P&L: ${total_pnl:.4f}")
        self.logger.info(f"Average Fill Time: {avg_fill_time:.2f}s")
        self.logger.info(f"Average Cycle Time: {avg_cycle_time:.2f}s")
        
        self.logger.info(f"\n📈 Individual Results:")
        for i, result in enumerate(results, 1):
            self.logger.info(f"  {i}. {result['order_type']} {result['aggressiveness']}: "
                           f"P&L ${result['pnl']:.4f}, Fill {result['timing']['order_fill_time']:.2f}s")
        
        # Save results to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"trading_test_results_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)
        
        self.logger.info(f"\n💾 Results saved to: {filename}")


def main():
    """Main function."""
    print("🚀 Real Trading Test System")
    print("=" * 30)
    print("⚠️  WARNING: This will place REAL ORDERS on TESTNET")
    print("💰 Position Limits: $50 total, $6 per order")
    print("🔄 Each test includes automatic position closing")
    print("📊 Asset: DOGE/USDT")
    print()
    
    # Check configuration
    config_path = "config/api.json"
    if not os.path.exists(config_path):
        print(f"❌ Configuration file {config_path} not found!")
        return
    
    with open(config_path, 'r') as f:
        config = json.load(f)
        if config.get("binance", {}).get("testnet", False):
            print("✅ Using TESTNET - Safe for testing")
        else:
            print("⚠️  WARNING: NOT using testnet! This is LIVE trading!")
    
    print("\nChoose test mode:")
    print("1. Single test (choose order type and aggressiveness)")
    print("2. Comprehensive test (all 4 scenarios)")
    print("3. Exit")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice not in ['1', '2', '3']:
        print("Invalid choice!")
        return
    
    if choice == '3':
        print("Exiting...")
        return
    
    # Initialize tester
    tester = RealTradingTester(config_path)
    
    if not tester.load_configuration():
        return
    
    if not tester.initialize_client():
        return
    
    if choice == '1':
        # Single test
        print("\nChoose order type:")
        print("1. BUY")
        print("2. SELL")
        order_choice = input("Enter choice (1-2): ").strip()
        
        print("\nChoose aggressiveness:")
        print("1. Conservative")
        print("2. Aggressive")
        agg_choice = input("Enter choice (1-2): ").strip()
        
        order_type = 'BUY' if order_choice == '1' else 'SELL'
        aggressiveness = 'conservative' if agg_choice == '1' else 'aggressive'
        
        confirm = input(f"\nExecute {order_type} {aggressiveness} test? (y/N): ").strip().lower()
        if confirm == 'y':
            result = tester.execute_limit_order_cycle(order_type=order_type, aggressiveness=aggressiveness)
            if result:
                tester.generate_summary_report([result])
    
    elif choice == '2':
        # Comprehensive test
        confirm = input("\nExecute all 4 trading scenarios? (y/N): ").strip().lower()
        if confirm == 'y':
            tester.run_comprehensive_test()


if __name__ == "__main__":
    main()
