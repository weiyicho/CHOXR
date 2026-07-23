from abc import abstractmethod, ABC
from tqdm import tqdm
from datetime import datetime, timedelta
from time import sleep
import pandas as pd
import os
from pathlib import Path
from typing import Union, Optional

# Import pyarrow for Parquet support
try:
    import pyarrow
except ImportError:
    print("Warning: pyarrow not installed. Please install with: pip install pyarrow")
    print("Falling back to CSV storage.")
    PARQUET_AVAILABLE = False
else:
    PARQUET_AVAILABLE = True


class BaseDataStorage(ABC):
    """
    Abstract base storage class for all data storage implementations.
    This class handles common storage operations like reading, writing,
    and managing data files in a consistent way across the application.
    """
    
    def __init__(self, base_dir=None, data_subdir=None, time_column='Time'):
        """
        Initialize the base storage.
        
        Args:
            base_dir: Optional explicit base directory path
            data_subdir: Subdirectory path relative to base_dir where data is stored
            time_column: Name of the timestamp column in data
        """
        self.base_dir = self._resolve_base_dir(base_dir)
        if data_subdir:
            self.data_dir = self.base_dir / data_subdir
            self.data_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.data_dir = self.base_dir
        self.time_col = time_column
    
    # ...existing code...
    def _resolve_base_dir(self, provided_dir=None) -> Path:
        """
        Resolve the base directory from provided dir, env var, or auto-detect.
        
        Args:
            provided_dir: Explicitly provided directory path
            
        Returns:
            Path: The resolved base directory path
        """
        if provided_dir:
            return Path(provided_dir)
        
        # Try environment variable
        elif os.environ.get('PROJECT_ROOT'):
            return Path(os.environ.get('PROJECT_ROOT'))
        
        else:
            # Auto-detect project root for strategy1
            # This file is in strategy/strategy1/src/core/storage.py
            # We want strategy/strategy1 as the base directory
            current_dir = Path(__file__).resolve().parent

            # Walk up the directory tree
            while current_dir != current_dir.parent:  # Stop at filesystem root
                # Check if this is the strategy1 directory (contains src and data folders)
                if current_dir.name == 'strategy1' and (current_dir / 'src').exists():
                    return current_dir
                
                # Fallback: detect .git as project root
                if (current_dir / '.git').exists():
                    # If we're in the git repo, use strategy/strategy1
                    strategy1_dir = current_dir / 'strategy' / 'strategy1'
                    if strategy1_dir.exists():
                        return strategy1_dir
                    return current_dir

                current_dir = current_dir.parent
            
            # If no markers found, use default 2 levels up (src/core -> src -> strategy1)
            return Path(__file__).resolve().parent.parent
# ...existing code...
        
    @abstractmethod
    def _file_name_save(self, symbol: str) -> str:
        """
        Convert symbol to filename format.
        
        Args:
            symbol: Symbol to convert
            
        Returns:
            str: The filename-friendly symbol representation
        """
        pass
        
    def path_for(self, symbol: str) -> Path:
        """
        Get full path for a symbol.
        
        Args:
            symbol: Symbol to get path for
            
        Returns:
            Path: Full path to the data file for the symbol
        """
        extension = "parquet" if PARQUET_AVAILABLE else "csv"
        file_name = f"{self._file_name_save(symbol)}.{extension}"
        return self.data_dir / file_name
        
    def read(self, symbol: str) -> pd.DataFrame:
        """
        Read data for symbol.
        
        Args:
            symbol: Symbol to read data for
            
        Returns:
            DataFrame: The data for the symbol, or empty DataFrame if not found
        """
        p = self.path_for(symbol)
        if not p.exists():
            print(f"File not found: {p}")
            return pd.DataFrame()
        try:
            if PARQUET_AVAILABLE and p.suffix == '.parquet':
                return pd.read_parquet(p)
            else:
                return pd.read_csv(p, parse_dates=[self.time_col])
        except Exception as e:
            print(f"Error reading {p}: {e}")
            return pd.DataFrame()
        
    def write(self, df: pd.DataFrame, symbol: str) -> Optional[Path]:
        """
        Write data for symbol.
        
        Args:
            df: DataFrame to write
            symbol: Symbol to write data for
            
        Returns:
            Optional[Path]: The path where data was written, or None on failure
        """
        if df is None or df.empty:
            print(f"No data to write for {symbol}")
            return None
            
        p = self.path_for(symbol)
        p.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Convert date columns to datetime if they aren't already
            if self.time_col in df.columns and not pd.api.types.is_datetime64_any_dtype(df[self.time_col]):
                df[self.time_col] = pd.to_datetime(df[self.time_col])
            
            if PARQUET_AVAILABLE and p.suffix == '.parquet':
                df.to_parquet(p, engine='pyarrow', index=False)
            else:
                df.to_csv(p, index=False)
                
            print(f"Successfully wrote {len(df)} rows to {p}")
            return p
        except Exception as e:
            print(f"Error writing to {p}: {e}")
            return None
        
    def exists(self, symbol: str) -> bool:
        """
        Check if data exists for symbol.
        
        Args:
            symbol: Symbol to check
            
        Returns:
            bool: True if data exists for the symbol, False otherwise
        """
        return self.path_for(symbol).exists()
        
    def search(self, symbol: str) -> pd.DataFrame:
        """
        Search for data by symbol.
        
        Args:
            symbol: Symbol to search for
            
        Returns:
            DataFrame: The data for the symbol if found, empty DataFrame otherwise
        """
        if self.exists(symbol):
            return self.read(symbol)
        return pd.DataFrame()
        
    def delete(self, symbol: str) -> bool:
        """
        Delete data for symbol.
        
        Args:
            symbol: Symbol to delete data for
            
        Returns:
            bool: True if data was deleted, False otherwise
        """
        p = self.path_for(symbol)
        if p.exists():
            try:
                p.unlink()
                print(f"Deleted file: {p}")
                return True
            except Exception as e:
                print(f"Error deleting {p}: {e}")
                return False
        else:
            print(f"File not found for deletion: {p}")
            return False
    @abstractmethod
    def list_symbols(self) -> list[str]:
        """
        List all symbols for which data files exist in the storage directory.
        
        Returns:
            list[str]: List of symbols (derived from filenames without extensions).
        """
