import json
import os
import sys

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.join(current_dir, '..', '..')
sys.path.insert(0, root_dir)

from websocket.binance_websocket import BinanceDataStream

# Use ConfigManager for automatic path resolution
from util.config_manager import get_strategy_config
config = get_strategy_config("strategy1")
 

import time
import json
from datetime import datetime

# Assuming BinanceDataStream and config are defined elsewhere
# from your_module import BinanceDataStream, config

if __name__ == "__main__":
    binance_data_stream = BinanceDataStream()
    output_file = "price_data.json"
    while True:
        snapshot = {}
        for symbol in config['result']['num_placed_symbols']:
            clean_symbol = symbol.replace('/USDT:USDT', 'USDT')
            data = binance_data_stream.get_current_price(clean_symbol)
            snapshot[clean_symbol] = {
                "price": data,
                "timestamp": datetime.utcnow().isoformat()
            }
        with open(output_file, "w") as f:
            json.dump(snapshot, f, indent=4)

        print(f"Recorded at {datetime.utcnow().isoformat()}")
        time.sleep(1)