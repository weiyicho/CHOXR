import json
import os
from websocket.binance_websocket import BinanceDataStream
config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'strategy1.json')
config = json.load(open(config_path))
 

if __name__ == "__main__":
    binance_data_stream = BinanceDataStream()
    for symbol in config['result']['num_placed_symbols']:
        print(symbol)
        print(binance_data_stream.get_klines(symbol, '1h'))
        print("=" * 100)