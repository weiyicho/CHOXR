
"""資金費率數據轉換和加載模組"""

from typing import Union, Optional
from tqdm import tqdm
import concurrent.futures
from time import sleep
import pandas as pd
import os
from datetime import datetime, timedelta
from abc import abstractmethod, ABC
from pathlib import Path
from src import FundingRateStorage, KlinesStorage
from .storage import CleanDataStorage


def calculate_time_diff_in_hours(df: pd.DataFrame) -> float:
    """計算時間間隔（小時）"""
    if df.empty or 'Time' not in df.columns or len(df) < 2:
        return 0.0
    df = df.sort_values('Time')
    time_diff = (df['Time'].iloc[-1] - df['Time'].iloc[-2]).total_seconds() / 3600
    return time_diff if time_diff > 0 else 1


class DataTransform(ABC):
    """資金費率數據轉換器"""
    
    TIME_COL = 'Time'
    
    def __init__(self, exchange_id: str):
        """初始化轉換器"""
        self.exchange_id = exchange_id
        self.funding_rate_storage = FundingRateStorage(exchange_id)
        self.clean_storage = CleanDataStorage(exchange_id)
        self.klines_storage = KlinesStorage(exchange_id)
    
    # ==================== Helper Functions ====================
    
    def _load_raw_data(self, symbol: str) -> pd.DataFrame:
        """加載原始數據"""
        print(f"[{self.exchange_id}] Loading raw data for {symbol}")
        return self.funding_rate_storage.read(symbol)
    
    def _validate_data(self, df: pd.DataFrame, required_columns: list = None, symbol: str = None) -> bool:
        """驗證數據"""
        prefix = f"[{self.exchange_id}|{symbol}]" if symbol else f"[{self.exchange_id}]"
        
        if df.empty:
            print(f"{prefix} Data is empty")
            return False
        
        if required_columns:
            missing_cols = [col for col in required_columns if col not in df.columns]
            if missing_cols:
                print(f"{prefix} Missing required columns: {missing_cols}")
                print(f"{prefix} Available columns: {list(df.columns)}")
                return False
        
        return True
    
    def _check_data_freshness(self, clean_df: pd.DataFrame, raw_df: pd.DataFrame) -> bool:
        """檢查數據新鮮度"""
        if not self._validate_data(clean_df, [self.TIME_COL]) or not self._validate_data(raw_df, [self.TIME_COL]):
            return True
            
        return raw_df[self.TIME_COL].max() > clean_df[self.TIME_COL].max()
        
    def _resample_data(self, df: pd.DataFrame, freq: str = '1h', symbol: str = None) -> pd.DataFrame:
        """重採樣數據"""
        if not self._validate_data(df, [self.TIME_COL], symbol):
            return df
        
        prefix = f"[{self.exchange_id}|{symbol}]" if symbol else f"[{self.exchange_id}]"
        print(f"{prefix} Resampling data to frequency: {freq}")
        df = df.set_index(self.TIME_COL)
        df = df.resample(freq).ffill().reset_index()
        return df
    
    def _prepare_funding_data(self, df: pd.DataFrame, symbol: str = None) -> pd.DataFrame:
        """準備資金費率數據"""
        if not self._validate_data(df, [self.TIME_COL, 'FundingRate'], symbol):
            return df
            
        df = df.copy()
        df[self.TIME_COL] = pd.to_datetime(df[self.TIME_COL], utc=True)
        df['FundingRate'] = pd.to_numeric(df['FundingRate'], errors='coerce')
        
        # 計算時間間隔和每小時資金費率
        df['Interval_hours'] = (df['Time'].shift(-1) - df['Time']).dt.total_seconds() / 3600
        
        # 處理最後一行：使用原始數據的最後兩行來計算間隔
        if len(df) > 1:
            # 計算倒數第二行的間隔（已經有值）
            last_interval = df['Interval_hours'].iloc[-2]
            if pd.notna(last_interval):
                df.loc[df.index[-1], 'Interval_hours'] = last_interval
            else:
                # 如果倒數第二行也是 NaN，直接從時間計算
                df.loc[df.index[-1], 'Interval_hours'] = (df['Time'].iloc[-1] - df['Time'].iloc[-2]).total_seconds() / 3600
        else:
            # 如果只有一行，預設為 8 小時（Binance 的標準資金費率間隔）
            df.loc[df.index[-1], 'Interval_hours'] = 8.0
        
        df['FundingRate_hourly'] = df['FundingRate'] / df['Interval_hours']
        
        return df

    
    def _prepare_volume_data(self, volume_df: pd.DataFrame, symbol: str = None) -> pd.DataFrame:
        """準備交易量數據"""
        if not self._validate_data(volume_df, ['Time', 'Open', 'Volume'], symbol):
            return pd.DataFrame()  # 返回空 DataFrame
            
        volume_df = volume_df.copy()
        volume_df['Value'] = volume_df['Open'] * volume_df['Volume']
        volume_df = volume_df[['Time', 'Value', 'Open']]
        volume_df['Time'] = pd.to_datetime(volume_df['Time'], utc=True)
        return volume_df

    def _process_symbol_data(self, symbol: str, include_volume: bool = True) -> pd.DataFrame:
        """處理單個交易對數據"""
        print(f"[{self.exchange_id}|{symbol}] Processing symbol data...")
        
        # 加載和轉換資金費率數據
        funding_df = self._load_raw_data(symbol)
        transformed_df = self.transform_raw_data(funding_df, symbol=symbol)
        
        # 處理交易量數據（如果需要且可用）
        if include_volume:
            print(f"[{self.exchange_id}|{symbol}] Loading volume data...")
            volume_df = self.klines_storage.read(symbol)
            
            # 檢查交易量數據是否有效
            if volume_df.empty or not self._validate_data(volume_df, ['Time', 'Open', 'Volume'], symbol):
                print(f"[{self.exchange_id}|{symbol}] No valid volume data, skipping volume merge.")
            else:
                transformed_df = self.merge_volume_data(transformed_df, volume_df, symbol)
        
        print(f"[{self.exchange_id}|{symbol}] ✓ Processing completed")
        return transformed_df
    
    # ==================== Public Methods ====================
        
    def transform_raw_data(self, df: pd.DataFrame, freq: str = '1h', symbol: str = None) -> pd.DataFrame:
        """轉換原始數據"""
        df = self._prepare_funding_data(df, symbol)
        df = self._resample_data(df, freq, symbol)
        # 移除最後一行（可能不完整），但要確保至少有數據
        # if len(df) > 1:
        #     df = df.iloc[:-1]
        return df
    
    def merge_volume_data(self, funding_df: pd.DataFrame, volume_df: pd.DataFrame, symbol: str = None) -> pd.DataFrame:
        """合併資金費率與交易量數據"""
        prefix = f"[{self.exchange_id}|{symbol}]" if symbol else f"[{self.exchange_id}]"
        print(f"{prefix} Merging funding rate data with volume data: {len(funding_df)} rows + {len(volume_df)} rows")
        
        # 準備交易量數據
        volume_df = self._prepare_volume_data(volume_df, symbol)
        
        # 如果交易量數據為空，直接返回資金費率數據
        if volume_df.empty:
            print(f"{prefix} Volume data is empty, returning funding data without volume.")
            return funding_df
        
        # 檢查兩個 DataFrame 是否都有 Time 列
        if 'Time' not in funding_df.columns:
            print(f"{prefix} ⚠️ Warning: 'Time' column not found in funding_df")
            print(f"{prefix} Available columns in funding_df: {list(funding_df.columns)}")
            return funding_df
        if 'Time' not in volume_df.columns:
            print(f"{prefix} ⚠️ Warning: 'Time' column not found in volume_df")
            print(f"{prefix} Available columns in volume_df: {list(volume_df.columns)}")
            return funding_df
        
        # 合併數據
        merged_df = pd.merge(funding_df, volume_df, on='Time', how='left')
        # merged_df.dropna(inplace=True)

        print(f"{prefix} ✓ Merge completed: {len(merged_df)} rows")
        return merged_df

    def transform_symbol(self, symbol: str) -> pd.DataFrame:
        """轉換單個交易對數據"""
        print(f"[{self.exchange_id}|{symbol}] Starting transformation...")
        transformed_df = self._process_symbol_data(symbol)
        self.clean_storage.write(transformed_df, symbol)
        print(f"[{self.exchange_id}|{symbol}] ✓ Transformation completed and saved\n")
        return transformed_df
        
    def load_symbol(self, symbol: str) -> pd.DataFrame:
        """加載清理數據"""
        print(f"[{self.exchange_id}|{symbol}] Loading clean data...")
        return self.clean_storage.read(symbol)

    def update_symbol(self, symbol: str) -> pd.DataFrame:
        """增量更新清理數據"""
        print(f"[{self.exchange_id}|{symbol}] Checking for updates...")
        
        # 檢查是否存在已清理的數據
        clean_df = self.clean_storage.read(symbol)
        if not self._validate_data(clean_df, [self.TIME_COL], symbol):
            print(f"[{self.exchange_id}|{symbol}] Clean data does not exist. Starting full transformation...")
            return self.transform_symbol(symbol)

        # 檢查是否需要更新
        raw_df = self._load_raw_data(symbol)
        if self._check_data_freshness(clean_df, raw_df):
            print(f"[{self.exchange_id}|{symbol}] New data available, updating...")
            
            # 獲取最後時間點
            last_time = clean_df[self.TIME_COL].max()
            
            # 只處理新的資金費率數據
            new_funding_data = raw_df[raw_df[self.TIME_COL] > last_time]
            print(f"[{self.exchange_id}|{symbol}] Processing {len(new_funding_data)} new rows...")
            
            # 轉換新的資金費率數據
            new_transformed = self.transform_raw_data(new_funding_data, symbol=symbol)
            
            # 讀取並合併對應的交易量數據
            volume_df = self.klines_storage.read(symbol)
            if not volume_df.empty and self._validate_data(volume_df, ['Time', 'Open', 'Volume'], symbol):
                # 只取新時間範圍的交易量數據
                volume_df['Time'] = pd.to_datetime(volume_df['Time'], utc=True)
                new_volume_data = volume_df[volume_df['Time'] > last_time]
                if not new_volume_data.empty:
                    new_transformed = self.merge_volume_data(new_transformed, new_volume_data, symbol)
            
            # 合併並保存
            clean_df = pd.concat([clean_df, new_transformed], ignore_index=True)
            self.clean_storage.write(clean_df, symbol)
            print(f"[{self.exchange_id}|{symbol}] ✓ Update completed\n")
            return clean_df
        else:
            print(f"[{self.exchange_id}|{symbol}] Data is up-to-date\n")
            return clean_df

    def reset_symbol(self, symbol: str) -> pd.DataFrame:
        """重置清理數據"""
        print(f"[{self.exchange_id}|{symbol}] Resetting clean data...")
        if self.clean_storage.exists(symbol):
            self.clean_storage.delete(symbol)
            print(f"[{self.exchange_id}|{symbol}] Existing data deleted")
        
        return self.transform_symbol(symbol)
    
    def _update_symbol_safe(self, symbol: str) -> tuple:
        """安全地更新單個交易對（用於並行處理）"""
        try:
            self.update_symbol(symbol)
            return (symbol, True, None)
        except Exception as e:
            error_msg = str(e)
            print(f"\n[{self.exchange_id}|{symbol}] ❌ ERROR: {error_msg}")
            return (symbol, False, error_msg)
    
    def transform_all_symbols(self, freq: str = '1h', max_workers: int = 4) -> None:
        """
        批量轉換所有交易對（並行處理）
        
        Args:
            freq: 重採樣頻率
            max_workers: 最大並行工作數
        """
        symbols = self.funding_rate_storage.list_symbols()
        print(f"\n{'='*60}")
        print(f"[{self.exchange_id}] Starting batch transformation")
        print(f"[{self.exchange_id}] Total symbols: {len(symbols)}")
        print(f"[{self.exchange_id}] Frequency: {freq}")
        print(f"[{self.exchange_id}] Max workers: {max_workers}")
        print(f"{'='*60}\n")
        
        # 並行處理
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任務
            future_to_symbol = {executor.submit(self._update_symbol_safe, symbol): symbol 
                               for symbol in symbols}
            
            # 使用 tqdm 顯示進度
            for future in tqdm(concurrent.futures.as_completed(future_to_symbol), 
                              total=len(symbols),
                              desc=f"[{self.exchange_id}] Transforming"):
                symbol, success, error = future.result()
                results.append((symbol, success, error))
        
        # 統計結果
        success_count = sum(1 for _, success, _ in results if success)
        failed_count = len(results) - success_count
        
        print(f"\n{'='*60}")
        print(f"[{self.exchange_id}] ✓ Batch transformation completed")
        print(f"[{self.exchange_id}] Success: {success_count}/{len(symbols)}")
        if failed_count > 0:
            print(f"[{self.exchange_id}] Failed: {failed_count}/{len(symbols)}")
            print(f"[{self.exchange_id}] Failed symbols:")
            for symbol, success, error in results:
                if not success:
                    print(f"  - {symbol}: {error}")
        print(f"{'='*60}\n")
    