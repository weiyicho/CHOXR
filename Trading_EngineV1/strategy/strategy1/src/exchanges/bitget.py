#%%
from ..adapters.Exchange_base import ExchangeFetcher
from ..adapters.storage import FundingRateStorage, KlinesStorage
from abc import abstractmethod,ABC
from  tqdm import tqdm
from time import sleep
from datetime import datetime, timezone
import pandas as pd
import ccxt
## Bitget

class BitgetFundingFetcher(ExchangeFetcher):
    TIME_COL = 'Time'
    
    def __init__(self, exchange, since=None):
        super().__init__(exchange, since)
        self.storage = FundingRateStorage(self.exchange.id)
        
    def _fetch_raw_data(self, symbol, since=None, limit=None):
        all_infos = []
        batch = []
        print(f"Fetching {symbol} funding rate history from {self._get_exchange().id} since {since}")
        since_api = int(pd.to_datetime(since).timestamp() * 1000)  # Convert to ms
        now_ts = int(datetime.now(timezone.utc).timestamp() *1000)
        
        prev_last_ts =0
        page = 0
        limit_per_page = 5000
        with tqdm(desc=f"{self._get_exchange().id} {symbol} funding history", unit="page") as pbar:
            while True:
                try:
                    batch = self._get_exchange().fetch_funding_rate_history(
                        symbol,
                        since=since_api,
                        limit=limit_per_page,
                        params={
                            "paginate": True,
                            # 'endTime': int(endtime),
                            # 'maxEntriesPerRequest':5000,
                            'pageSize':limit_per_page,
                            'pageNo':page+1
                        }
                    )
                except Exception as e:
                    print(f"Error fetching {symbol} on {self._get_exchange().id}", e)
                if not batch:
                    break
                all_infos.extend(fr['info'] if 'info' in fr else fr for fr in batch)

                last_fr = batch[-1]
                if 'timestamp' in last_fr:  # Direct timestamp (most exchanges)
                    last_ts = last_fr['timestamp']
                else:  # Try to get from info
                    last_fr_info = last_fr.get('info', {})
                    last_ts = last_fr_info.get('timestamp') or last_fr_info.get('t') or last_fr_info.get('fundingRateTimestamp')

                if last_ts is None:
                    print(f"No timestamp found in last item at page {page}")
                    break
                    
                if last_ts >= now_ts + 1:
                    print(f"Reached current data at page {page}")
                    break

                if prev_last_ts is not None and last_ts <= prev_last_ts:
                    print(f"Timestamp stalled at page {page} ({last_ts} ≤ {prev_last_ts})")
                    break

                prev_last_ts = last_ts
                since_api = last_ts + 1 
                # Break if we got less than expected (likely end of data)
                if len(batch) < limit_per_page:
                    break
                
                page += 1
                pbar.update(1)
        
        return all_infos
        
    def _normalize_data(self, raw_data):
        if not raw_data:
            return pd.DataFrame()
        df = pd.DataFrame(raw_data)
        # Standardize column names
        column_mapping = {
            'symbol': 'Symbol',
            'fundingTime': 'Time',
            'fundingRate': 'FundingRate',
            'markprice': 'MarkPrice',
        }
        df.rename(columns=column_mapping, inplace=True)
        
        # Ensure required columns exist
        required_columns = ['Symbol', 'Time', 'FundingRate']
        for col in required_columns:
            if col not in df.columns:
                print(f"Warning: Missing expected column '{col}' in data")
        df['Exchange'] = self._get_exchange().id 
        
        # Convert Time to numeric first to avoid the FutureWarning
        df['Time'] = pd.to_numeric(df['Time'], errors='coerce')
        df['Time'] = pd.to_datetime(df['Time'], unit='ms', errors='coerce', utc=True)
        df["Time"] = df["Time"].dt.floor("s")   # 亦可 .round("s")
        
        # Convert FundingRate to numeric to ensure proper data type for Parquet storage
        df['FundingRate'] = pd.to_numeric(df['FundingRate'], errors='coerce')
        
        return df
        
    def _normalize_symbol_name(self, symbol):
        return symbol.split("/")[0]


    # ------------- NEW FUNCTIONALITY ------------- #
    def get_perpetual_symbols(self):
        perpetuals = [s for s in self._get_symbols() if s.endswith(":USDT")]
        self.symbols = perpetuals
        




class BitgetKlinesFetcher(ExchangeFetcher):
    TIME_COL = 'Time'
    
    def __init__(self, exchange, since=None):
        super().__init__(exchange, since)
        self.storage = KlinesStorage(self.exchange.id)
        
    def _fetch_raw_data(self, symbol, since=None, limit=None):
        all_infos = []
        batch = []
        print(f"Fetching {symbol} klines history from {self._get_exchange().id} since {since}")
        since_api = int(pd.to_datetime(since).timestamp() * 1000)  # Convert to ms
        now_ts = int(datetime.now(timezone.utc).timestamp() *1000)
        
        prev_last_ts =0
        page = 0
        limit_per_page = limit if limit and limit < 1000 else 200
        with tqdm(desc=f"{self._get_exchange().id} {symbol} klines history", unit="page") as pbar:
            while True:
                try:
                    batch = self._get_exchange().fetch_ohlcv(
                        symbol,
                        timeframe='1h',
                        since=since_api,
                        limit=limit_per_page
                    )
                except Exception as e:
                    print(f"Error fetching {symbol} on {self._get_exchange().id}", e)
                if not batch:
                    break
                all_infos.extend(batch)

                last_kline = batch[-1]
                if len(last_kline) > 0:  # Direct timestamp (most exchanges)
                    last_ts = last_kline[0]
                else:  # Try to get from info
                    print(f"No data in last kline at page {page}")
                    break

                if last_ts is None:
                    print(f"No timestamp found in last item at page {page}")
                    break
                    
                if last_ts >= now_ts + 1:
                    print(f"Reached current data at page {page}")
                    break
                since_api = last_ts + 1

                page += 1
                pbar.update(1)
        
        return all_infos
        
    def _normalize_data(self, raw_data):
        if not raw_data:
            return pd.DataFrame()
        df = pd.DataFrame(raw_data, columns=['Time','Open','High','Low','Close','Volume'])
        df['Time'] = pd.to_datetime(df['Time'], unit='ms', errors='coerce', utc=True)
        return df