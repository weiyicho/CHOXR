import time
import pytz
import hmac
import hashlib
import requests
import datetime
from typing import Optional, Dict, Any, Union
from urllib.parse import urlencode

# Timezone configuration - use UTC for consistency
tz = datetime.timezone.utc


class BinanceDataStream():
    """
    Binance Futures Client for USDⓈ-M Futures and Portfolio Margin operations.
    
    This client provides a unified interface for both public market data and private
    trading operations using Binance's Portfolio Margin API (PAPI) and Futures API (FAPI).
    """

    def __init__(self):
        self._market_endpoint = 'https://fapi.binance.com'
        self._session = None  # Placeholder for an HTTP session or client
        self._timeout = 30  # Default timeout for requests


    def _process_api_response(self, response: requests.Response) -> Any:

        try:
            data = response.json()
        except ValueError:
            response.raise_for_status()
            raise

        if isinstance(data, dict):
            if 'code' in data:
                if data['code'] == 200:
                    return data.get('msg', data)
                else:
                    raise Exception(str(data))
            elif 'msg' in data and 'error' in str(data['msg']).lower():
                raise Exception(str(data))
            else:
                return data
        return data

    def _make_public_request(self, path: str, params: Dict[str, Any]) -> Any:
        """Make public API request (FAPI endpoints)."""
        r = requests.get(self._market_endpoint + path, params=params, timeout=30)
        return self._process_api_response(r)

    def _convert_to_timestamp(self, dt: Optional[Union[datetime.datetime, str]]) -> Optional[int]:
        if dt is None:
            return None
        if isinstance(dt, datetime.datetime):
            return int(dt.timestamp() * 1000)
        if isinstance(dt, str):
            dt = datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
            return int(time.mktime(dt.timetuple()) * 1000)
        raise ValueError(f'Datetime type not supported: {type(dt)}')

    # === Market Data Methods (Public: FAPI) ===
    
    def get_klines(self, symbol: str, interval: str, start_time: Optional[Union[datetime.datetime, str]] = None, 
                   end_time: Optional[Union[datetime.datetime, str]] = None, limit: int = 1500) -> list:
        """
        Get kline/candlestick data for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            interval: Kline interval (e.g., '1m', '5m', '1h', '1d')
            start_time: Start time for klines
            end_time: End time for klines
            limit: Number of klines to retrieve (max 1500)
            
        Returns:
            List of kline data
        """
        return self._make_public_request('/fapi/v1/klines', {
            'symbol': symbol, 'interval': interval,
            'startTime': start_time, 'endTime': end_time, 'limit': limit
        })

    def get_order_book(self, symbol: str, limit: int = 5) -> Dict[str, Any]:
        """
        Get order book depth for a symbol.
        
        Args:
            symbol: Trading pair symbol
            limit: Number of orders to retrieve (valid values: 5, 10, 20, 50, 100, 500, 1000, 5000)
            
        Returns:
            Order book data
        """
        # Validate limit parameter
        valid_limits = [5, 10, 20, 50, 100, 500, 1000, 5000]
        if limit not in valid_limits:
            limit = 5  # Default to minimum valid limit
            
        return self._make_public_request('/fapi/v1/depth', {'symbol': symbol, 'limit': limit})

    def get_recent_trades(self, symbol: str, limit: Optional[int] = None) -> list:
        """
        Get recent trades for a symbol.
        
        Args:
            symbol: Trading pair symbol
            limit: Number of trades to retrieve
            
        Returns:
            List of recent trades
        """
        return self._make_public_request('/fapi/v1/trades', {'symbol': symbol, 'limit': limit})

    def get_spot_price(self, symbol: str) -> str:
        """
        Get current spot price for a symbol.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Current spot price as string
        """
        r = requests.get('https://api.binance.com/api/v3/ticker/price', params={'symbol': symbol}, timeout=self._timeout)
        return self._process_api_response(r)['price']
    
    def get_ticker_price(self, symbol: str) -> Dict[str, Any]:
        """
        Get 24hr ticker price statistics for a symbol.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Ticker price statistics
        """
        return self._make_public_request('/fapi/v1/ticker/24hr', {'symbol': symbol})
    
    def get_current_price(self, symbol: str) -> float:
        """
        Get current price for a symbol (futures).
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Current price as float
        """
        ticker = self.get_ticker_price(symbol)
        return float(ticker['lastPrice'])

