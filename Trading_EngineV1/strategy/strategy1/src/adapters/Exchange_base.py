from abc import abstractmethod,ABC
from tqdm import tqdm
from datetime import datetime, timedelta
from time import sleep
import pandas as pd
import os
from pathlib import Path
from typing import Union, Optional
from .storage import FundingRateStorage,KlinesStorage
import ccxt



class ExchangeFetcher(ABC):
    DEFAULT_LIMIT = 150
    TIME_COL= 'Time'
    def __init__(self, exchange,since=None):
        if isinstance(exchange, str):
            self.exchange = getattr(ccxt, exchange)()   # 動態建立 ccxt.binance()
        else:
            self.exchange = exchange  # 已經是 instance
        if since is None:
            self.since = self._default_since()
        else:
            self.since = since

        self.storage = FundingRateStorage(self.exchange.id)
        self.markets = self._load_markets()
        self.symbols = self._load_supported_symbols(self.markets, self.exchange)
        self.USDT_SYMBOLS = [s for s in self._get_symbols() if s.endswith(":USDT")]
        
        
    ### ------------- UTILS ------------- #
    def _get_symbols(self):
        return self.symbols
    def _get_exchange(self):
        return self.exchange
    def _get_exchange_id(self):
        return self.exchange.id
    def _get_usdt_symbols(self):
        return self.USDT_SYMBOLS
    def _default_since(self):
        # Default to 5 years ago
        return '2021-01-01'
    def _load_markets(self):
        try:
            return self.exchange.load_markets()
        except Exception as e:
            print(f"Error loading markets for {self.exchange.id}: {e}")
            return {}
    def _load_supported_symbols(self, markets, exchange):
            return [
                symbol for symbol, market in markets.items()
                if market.get('swap', False) and market.get('contract', False)
            ]   
    def _deduplicate(self, df):
            if df is None or df.empty:
                return pd.DataFrame()
            df[self.TIME_COL] = pd.to_datetime(df[self.TIME_COL], errors='coerce', utc=True)
            df = df.drop_duplicates(subset=[self.TIME_COL])
            df = df.sort_values(by=self.TIME_COL).reset_index(drop=True)
            return df
    def _default_since(self):
        # Default to 5 years ago
        return '2021-01-01'
    
    ### ------------- ABSTRACT METHODS ------------- #
    @abstractmethod
    def _fetch_raw_data(self, symbol, since=None, limit=None):
        pass
    @abstractmethod
    def _normalize_data(self, raw_data):
        pass
    
    
    ### ------------- MAIN METHODS ------------- #
    def fetch_data(self, symbol, since=None, limit=None):
        if symbol not in self.symbols:
            raise ValueError(f"{symbol} not supported in {self.exchange.id}")
        since = since or self.since
        limit = limit or self.DEFAULT_LIMIT
        raw_data = self._fetch_raw_data(symbol, since, limit)
        processed_data = self._normalize_data(raw_data)
        processed_data = self._deduplicate(processed_data)
        return processed_data
    def load_historical_data(self, symbol):
        historical_data, last_timestamp = pd.DataFrame(), None
        historical_data = self.storage.search(symbol)
        if historical_data is not None:
            try:
                last_timestamp = historical_data[self.TIME_COL].max() if not historical_data.empty else None
                last_timestamp = pd.to_datetime(last_timestamp, utc=True) if last_timestamp is not None else None
                return historical_data, last_timestamp
            except Exception:
                return historical_data, last_timestamp
        else:
            return historical_data, last_timestamp
    def get_data(self, symbol):
        time_col = self.TIME_COL
        historical_data, last_timestamp = self.load_historical_data(symbol)
        
        # 計算時間差（如果有歷史數據）
        if not historical_data.empty and len(historical_data) >= 2 and time_col in historical_data.columns:
            time_diff = historical_data[time_col].max() - historical_data[time_col].iloc[-2]
        else:
            time_diff = pd.Timedelta(hours=1)  # 預設 1 小時
        
        now = pd.Timestamp.now(tz="UTC")
        if last_timestamp is not None:
            print (f"Last data time for {symbol}: {last_timestamp}")
        if last_timestamp and (now - last_timestamp).total_seconds() < time_diff.total_seconds():
            print(f"Data for {symbol} is up-to-date. No update needed.")
            return historical_data
        
        fresh_data = self.fetch_data(symbol, since=last_timestamp)
        
        if fresh_data is None:
            fresh_data = pd.DataFrame()

        if historical_data.empty and fresh_data.empty:
            return pd.DataFrame()
        elif fresh_data.empty and not historical_data.empty:
            return historical_data
        combined_data = pd.concat([historical_data, fresh_data], ignore_index=True).drop_duplicates(subset=[time_col])
        combined_data[time_col] = pd.to_datetime(combined_data[time_col], errors='coerce', utc=True)
        combined_data = combined_data.sort_values(by=time_col)
        combined_data = self._deduplicate(combined_data)
        self.storage.write(combined_data, symbol)
        print(f"Updated data for {symbol}. Total records: {len(combined_data)}")
        return combined_data

    def get_all_data(self,usdt_pairs_only=True):
        print(f"Updating funding rates for {len(self.symbols)} symbols on {self.exchange.id}...")
        symbols = self.USDT_SYMBOLS if usdt_pairs_only else self.symbols
        for symbol in tqdm(symbols, desc="Updating symbols"):
            print(f"Updating {symbol}...")
            try:
                self.get_data(symbol)
            except Exception as e:
                print(f"Error updating {symbol}: {e}")
        print("All symbols updated.")
    def reset_data(self, symbol):
        if self.storage.exists(symbol):
            print(f"Resetting data for {symbol}")
            self.storage.delete(symbol)
        df = self.fetch_data(symbol, since=self._default_since())
        if df is not None and not df.empty:
            self.storage.write(df, symbol)
            print(f"Data for {symbol} reset. Total records: {len(df)}")
        return df
    def reset_all_data(self):
        for symbol in self.symbols:
            self.reset_data(symbol)
        print("All data reset.")



