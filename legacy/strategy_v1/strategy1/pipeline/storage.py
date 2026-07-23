
from typing import Union, Optional

from tqdm import tqdm
import concurrent.futures
from time import sleep
import pandas as pd
import os
from datetime import datetime, timedelta
from abc import abstractmethod, ABC
from pathlib import Path
import pyarrow
# Import the BaseDataStorage class
from src.core.storage import BaseDataStorage
try:
    import pyarrow
except ImportError:
    print("Warning: pyarrow not installed. Please install with: pip install pyarrow")
    print("Falling back to CSV storage.")
    PARQUET_AVAILABLE = False
else:
    PARQUET_AVAILABLE = True



class CleanDataStorage(BaseDataStorage):
    TIME_COL = 'Time'

    def __init__(self, exchange_id, folder="funding_rates", project_root=None):
        # Create the data_subdir path
        data_subdir = Path("data") / 'clean' / exchange_id / folder
        # Call parent constructor
        super().__init__(project_root, data_subdir, self.TIME_COL)
        self.exchange_id = exchange_id
        
    def _file_name_save(self, symbol: str) -> str:
        """
        Converts a trading symbol to a filename-friendly format.
        Handles various formats:
        - 'BTC/USDT' → 'BTCUSDT'
        - 'BTC/USDT:USDT' → 'BTCUSDT'
        - 'BTCUSDT' → 'BTCUSDT' (already normalized)
        - 'ETH' → 'ETHUSDT' (assumes USDT quote)
        - 'BTC' → 'BTCUSDT' (assumes USDT quote)
        
        Args:
            symbol: The trading symbol
            
        Returns:
            str: Filename-friendly symbol representation with base and quote
        """
        # Handle perpetual futures notation (BTC/USDT:USDT)
        if ':' in symbol:
            symbol = symbol.split(':')[0]  # Take the part before the colon
            
        # Handle standard notation (BTC/USDT)
        if '/' in symbol:
            base, quote = symbol.split('/')
            return f"{base}{quote}"
            
        # Handle other separators like dash (BTC-USDT)
        if '-' in symbol:
            base, quote = symbol.split('-')
            return f"{base}{quote}"
            
        # Handle base currency only (e.g., 'ETH' → 'ETHUSDT')
        if '/' not in symbol and ':' not in symbol and '-' not in symbol:
            if len(symbol) <= 4 and symbol.isupper() and not symbol.endswith('USDT'):
                return f"{symbol}USDT"
            return symbol
            
        # Fallback
        return symbol.replace('/', '').replace('-', '').replace(':', '')
    def list_symbols(self) -> list[str]:
        """
        List all symbols for which data files exist in the storage directory.
        
        Returns:
            list[str]: List of symbols (derived from filenames without extensions).
        """
        extension = "parquet" if PARQUET_AVAILABLE else "csv"
        files = self.data_dir.glob(f"*.{extension}")
        symbols = [f.stem for f in files]
        return list(symbols)
class MergeDataStorage(BaseDataStorage):
    TIME_COL = 'Time'
    
    def __init__(self, exchange1, exchange2, folder="funding_rates", project_root=None):
        exchanges = sorted([exchange1, exchange2])
        self.exchange1_id = exchanges[0]
        self.exchange2_id = exchanges[1]
        
        # Create the data_subdir path
        data_subdir = Path("data") / 'merge' / f"{self.exchange1_id}_{self.exchange2_id}" / folder
        
        # Call parent constructor
        super().__init__(project_root, data_subdir, self.TIME_COL)
        
    def _file_name_save(self, symbol: str) -> str:
        """
        Converts a trading symbol to a filename-friendly format.
        Handles various formats:
        - 'BTC/USDT' → 'BTCUSDT'
        - 'BTC/USDT:USDT' → 'BTCUSDT'
        - 'BTCUSDT' → 'BTCUSDT' (already normalized)
        - 'ETH' → 'ETHUSDT' (assumes USDT quote)
        - 'BTC' → 'BTCUSDT' (assumes USDT quote)
        
        Args:
            symbol: The trading symbol
            
        Returns:
            str: Filename-friendly symbol representation with base and quote
        """
        # Handle perpetual futures notation (BTC/USDT:USDT)
        if ':' in symbol:
            symbol = symbol.split(':')[0]  # Take the part before the colon
            
        # Handle standard notation (BTC/USDT)
        if '/' in symbol:
            base, quote = symbol.split('/')
            return f"{base}{quote}"
            
        # Handle other separators like dash (BTC-USDT)
        if '-' in symbol:
            base, quote = symbol.split('-')
            return f"{base}{quote}"
            
        # Handle base currency only (e.g., 'ETH' → 'ETHUSDT')
        if '/' not in symbol and ':' not in symbol and '-' not in symbol:
            if len(symbol) <= 4 and symbol.isupper() and not symbol.endswith('USDT'):
                return f"{symbol}USDT"
            return symbol
            
        # Fallback
        return symbol.replace('/', '').replace('-', '').replace(':', '')
    
    def list_symbols(self) -> list[str]:
        """
        List all symbols for which data files exist in the storage directory.
        
        Returns:
            list[str]: List of symbols (derived from filenames without extensions).
        """
        extension = "parquet" if PARQUET_AVAILABLE else "csv"
        files = self.data_dir.glob(f"*.{extension}")
        symbols = [f.stem for f in files]
        return list(symbols)

