#%%
from ..adapters.Exchange_base import ExchangeFetcher
from ..adapters.storage import FundingRateStorage, KlinesStorage
from abc import abstractmethod,ABC
from  tqdm import tqdm
from time import sleep,time
from datetime import datetime, time, timezone
import pandas as pd
import ccxt
## Bybit

class BybitFundingFetcher(ExchangeFetcher):
    TIME_COL = 'Time'
    
    def __init__(self, exchange, since=None):
        super().__init__(exchange, since)
        self.storage = FundingRateStorage(self.exchange.id)
        
    def _fetch_raw_data(self, symbol, since=None, limit=None):
        """
        Fetch funding rate history with improved handling for early dates and pagination.
        
        Args:
            symbol (str): Trading pair symbol
            since (str): Starting date in YYYY-MM-DD format, defaults to 2023-01-01
            limit (int): Maximum number of records per request
            
        Returns:
            list: Funding rate history records
        """
        import pandas as pd
        from datetime import datetime, timezone, timedelta
        from tqdm import tqdm
        
        all_infos = []
        if since is None:
            since = '2023-01-01'  # Default start date
        
        since_api = int(pd.to_datetime(since).timestamp() * 1000)  # Convert to ms
        now_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
        limit_per_page = min(limit or 1000, 1000)
        prev_last_ts = 0
        retry_count = 0
        max_retries = 3
        
        print(f"Fetching {symbol} funding history from {self._get_exchange_id()} starting {since}...")
        
        with tqdm(desc=f"{self._get_exchange_id()} {symbol} funding history", unit="page") as pbar:
            while True:
                try:
                    batch = self.exchange.fetch_funding_rate_history(
                        symbol,
                        since=since_api,
                        limit=limit_per_page,
                        params={"startTime": since_api}
                    )
                    
                    # Reset retry counter on successful fetch
                    retry_count = 0
                    
                    # Handle empty result
                    if not batch:
                        # If no data found, move forward by 3 days and try again
                        since_api += 86400000 * 3  # Add three days in milliseconds
                        
                        # Stop if we've reached current time
                        if since_api >= now_ts:
                            print(f"Reached current date without finding data")
                            break

                        print(f"No data found at timestamp {pd.to_datetime(since_api, unit='ms', utc=True)}, advancing 3 days...")
                        continue
                    
                    # Extend our results with valid data
                    all_infos.extend(fr['info'] if 'info' in fr else fr for fr in batch)
                    
                    # Get timestamp from last entry for next query
                    last_fr = batch[-1]
                    last_ts = last_fr['timestamp'] + 1  # Add 1ms to avoid duplicate entries
                    
                    # Check if we've reached the end of available data
                    if last_ts >= now_ts or last_ts <= prev_last_ts or len(batch) < limit_per_page:
                        print(f"Completed with {len(all_infos)} total records")
                        break
                    
                    # Update for next iteration
                    prev_last_ts = last_ts - 1  # Store the actual last timestamp
                    since_api = last_ts
                    pbar.update(1)
                    
                except Exception as e:
                    retry_count += 1
                    if retry_count > max_retries:
                        print(f"Failed to fetch data after {max_retries} retries: {e}")
                        break
                        
                    wait_time = 2 ** retry_count  # Exponential backoff
                    print(f"Error fetching data: {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)

        return all_infos

    def _normalize_data(self, raw_data):
        if not raw_data:
            return pd.DataFrame()
        df = pd.DataFrame(raw_data)
        # Standardize column names
        column_mapping = {
            'symbol': 'Symbol',
            'fundingRateTimestamp': 'Time',
            'fundingRate': 'FundingRate',
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
        
        

class BybitKlinesFetcher(ExchangeFetcher):
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

                last_kline = batch[-1][0]
                
                since_api = last_kline

                if last_kline is None:  # Try to get from info
                    print(f"No data in last kline at page {page}")
                    break

                if last_kline is None:
                    print(f"No timestamp found in last item at page {page}")
                    break


                if prev_last_ts is not None and last_kline <= prev_last_ts:
                    print(f"Timestamp stalled at page {page} ({last_kline} ≤ {prev_last_ts})")
                    break

                # Break if we got less than expected (likely end of data)
                if len(batch) < limit_per_page:
                    break
                prev_last_ts = last_kline
                page += 1
                pbar.update(1)
        
        return all_infos
        
    def _normalize_data(self, raw_data):
        if not raw_data:
            return pd.DataFrame()
        df = pd.DataFrame(raw_data, columns=['Time','Open','High','Low','Close','Volume'])
        df['Time'] = pd.to_datetime(df['Time'], unit='ms', errors='coerce', utc=True)
        return df