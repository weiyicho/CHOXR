import sys
from itertools import accumulate
from bisect import bisect_left

class OrderManager():
    def __init__(self, config, symbol, exchange_client=None):
        self.symbol = symbol
        self.position = config['position']
        self.leverage = config['leverage']
        self.spot, self.margin = self.calculate_margin()
        # 如果提供了 exchange_client，使用它；否則創建一個新的 BinanceFuturesClient
    def calculate_margin(self,):
        spot = self.position * (1 - (1 / (self.leverage + 1)))
        margin = self.position - spot
        print(f"Position: {self.position}, Leverage: {self.leverage}, Margin: {margin}, Spot: {spot},spot + margin: {spot + margin}")
        return spot, margin

    def get_order_details(self):
        return {
            "symbol": self.symbol,
            "position": self.position,
            "leverage": self.leverage,
            "spot": self.spot,
            "margin": self.margin
        }

    def calculate_number(self, price, position):
        number = position / price
        return number

    def OBIV(self, order_book):
        # bids/asks: list of [price, qty]
        bid_value = sum(float(p) * float(q) for p, q in order_book['bids'])
        ask_value = sum(float(p) * float(q) for p, q in order_book['asks'])
        denom = bid_value + ask_value
        return 0.0 if denom == 0 else (bid_value - ask_value) / denom  # ∈ [-1, 1]
    
    def OBI(self,order_book):
        total_bid_quantity = sum(float(bid[1]) for bid in order_book['bids'])
        total_ask_quantity = sum(float(ask[1]) for ask in order_book['asks'])
        if total_bid_quantity - total_ask_quantity == 0:
            return 0
        obi = (total_bid_quantity - total_ask_quantity) / (total_bid_quantity + total_ask_quantity)
        return obi
    
    def calculate_percentile_price(self, order_book, percentile, side='asks'):
        """
        Calculate price at given percentile of order book side.
        
        Args:
            order_book: Order book data with 'bids' and 'asks'
            percentile: Percentile (0.25 for 25%, 0.75 for 75%)
            side: 'bids' or 'asks'
            
        Returns:
            Price at the specified percentile
        """
        if side not in ['bids', 'asks']:
            raise ValueError("Side must be 'bids' or 'asks'")
        
        if side not in order_book:
            raise ValueError(f"Order book missing '{side}' data")
        
        # Sort by price (ascending for asks, descending for bids)
        if side == 'asks':
            lvls = sorted(((float(p), float(q)) for p, q in order_book['asks']), key=lambda x: x[0])
        else:  # bids
            lvls = sorted(((float(p), float(q)) for p, q in order_book['bids']), key=lambda x: x[0], reverse=True)
        
        prices = [p for p, _ in lvls]
        qtys = [q for _, q in lvls]
        
        total = sum(qtys)
        if total <= 0:
            return None
        
        # Calculate cumulative quantities and find percentile
        cum = list(accumulate(qtys))
        target = percentile * total
        i = bisect_left(cum, target)
        if i >= len(prices):
            i = len(prices) - 1
        return prices[i]
    
    def analyze_market_direction(self, order_book):
        """
        Analyze market direction based on order book imbalance.
        
        Args:
            order_book: Order book data
            
        Returns:
            'UP', 'DOWN', or 'NEUTRAL'
        """
        obi = self.OBI(order_book)
        obiv = self.OBIV(order_book)
        
        # Combine both indicators for more robust signal
        combined_signal = (obi + obiv) / 2
        
        if combined_signal > 0.1:  # Threshold for strong upward pressure
            return 'UP'
        elif combined_signal < -0.1:  # Threshold for strong downward pressure
            return 'DOWN'
        else:
            return 'NEUTRAL'
    
    def get_symbol_tick_size(self, symbol, exchange_client):
        """
        Get tick size for a symbol from exchange info.
        
        Args:
            symbol: Trading pair symbol (e.g., 'DOGEUSDT')
            exchange_client: Exchange client to get symbol info
            
        Returns:
            Tick size as float
        """
        try:
            exchange_info = exchange_client.get_exchange_info()
            for s in exchange_info.get('symbols', []):
                if s.get('symbol') == symbol:
                    # Look for PRICE_FILTER to get tick size
                    price_filter = next((f for f in s.get('filters', []) if f.get('filterType') == 'PRICE_FILTER'), None)
                    if price_filter:
                        tick_size = float(price_filter.get('tickSize', '0.00001'))
                        return tick_size
            # Default tick size if not found
            return 0.00001
        except Exception as e:
            print(f"Warning: Could not get tick size for {symbol}: {e}")
            return 0.00001
    
    def round_to_tick_size(self, price, tick_size):
        """
        Round price to conform to tick size requirements.
        
        Args:
            price: Price to round
            tick_size: Tick size increment
            
        Returns:
            Price rounded to tick size
        """
        if tick_size <= 0:
            return price
        
        # Use decimal arithmetic to avoid floating-point precision issues
        from decimal import Decimal, ROUND_HALF_UP
        
        # Convert to Decimal for precise arithmetic
        price_decimal = Decimal(str(price))
        tick_size_decimal = Decimal(str(tick_size))
        
        # Calculate how many tick size increments fit into the price
        ticks_float = price_decimal / tick_size_decimal
        
        # Round to nearest integer using ROUND_HALF_UP
        ticks = int(ticks_float.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        
        # Convert back to float
        result = float(ticks * tick_size_decimal)
        
        return result
    
    def calculate_limit_price(self, order_book, order_type, aggressiveness, market_direction=None, symbol=None, exchange_client=None):
        """
        Calculate optimal limit order price based on market analysis.
        
        Args:
            order_book: Order book data
            order_type: 'BUY' or 'SELL'
            aggressiveness: 'conservative' or 'aggressive'
            market_direction: 'UP', 'DOWN', 'NEUTRAL' (auto-detect if None)
            symbol: Trading pair symbol (e.g., 'DOGEUSDT')
            exchange_client: Exchange client to get tick size info
            
        Returns:
            Dictionary with calculated price and analysis
        """
        if market_direction is None:
            market_direction = self.analyze_market_direction(order_book)
        
        # Determine percentile based on aggressiveness
        if aggressiveness == 'conservative':
            percentile = 0.25  # 25th percentile
        elif aggressiveness == 'aggressive':
            percentile = 0.75  # 75th percentile
        else:
            raise ValueError("Aggressiveness must be 'conservative' or 'aggressive'")
        
        # Calculate prices for both sides
        bid_price = self.calculate_percentile_price(order_book, percentile, 'bids')
        ask_price = self.calculate_percentile_price(order_book, percentile, 'asks')
        
        # Get current market prices
        current_bid = float(order_book['bids'][0][0]) if order_book['bids'] else None
        current_ask = float(order_book['asks'][0][0]) if order_book['asks'] else None
        
        # Get tick size for the symbol
        tick_size = 0.00001  # Default fallback
        if symbol and exchange_client:
            tick_size = self.get_symbol_tick_size(symbol, exchange_client)
        
        # Determine limit price based on order type and strategy
        if order_type == 'BUY':
            # For BUY orders, we want to buy below current ask
            if market_direction == 'UP':
                # Market going up, be more aggressive
                limit_price = ask_price if aggressiveness == 'aggressive' else current_ask * 0.999
            else:
                # Market going down or neutral, be more conservative
                limit_price = ask_price if aggressiveness == 'conservative' else current_ask * 0.998
        else:  # SELL
            # For SELL orders, we want to sell above current bid
            if market_direction == 'DOWN':
                # Market going down, be more aggressive
                limit_price = bid_price if aggressiveness == 'aggressive' else current_bid * 1.001
            else:
                # Market going up or neutral, be more conservative
                limit_price = bid_price if aggressiveness == 'conservative' else current_bid * 1.002
        
        # Round to tick size to ensure compliance with exchange requirements
        limit_price = self.round_to_tick_size(limit_price, tick_size)
        
        return {
            'limit_price': round(limit_price, 8),  # Higher precision to preserve tick size rounding
            'market_direction': market_direction,
            'order_type': order_type,
            'aggressiveness': aggressiveness,
            'percentile_used': percentile,
            'current_bid': current_bid,
            'current_ask': current_ask,
            'calculated_bid_price': bid_price,
            'calculated_ask_price': ask_price,
            'tick_size': tick_size,
            'obi': self.OBI(order_book),
            'obiv': self.OBIV(order_book)
        }
        


