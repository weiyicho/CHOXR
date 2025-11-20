#%%
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.binance_sdk import BinanceFuturesClient
from typing import Dict
from enum import Enum
from risks import AccountStatus, RiskManager

# %%
import json




from src.binance_sdk import BinanceFuturesClient

# Load config from JSON file
with open('/Users/zhuoweiyi/Desktop/CHOXR/Trading_EngineV1/config/api.json', 'r') as f:
    config = json.load(f)

# Now pass the dictionary
binance_account = BinanceFuturesClient(config, exchange='binance')



# %%