class DexFetcher(ABC):
    def __init__(self, exchange,since=None):
        self.exchange = exchange
        if since is None:
            self.since = self._default_since()
        else:
            self.since = since

        self.storage = FundingRateStorage(self.exchange)
        self.DEFAULT_LIMIT = 150
        self.TIME_COL= 'Time'
        self.symbols = self._load_supported_symbols()
        self.USDT_SYMBOLS = self._usdt_symbols()
        
        
    ### ------------- UTILS ------------- #
    def _get_exchange(self):
        return self.exchange
    def _default_since(self):
        # Default to 5 years ago
        return '2021-01-01'

    def _deduplicate(self, df):
            if df is None or df.empty:
                return pd.DataFrame()
            df[self.TIME_COL] = pd.to_datetime(df[self.TIME_COL], errors='coerce', utc=True)
            df = df.drop_duplicates(subset=[self.TIME_COL])
            df = df.sort_values(by=self.TIME_COL).reset_index(drop=True)
            return df
    def _default_since(self):
        # Default to 5 years ago
        return '2021-01-01'
    
    ### ------------- ABSTRACT METHODS ------------- #
    @abstractmethod
    def _fetch_raw_data(self, symbol, since=None, limit=None):
        pass
    @abstractmethod
    def _normalize_data(self, raw_data):
        pass
    
    @abstractmethod
    def _load_supported_symbols(self):
        pass
    def _usdt_symbols(self):
        pass
    
    
    ### ------------- MAIN METHODS ------------- #
    def fetch_data(self, symbol, since=None, limit=None):
        if symbol not in self.symbols:
            raise ValueError(f"{symbol} not supported in {self.exchange.id}")
        since = since or self.since
        limit = limit or self.DEFAULT_LIMIT
        raw_data = self._fetch_raw_data(symbol, since, limit)
        processed_data = self._normalize_data(raw_data)
        processed_data = self._deduplicate(processed_data)
        return processed_data
    def load_historical_data(self, symbol):
        historical_data, last_timestamp = pd.DataFrame(), None
        historical_data = self.storage.search(symbol)
        if historical_data is not None:
            try:
                last_timestamp = historical_data[self.TIME_COL].max() if not historical_data.empty else None
                last_timestamp = pd.to_datetime(last_timestamp, utc=True) if last_timestamp is not None else None
                return historical_data, last_timestamp
            except Exception:
                return historical_data, last_timestamp
        else:
            return historical_data, last_timestamp
    def get_data(self, symbol):
        time_col = self.TIME_COL
        historical_data, last_timestamp = self.load_historical_data(symbol)
        now = pd.Timestamp.now(tz="UTC")
        if last_timestamp is not None:
            print (f"Last data time for {symbol}: {last_timestamp}")
        if last_timestamp and (now - last_timestamp).total_seconds() < 3600 * 8:
            print(f"Data for {symbol} is up-to-date. No update needed.")
            return historical_data
        
        fresh_data = self.fetch_data(symbol, since=last_timestamp)
        
        if fresh_data is None:
            fresh_data = pd.DataFrame()

        if historical_data.empty and fresh_data.empty:
            return pd.DataFrame()
        elif fresh_data.empty and not historical_data.empty:
            return historical_data
        combined_data = pd.concat([historical_data, fresh_data], ignore_index=True).drop_duplicates(subset=[time_col])
        combined_data[time_col] = pd.to_datetime(combined_data[time_col], errors='coerce', utc=True)
        combined_data = combined_data.sort_values(by=time_col)
        combined_data = self._deduplicate(combined_data)
        self.storage.write(combined_data, symbol)
        print(f"Updated data for {symbol}. Total records: {len(combined_data)}")
        return combined_data

    def get_all_data(self,usdt_pairs_only=True):
        print(f"Updating funding rates for {len(self.symbols)} symbols on {self.exchange.id}...")
        symbols = self.USDT_SYMBOLS if usdt_pairs_only else self.symbols
        for symbol in tqdm(symbols, desc="Updating symbols"):
            print(f"Updating {symbol}...")
            try:
                self.get_data(symbol)
            except Exception as e:
                print(f"Error updating {symbol}: {e}")
        print("All symbols updated.")
    def reset_data(self, symbol):
        if self.storage.exists(symbol):
            print(f"Resetting data for {symbol}")
            self.storage.delete(symbol)
        df = self.fetch_data(symbol, since=self._default_since())
        if df is not None and not df.empty:
            self.storage.write(df, symbol)
            print(f"Data for {symbol} reset. Total records: {len(df)}")
        return df
    def reset_all_data(self):
        for symbol in self.symbols:
            self.reset_data(symbol)
        print("All data reset.")

