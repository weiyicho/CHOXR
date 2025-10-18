from ..adapters.Exchange_base import ExchangeFetcher
from ..adapters.storage import FundingRateStorage, KlinesStorage
from abc import abstractmethod,ABC
from  tqdm import tqdm
from time import sleep,time
from datetime import datetime, time, timezone
import pandas as pd
import ccxt


class HyperliquidFundingFetcher(ExchangeFetcher):
    TIME_COL = 'Time'
    
    def __init__(self, exchange, since=None):
        super().__init__(exchange, since)
        self.storage = FundingRateStorage(self.exchange.id)
        
    def _fetch_raw_data(self, symbol, since=None, limit=None):

        all_infos = []
        print(f"Fetching {symbol} klines history from  since {since}")
        since_api = 0
        limit_per_page = 100
        prev_last_ts = 0
        while True:
                sleep(0.2)  # Avoid rate limiting
                try:
                    batch = self._get_exchange_id().fetchFundingRateHistory(
                            # params = 
                    symbol,
                    since=since_api,
                    limit=limit_per_page
                    )

                        # Break if we got less than expected (likely end of data)
                        # if len(batch) < limit_per_page:
                        #     break
                except Exception as e:
                    print(f"Error fetching {symbol} on {self._get_exchange().id}", e)
                    break
                all_infos.extend(batch)
                since_api = batch[-1]['info']['time'] + 1
                last_kline = batch[-1]['info']['time']
                print(batch[-1]['datetime'])
                if last_kline is None:  # Try to get from info
                    print(f"No data in last kline at page")
                    break

                if last_kline is None:
                    print(f"No timestamp found in last item at page ")
                    break


                if prev_last_ts is not None and last_kline <= prev_last_ts:
                    print(f"Timestamp stalled at page  ({last_kline} ≤ {prev_last_ts})")
                    break

                prev_last_ts = last_kline
                # Break if we got less than expected (likely end of data)
                if len(batch) < limit_per_page:
                    break

        return all_infos
    
    def _normalize_data(self, raw_data):
        if not raw_data:
            return pd.DataFrame()
        df = pd.DataFrame(raw_data)
        if df.empty:
            return df
        df.drop(columns=['info'], inplace=True)
        df.rename(columns={'fundingRate':'FundingRate','datetime':'Time','symbol':'Symbol'}, inplace=True)
        df['Symbol'] = df['Symbol'].str.split(':').str[0]
        df['Symbol'] = df['Symbol'].str.replace('/','')
        df['Time'] = pd.to_datetime(df['Time'], errors='coerce', utc=True)
        df['FundingRate'] = pd.to_numeric(df['FundingRate'], errors='coerce')
        return df
    
    
    

class HyperliquidKlinesFetcher(ExchangeFetcher):
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
                
                page += 1
                pbar.update(1)
        
        return all_infos
    
    def _normalize_data(self, raw_data):
        if not raw_data:
            return pd.DataFrame()
        df = pd.DataFrame(raw_data, columns=['Time','Open','High','Low','Close','Volume'])
        df['Time'] = pd.to_datetime(df['Time'], unit='ms', errors='coerce', utc=True)
        return df
    