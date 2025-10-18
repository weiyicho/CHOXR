

from typing import Union  # Add this import at the top

from tqdm import tqdm
import concurrent.futures
from time import sleep
import pandas as pd
import os
from datetime import datetime, timedelta
from abc import abstractmethod,ABC
from pathlib import Path

from pipeline.storage import CleanDataStorage,MergeDataStorage

class DataMerge(ABC):
    def __init__(self, exchange1, exchange2):
        exchanges = sorted([exchange1, exchange2])
        self.TIME_COL = 'Time'
        self.exchange1_id = exchanges[0]
        self.exchange2_id = exchanges[1]
        self.storage1 = CleanDataStorage(self.exchange1_id)
        self.storage2 = CleanDataStorage(self.exchange2_id)
        self.storage3 = MergeDataStorage(self.exchange1_id, self.exchange2_id)
    def load_clean_data(self,symbol):
        df1 = self.storage1.read(symbol)
        df2 = self.storage2.read(symbol)
        return df1, df2
    def combined_data(self,df1,df2):
        if df1.empty and df2.empty:
            return pd.DataFrame()
        if df1.empty:
            return df2
        if df2.empty:
            return df1
        start = max(df1[self.TIME_COL].min(), df2[self.TIME_COL].min())
        end = min(df1[self.TIME_COL].max(), df2[self.TIME_COL].max())
        df1_filtered = df1[(df1[self.TIME_COL] >= start) & (df1[self.TIME_COL] <= end)]
        df2_filtered = df2[(df2[self.TIME_COL] >= start) & (df2[self.TIME_COL] <= end)]
        df1_filtered_ = df1_filtered.set_index(self.TIME_COL)
        df2_filtered_ = df2_filtered.set_index(self.TIME_COL)
        df1_aligned, df2_aligned = df1_filtered_.align(df2_filtered_, join='inner')
        diff = df1_aligned['FundingRate_hourly'] - df2_aligned['FundingRate_hourly']
        print(diff)
        df = pd.DataFrame()
        df['Time'] = df1_aligned.index
        df['Diff'] = diff.values
        df['Diff_cumsum'] = diff.values.cumsum()

        df[f'{str(self.exchange1_id).capitalize()}_FR_1H'] = df1_aligned['FundingRate_hourly'].values
        df[f'{str(self.exchange2_id).capitalize()}_FR_1H'] = df2_aligned['FundingRate_hourly'].values
        
        # Handle Value columns with fallback logic
        if 'Value' in df1_aligned.columns and 'Value' in df2_aligned.columns:
            # Use each exchange's own data, but fill missing values with the other exchange's data
            df1_value = df1_aligned['Value'].fillna(df2_aligned['Value'])
            df2_value = df2_aligned['Value'].fillna(df1_aligned['Value'])
            df[f'{str(self.exchange1_id).capitalize()}_Value'] = df1_value.values
            df[f'{str(self.exchange2_id).capitalize()}_Value'] = df2_value.values
        elif 'Value' in df1_aligned.columns:
            # Only df1 has Value data, use it for both
            df[f'{str(self.exchange1_id).capitalize()}_Value'] = df1_aligned['Value'].values
            df[f'{str(self.exchange2_id).capitalize()}_Value'] = df1_aligned['Value'].values
        elif 'Value' in df2_aligned.columns:
            # Only df2 has Value data, use it for both
            df[f'{str(self.exchange1_id).capitalize()}_Value'] = df2_aligned['Value'].values
            df[f'{str(self.exchange2_id).capitalize()}_Value'] = df2_aligned['Value'].values

        # Handle Open columns with fallback logic
        if 'Open' in df1_aligned.columns and 'Open' in df2_aligned.columns:
            # Use each exchange's own data, but fill missing values with the other exchange's data
            df1_open = df1_aligned['Open'].fillna(df2_aligned['Open'])
            df2_open = df2_aligned['Open'].fillna(df1_aligned['Open'])
            df[f'{str(self.exchange1_id).capitalize()}_Open'] = df1_open.values
            df[f'{str(self.exchange2_id).capitalize()}_Open'] = df2_open.values
        elif 'Open' in df1_aligned.columns:
            # Only df1 has Open data, use it for both
            df[f'{str(self.exchange1_id).capitalize()}_Open'] = df1_aligned['Open'].values
            df[f'{str(self.exchange2_id).capitalize()}_Open'] = df1_aligned['Open'].values
        elif 'Open' in df2_aligned.columns:
            # Only df2 has Open data, use it for both
            df[f'{str(self.exchange1_id).capitalize()}_Open'] = df2_aligned['Open'].values
            df[f'{str(self.exchange2_id).capitalize()}_Open'] = df2_aligned['Open'].values

        return df

    def load_merged_data(self,symbol):
        return self.storage3.read(symbol)

    def update_merged_data(self,symbol):
        df = self.storage3.read(symbol)
        if len(df) ==0 or self.TIME_COL not in df.columns:
            print(f"Merge data for {symbol} does not exist. Merging...")
            df1,df2 = self.load_clean_data(symbol)  # Updated function name
            combined_df = self.combined_data(df1, df2)  # Updated function name
            self.storage3.write(combined_df, symbol)
            return combined_df        
        clean_df = self.load_merged_data(symbol)  # Updated function name
        funding_df1,funding_df2 = self.load_clean_data(symbol)  # Updated function name

        if funding_df2[self.TIME_COL].max() > clean_df[self.TIME_COL].max() and funding_df1[self.TIME_COL].max() > clean_df[self.TIME_COL].max():
            print(f"New data available for {symbol}. Merging...")
            funding_df1_new = funding_df1[funding_df1[self.TIME_COL] > clean_df[self.TIME_COL].max()]
            funding_df2_new = funding_df2[funding_df2[self.TIME_COL] > clean_df[self.TIME_COL].max()]
            new_df = self.combined_data(funding_df1_new, funding_df2_new)  # Updated function name
            clean_df = pd.concat([clean_df, new_df], ignore_index=True)
            clean_df["Diff_cumsum"] = clean_df["Diff"].cumsum()
        self.storage3.write(clean_df, symbol)
        return clean_df
    
    def reset_merged_data(self,symbol):
        if self.storage3.exists(symbol):
            print(f"Resetting merged data for {symbol}")
            self.storage3.delete(symbol)
        df1,df2 = self.load_clean_data(symbol)  # Updated function name
        combined_df = self.combined_data(df1, df2)  # Updated function name
        self.storage3.write(combined_df, symbol)
        return combined_df
    
    
    def merge_all_symbols(self):
        symbols1 = set(self.storage1.list_symbols())
        symbols2 = set(self.storage2.list_symbols())
        shared_symbols = symbols1.intersection(symbols2)
        
        print(f"Merging data for {len(shared_symbols)} shared symbols between {self.exchange1_id} and {self.exchange2_id}...")
        for symbol in tqdm(shared_symbols, desc="Merging symbols"):
            try:
                self.update_merged_data(symbol)  # Updated function name
            except Exception as e:
                print(f"Error merging {symbol}: {e}")
        print("Merging completed for all shared symbols.")