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

# Binance Futures SDK for USDⓈ-M Futures and Portfolio Margin operations

class BinanceFuturesClient():
    """Binance Futures Client for USDⓈ-M Futures and Portfolio Margin operations."""

    def __init__(self, config: Dict[str, Any], exchange: Any):
        self.config = config[exchange]
        
        self._api_key = self.config.get("api_key", "")
        self._api_secret = self.config.get("api_secret", "")
        # API endpoints
        self._market_endpoint = 'https://fapi.binance.com'
        self._private_endpoint = 'https://papi.binance.com'
        self.header = {
            "X-MBX-APIKEY": self._api_key,
        }
        self._timeout = self.config.get("timeout", 30)
        self._session = None

    def _generate_signature(self, param: Dict[str, Any], recv_window: int = 60000) -> Dict[str, Any]:
        """Generate API signature for authenticated requests."""
        timestamp = int((datetime.datetime.now(tz) - datetime.datetime.utcfromtimestamp(0).replace(tzinfo=tz)).total_seconds() * 1000)
        param['timestamp'] = timestamp
        param['recvWindow'] = recv_window
        query = urlencode({k: v for k, v in param.items() if v is not None})
        signature = hmac.new(self._api_secret.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
        param['signature'] = signature
        return param

    def _process_api_response(self, response: requests.Response) -> Any:
        """Process API response and handle errors."""
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
        r = requests.get(self._market_endpoint + path, headers=self.header, params=params, timeout=self._timeout)
        return self._process_api_response(r)

    def _make_private_get_request(self, path: str, params: Dict[str, Any]) -> Any:
        """Make private GET API request (PAPI endpoints)."""
        r = requests.get(self._private_endpoint + path, headers=self.header, params=self._generate_signature(params), timeout=self._timeout)
        return self._process_api_response(r)
    def _make_private_post_request(self, path: str, params: Dict[str, Any]) -> Any:
        """Make private POST API request (PAPI endpoints)."""
        r = requests.post(self._private_endpoint + path, headers=self.header, params=self._generate_signature(params), timeout=self._timeout)
        return self._process_api_response(r)

    def _make_private_delete_request(self, path: str, params: Dict[str, Any]) -> Any:
        """Make private DELETE API request (PAPI endpoints)."""
        r = requests.delete(self._private_endpoint + path, headers=self.header, params=self._generate_signature(params), timeout=self._timeout)
        return self._process_api_response(r)

    def _convert_to_timestamp(self, dt: Optional[Union[datetime.datetime, str]]) -> Optional[int]:
        """Convert datetime object or string to timestamp in milliseconds."""
        if dt is None:
            return None
        if isinstance(dt, datetime.datetime):
            return int(dt.timestamp() * 1000)
        if isinstance(dt, str):
            dt = datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
            return int(time.mktime(dt.timetuple()) * 1000)
        raise ValueError(f'Datetime type not supported: {type(dt)}')

    # Market Data Methods
    
    def get_klines(self, symbol: str, interval: str, start_time: Optional[Union[datetime.datetime, str]] = None, 
                   end_time: Optional[Union[datetime.datetime, str]] = None, limit: int = 1500) -> list:
        """Get kline/candlestick data for a symbol."""
        return self._make_public_request('/fapi/v1/klines', {
            'symbol': symbol, 'interval': interval,
            'startTime': start_time, 'endTime': end_time, 'limit': limit
        })

    def get_order_book(self, symbol: str, limit: int = 5) -> Dict[str, Any]:
        """Get order book depth for a symbol."""
        return self._make_public_request('/fapi/v1/depth', {'symbol': symbol, 'limit': limit})

    def get_recent_trades(self, symbol: str, limit: Optional[int] = None) -> list:
        """Get recent trades for a symbol."""
        return self._make_public_request('/fapi/v1/trades', {'symbol': symbol, 'limit': limit})

    def get_spot_price(self, symbol: str) -> str:
        """Get current spot price for a symbol."""
        r = requests.get('https://api.binance.com/api/v3/ticker/price', params={'symbol': symbol}, timeout=self._timeout)
        return self._process_api_response(r)['price']

    # Futures Trading Methods
    
    def place_market_order(self, symbol: str, side: str, quantity: float, 
                          reduce_only: Optional[bool] = None, client_order_id: Optional[str] = None) -> Dict[str, Any]:
        """Place a market order for futures trading."""
        return self._make_private_post_request('/papi/v1/um/order', {
            'symbol': symbol, 'side': side, 'type': 'MARKET',
            'quantity': quantity, 'reduceOnly': reduce_only, 'newClientOrderId': client_order_id
        })
    
    def place_limit_order(self, symbol: str, side: str, price: float, quantity: float, 
                         time_in_force: str = 'GTC', reduce_only: Optional[bool] = None, 
                         client_order_id: Optional[str] = None) -> Dict[str, Any]:
        """Place a limit order for futures trading."""
        return self._make_private_post_request('/papi/v1/um/order', {
            'symbol': symbol, 'side': side, 'price': price, 'type': 'LIMIT',
            'quantity': quantity, 'reduceOnly': reduce_only, 'timeInForce': time_in_force,
            'newClientOrderId': client_order_id
        })

    def get_order_status(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """Query order status by order ID."""
        return self._make_private_get_request('/papi/v1/um/order', {'symbol': symbol, 'orderId': order_id})

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """Get all current open orders."""
        return self._make_private_get_request('/papi/v1/um/openOrders', {'symbol': symbol})

    def cancel_all_orders(self, symbol: str) -> Dict[str, Any]:
        """Cancel all open orders for a symbol."""
        return self._make_private_delete_request('/papi/v1/um/allOpenOrders', {'symbol': symbol})
    
    def cancel_order(self, symbol: str, order_id: Optional[int] = None, 
                    client_order_id: Optional[str] = None) -> Dict[str, Any]:
        """Cancel a specific order."""
        return self._make_private_delete_request('/papi/v1/um/order', {
            'symbol': symbol, 'orderId': order_id, 'origClientOrderId': client_order_id
        })
    # Margin Trading Methods
    
    def place_margin_market_order(
        self, symbol: str, side: str, quantity: float,
        side_effect_type: str = "NO_SIDE_EFFECT",
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Place a market order for margin trading."""
        return self._make_private_post_request('/papi/v1/margin/order', {
            'symbol': symbol,
            'side': side,
            'type': 'MARKET',
            'quantity': quantity,
            'sideEffectType': side_effect_type,
            'newClientOrderId': client_order_id
        })

    def place_margin_limit_order(
        self, symbol: str, side: str, price: float, quantity: float,
        time_in_force: str = 'GTC',
        side_effect_type: str = "NO_SIDE_EFFECT",
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Place a limit order for margin trading."""
        return self._make_private_post_request('/papi/v1/margin/order', {
            'symbol': symbol,
            'side': side,
            'type': 'LIMIT',
            'price': price,
            'quantity': quantity,
            'timeInForce': time_in_force,
            'sideEffectType': side_effect_type,
            'newClientOrderId': client_order_id
        })

    def get_margin_order_status(self, symbol: str, order_id: Optional[int] = None, 
                               client_order_id: Optional[str] = None) -> Dict[str, Any]:
        """Query margin order status."""
        return self._make_private_get_request('/papi/v1/margin/order', {
            'symbol': symbol,
            'orderId': order_id,
            'origClientOrderId': client_order_id
        })

    def get_open_margin_orders(self, symbol: Optional[str] = None) -> list:
        """Get all current open margin orders."""
        return self._make_private_get_request('/papi/v1/margin/openOrders', {
            'symbol': symbol
        })

    def cancel_margin_order(self, symbol: str, order_id: Optional[int] = None, 
                           client_order_id: Optional[str] = None) -> Dict[str, Any]:
        """Cancel a specific margin order."""
        return self._make_private_delete_request('/papi/v1/margin/order', {
            'symbol': symbol,
            'orderId': order_id,
            'origClientOrderId': client_order_id
        })

    # Account and Position Management
    
    def get_positions(self, symbol: Optional[str] = None) -> list:
        """Get current positions."""
        return self._make_private_get_request('/papi/v1/um/positionRisk', {'symbol': symbol})

    def get_account_info(self) -> Dict[str, Any]:
        """Get account information."""
        return self._make_private_get_request('/papi/v1/account', {})
    def get_balances(self) -> list:
        """Get account balances."""
        return self._make_private_get_request('/papi/v1/balance', {})

    def get_trade_history(self, symbol: str, start_time: Optional[Union[datetime.datetime, str]] = None, 
                         end_time: Optional[Union[datetime.datetime, str]] = None, limit: int = 1000) -> list:
        """Get trade history for a symbol."""
        return self._make_private_get_request('/papi/v1/userTrades', {
            'symbol': symbol,
            'startTime': self._convert_to_timestamp(start_time),
            'endTime': self._convert_to_timestamp(end_time),
            'limit': limit
        })

    
    def change_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """Change leverage for a symbol."""
        return self._make_private_post_request('/papi/v1/um/leverage', {'symbol': symbol, 'leverage': int(leverage)})

    def auto_allocation(self,):
        """Enable auto allocation for portfolio margin."""
        return self._make_private_post_request('/papi/v1/auto-collection', {})





