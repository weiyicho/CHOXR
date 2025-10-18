from abc import abstractmethod, ABC
from tqdm import tqdm
from datetime import datetime, timedelta
from time import sleep
import pandas as pd
import os
from pathlib import Path
from typing import Union, Optional

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


class FundingRateStorage(BaseDataStorage):
    TIME_COL = 'Time'

    def __init__(self, exchange_id, folder="funding_rates", project_root=None):
        # Create the data_subdir path
        data_subdir = Path("data") / 'raw' / exchange_id / folder
        # Call parent constructor
        super().__init__(base_dir=project_root, data_subdir=data_subdir, time_column=self.TIME_COL)
        self.exchange_id = exchange_id

    def _file_name_save(self, symbol: str) -> str:
        """
        Converts a trading symbol to a filename-friendly format.
        Handles various formats:
        - 'BTC/USDT' → 'BTCUSDT'
        - 'BTC/USDT:USDT' → 'BTCUSDT'
        - 'BTCUSDT' → 'BTCUSDT' (already normalized)
        
        Args:
            symbol: The trading symbol
            
        Returns:
            str: Filename-friendly symbol representation with base and quote
        """
        # Handle already normalized symbols (no separators)
        if '/' not in symbol and ':' not in symbol and '-' not in symbol:
            return symbol
            
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




class KlinesStorage(BaseDataStorage):
    TIME_COL = 'Time'

    def __init__(self, exchange_id, folder="klines", project_root=None):
        # Create the data_subdir path
        data_subdir = Path("data") / 'raw' / exchange_id / folder
        # Call parent constructor
        super().__init__(base_dir=project_root, data_subdir=data_subdir, time_column=self.TIME_COL)
        self.exchange_id = exchange_id

    def _file_name_save(self, symbol: str) -> str:
        """
        Converts a trading symbol to a filename-friendly format.
        Handles various formats:
        - 'BTC/USDT' → 'BTCUSDT'
        - 'BTC/USDT:USDT' → 'BTCUSDT'
        - 'BTCUSDT' → 'BTCUSDT' (already normalized)
        
        Args:
            symbol: The trading symbol
            
        Returns:
            str: Filename-friendly symbol representation with base and quote
        """
        # Handle already normalized symbols (no separators)
        if '/' not in symbol and ':' not in symbol and '-' not in symbol:
            return symbol
            
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