import os
import sys
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent to path first, before any complex imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Now import heavy dependencies
import pandas as pd

# Local imports
try:
    from src.utils import get_order_book
    from src import Create_funding_fetcher, Create_klines_fetcher
except ImportError:
    # Fallback if src module not found
    get_order_book = None
    Create_funding_fetcher = None
    Create_klines_fetcher = None
class B2B_monitor():
    def __init__(self, config_path=None):
        """
        Initialize B2B monitor from configuration.
        
        Args:
            config_path: Path to strategy1.json configuration file
        """
        # Import here to avoid circular imports
        import sys
        project_root = os.path.join(os.path.dirname(__file__), '..', '..')
        if project_root not in sys.path:
            sys.path.append(project_root)
        from util.config_manager import get_strategy_config
        
        # Load configuration using ConfigManager
        if config_path is None:
            self.config = get_strategy_config("strategy1")
        else:
            # Fallback to direct loading if specific path provided
            import json
            with open(config_path, 'r') as f:
                self.config = json.load(f)
        
        # Extract configuration from existing 'monitor' section
        monitor_config = self.config.get('monitor', {})
        
        self.exchange1_id = monitor_config.get('exchange1_id', 'binance')
        self.exchange2_id = monitor_config.get('exchange2_id', None)
        self.is_cross_exchange = self.exchange2_id is not None
        
        self.TIME_COL = 'Time'
        self.n_days = monitor_config.get('n_days', 2)
        self.threshold = monitor_config.get('threshold', 0.1)
        self.value_threshold = monitor_config.get('value_threshold', 30000000)
        
        # Fixed configuration values (as requested)
        self.max_symbols = 10
        self.concurrent_workers = 2
        self.cleanup_enabled = True
        self.days_to_keep = 7
        
        since = datetime.now() - timedelta(days=self.n_days+3)
        
        # Set up exchanges and paths based on mode
        if self.is_cross_exchange:
            exchanges = sorted([self.exchange1_id, self.exchange2_id])
            self.exchange1_id = exchanges[0]
            self.exchange2_id = exchanges[1]
            
            if Create_funding_fetcher is not None and Create_klines_fetcher is not None:
                self.exchange1 = Create_funding_fetcher(self.exchange1_id, since=since)
                self.exchange1_klines = Create_klines_fetcher(self.exchange1_id, since=since)
                self.exchange2 = Create_funding_fetcher(self.exchange2_id, since=since)
                self.exchange2_klines = Create_klines_fetcher(self.exchange2_id, since=since)
                self.shared_symbols = set(self.exchange1.USDT_SYMBOLS).intersection(set(self.exchange2.USDT_SYMBOLS))
            else:
                # Fallback if functions not available
                self.exchange1 = None
                self.exchange1_klines = None
                self.exchange2 = None
                self.exchange2_klines = None
                self.shared_symbols = set()
            self.path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'merge', f'{self.exchange1_id}_{self.exchange2_id}', 'funding_rates')
            print(f"Initialized B2B_monitor (Cross-exchange): {self.exchange1_id} vs {self.exchange2_id} | Threshold: {self.threshold}")
        else:
            if Create_funding_fetcher is not None and Create_klines_fetcher is not None:
                self.exchange1 = Create_funding_fetcher(self.exchange1_id, since=since)
                self.exchange1_klines = Create_klines_fetcher(self.exchange1_id, since=since)
            else:
                # Fallback if functions not available
                self.exchange1 = None
                self.exchange1_klines = None
            self.exchange2 = None
            self.exchange2_klines = None
            if self.exchange1 is not None:
                self.shared_symbols = set(self.exchange1.USDT_SYMBOLS)
            else:
                self.shared_symbols = set()
            self.path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'clean', self.exchange1_id, 'funding_rates')
            print(f"Initialized B2B_monitor (Single-exchange): {self.exchange1_id} | Threshold: {self.threshold}")
        
        # Set up dynamic sorting configuration based on mode
        if self.is_cross_exchange:
            self.sorting_config = {
                'primary': 'annual_fr_diff',  # Use the difference for cross-exchange
                'secondary': f'{self.exchange1_id}_long/short',
                'ascending_primary': False,
                'ascending_secondary': False
            }
        else:
            self.sorting_config = {
                'primary': 'annual_fr',  # Use absolute funding rate for single exchange
                'secondary': 'position',
                'ascending_primary': False,
                'ascending_secondary': False
            }
    
    def _normalize_symbol(self, symbol):
        # Remove common suffixes that might be in the symbol
        for suffix in ['/USDT:USDT', '/USDT', ':USDT']:
            if symbol.endswith(suffix):
                return symbol[:-len(suffix)]
        return symbol
        
        
    def get_data(self):
        for symbol in self.shared_symbols:
            try:
                self.exchange1.get_data(symbol)
                self.exchange1_klines.get_data(symbol)
                if self.is_cross_exchange:
                    self.exchange2.get_data(symbol)
                    self.exchange2_klines.get_data(symbol)
            except Exception as e:
                print(f"Error fetching data for {symbol}: {e}")
                continue
        return
    def transform_data(self):
        from pipeline import DataTransform
        
        shared_symbols = self.shared_symbols
        if self.is_cross_exchange:
            print(f"Transforming data for {self.exchange1_id} and {self.exchange2_id} with {len(shared_symbols)} symbols...")
        else:
            print(f"Transforming data for {self.exchange1_id} with {len(shared_symbols)} symbols...")
        
        for symbol in shared_symbols:
            try:
                df1 = DataTransform(self.exchange1_id)
                df1.update_symbol(symbol)
                if self.is_cross_exchange:
                    df2 = DataTransform(self.exchange2_id)
                    df2.update_symbol(symbol)
            except Exception as e:
                print(f"Error transforming data for {symbol}: {e}")
                continue
        return
    def merge_data(self):
        from pipeline import DataMerge
        
        # Only merge data in cross-exchange mode
        if not self.is_cross_exchange:
            print(f"Single-exchange mode: Skipping merge step (using clean data directly)")
            return
        
        shared_symbols = self.shared_symbols
        print(f"Merging data for {len(shared_symbols)} shared symbols between {self.exchange1_id} and {self.exchange2_id}...")
        for symbol in shared_symbols:
            try:
                merger = DataMerge(self.exchange1_id, self.exchange2_id)
                merger.update_merged_data(symbol)
            except Exception as e:
                print(f"Error merging data for {symbol}: {e}")
                continue
        return

    def cleanup_old_data(self, days_to_keep=None):
        """
        Delete data older than specified days by filtering and rewriting.
        
        Args:
            days_to_keep: Number of days to keep (uses config if None)
        """
        if not self.cleanup_enabled:
            print("Data cleanup disabled in configuration")
            return 0
            
        if days_to_keep is None:
            days_to_keep = self.days_to_keep
            
        cutoff_time = datetime.now() - timedelta(days=days_to_keep)
        total_cleaned = 0
        
        print(f"Cleaning data older than {days_to_keep} days...")
        
        # List all fetchers to clean
        fetchers = [self.exchange1, self.exchange1_klines]
        if self.is_cross_exchange:
            fetchers.extend([self.exchange2, self.exchange2_klines])
        
        for fetcher in fetchers:
            for symbol in self.shared_symbols:
                # Skip if no data exists
                if not fetcher.storage.exists(symbol):
                    continue
                
                try:
                    df = fetcher.storage.read(symbol)
                    if df.empty or self.TIME_COL not in df.columns:
                        continue
                    
                    # Ensure Time is datetime
                    if not pd.api.types.is_datetime64_any_dtype(df[self.TIME_COL]):
                        df[self.TIME_COL] = pd.to_datetime(df[self.TIME_COL])
                    
                    # Filter: keep recent data only
                    df_new = df[df[self.TIME_COL] >= cutoff_time]
                    
                    # Rewrite if data was removed
                    if len(df_new) < len(df):
                        fetcher.storage.write(df_new, symbol)
                        total_cleaned += 1
                        
                except Exception as e:
                    continue
        
        print(f"Cleanup done. Cleaned {total_cleaned} files.")
        return total_cleaned

    
    def backtest_fundingrate(self, symbol):
        normalized_symbol = self._normalize_symbol(symbol)
        normalized_symbol += 'USDT'
        df_ = pd.read_parquet(os.path.join(self.path, f"{normalized_symbol}.parquet"))
        if df_.empty or len(df_) == 0:
            print(f"No data available for symbol: {symbol}")
            return None, symbol
        df_['Time'] = pd.to_datetime(df_['Time'])
        print(f"Backtesting {symbol} for {self.n_days} days with length {len(df_)} and threshold {self.threshold}")
        n = int(self.n_days * 24)
        threshold = self.threshold / (365 * 24)
        value_threshold = self.value_threshold
        
        # Calculate signal based on mode
        if self.is_cross_exchange:
            # Cross-exchange: use funding rate difference
            df_['signal_mean'] = df_['Diff'].rolling(window=n).mean()
        else:
            # Single-exchange: use absolute funding rate
            if 'FundingRate_hourly' in df_.columns:
                df_['signal_mean'] = df_['FundingRate_hourly'].rolling(window=n).mean()
            else:
                print(f"Error: Missing 'FundingRate_hourly' column for {symbol}")
                return None, symbol
        
        # Volume conditions (adapt to single or dual exchange)
        cols = [col for col in df_.columns if col.endswith("_Value")]
        
        if self.is_cross_exchange:
            if len(cols) != 2:
                print(f"Error: Expected exactly 2 value columns for {symbol}, found {len(cols)}")
                return None, symbol
            value_mean1 = df_[cols[0]].rolling(window=n).mean()
            value_mean2 = df_[cols[1]].rolling(window=n).mean()
            condition_1 = (abs(df_['signal_mean']) > threshold) & (value_mean1 > value_threshold) & (value_mean2 > value_threshold)
        else:
            # Single exchange mode
            value_mean = df_['Value'].rolling(window=n).mean()
            condition_1 = (abs(df_['signal_mean']) > threshold) & (value_mean > value_threshold)


        # Build return DataFrame based on mode
        if self.is_cross_exchange:
            return_df = pd.DataFrame(columns=['symbol', 
                                             f'{self.exchange1_id}_annual_fr', 
                                             f'{self.exchange1_id}_last_annual_fr',
                                             f'{self.exchange2_id}_annual_fr', 
                                             f'{self.exchange2_id}_last_annual_fr',
                                             'last_annual_fr_diff', 
                                             'annual_fr_diff',
                                             'spread',
                                             f'{self.exchange1_id}_long/short'])
            return_df.loc[0] = [
                symbol,
                round(df_[self.exchange1_id.capitalize() + '_FR_1H'].rolling(window=n).mean().tail(1).values[0] * 24 * 365, 4),
                round(df_[self.exchange1_id.capitalize() + '_FR_1H'].iloc[-1] * 24 * 365, 4),  # Last exchange1 FR
                round(df_[self.exchange2_id.capitalize() + '_FR_1H'].rolling(window=n).mean().tail(1).values[0] * 24 * 365, 4),
                round(df_[self.exchange2_id.capitalize() + '_FR_1H'].iloc[-1] * 24 * 365, 4),  # Last exchange2 FR
                round((df_[self.exchange2_id.capitalize() + '_FR_1H'].iloc[-1] - df_[self.exchange1_id.capitalize() + '_FR_1H'].iloc[-1]) * 24 * 365, 4),  # Last diff
                0,  # placeholder for annual_fr_diff
                0,   # placeholder for spread
                0  # placeholder for long/short
            ]
            cond_long_entry  = condition_1 & (df_['signal_mean'] < 0)
            cond_short_entry = condition_1 & (df_['signal_mean'] > 0)
        else:
            # Single exchange mode
            return_df = pd.DataFrame(columns=['symbol', 'annual_fr', 'last_annual_fr', 'position'])
            return_df.loc[0] = [
                symbol,
                round(df_['FundingRate_hourly'].rolling(window=n).mean().tail(1).values[0] * 24 * 365, 4),
                round(df_['FundingRate_hourly'].iloc[-1] * 24 * 365, 4),  # Last/latest FR
                0  # placeholder for position (short/long)
            ]
            # Single exchange: short when FR > 0 (receive funding), long when FR < 0 (receive funding)
            # When FR > 0: shorts receive, longs pay → go SHORT
            # When FR < 0: longs receive, shorts pay → go LONG
            cond_short_entry = condition_1 & (df_['signal_mean'] > 0)  # Short to receive positive funding
            cond_long_entry  = condition_1 & (df_['signal_mean'] < 0)  # Long to receive negative funding (pay negative = receive)
        
        try:
            if self.is_cross_exchange:
                # Cross-exchange mode: check if the LAST row meets the condition
                if condition_1.iloc[-1]:  # Check if the last row meets threshold & volume conditions
                    last_signal = df_['signal_mean'].iloc[-1]
                    
                    if last_signal < 0:
                        # Negative diff: exchange2 FR < exchange1 FR → LONG exchange1, SHORT exchange2
                        if get_order_book is not None:
                            other_exchanges_price = get_order_book(symbol, exchange=self.exchange1_id, limit=5)
                            hyperliquid = get_order_book(symbol, exchange=self.exchange2_id, limit=5)
                        else:
                            # Fallback if get_order_book not available
                            other_exchanges_price = None
                            hyperliquid = None

                        return_df['annual_fr_diff'] = round(return_df[f'{self.exchange2_id}_annual_fr'] - return_df[f'{self.exchange1_id}_annual_fr'], 4)
                        return_df['spread'] = round((hyperliquid.head(1)['bids'].values[0][0] - other_exchanges_price.tail(1)['asks'].values[0][0]) / hyperliquid.head(1)['bids'].values[0][0], 4)
                        return_df[f'{self.exchange1_id}_long/short'] = 1
                        print("Long entry conditions met")
                        return True, return_df
                    elif last_signal > 0:
                        # Positive diff: exchange1 FR < exchange2 FR → SHORT exchange1, LONG exchange2
                        if get_order_book is not None:
                            other_exchanges_price = get_order_book(symbol, exchange=self.exchange1_id, limit=5)
                            hyperliquid = get_order_book(symbol, exchange=self.exchange2_id, limit=5)
                        else:
                            # Fallback if get_order_book not available
                            other_exchanges_price = None
                            hyperliquid = None

                        return_df['annual_fr_diff'] = round(return_df[f'{self.exchange1_id}_annual_fr'] - return_df[f'{self.exchange2_id}_annual_fr'], 4)
                        return_df['spread'] = round((other_exchanges_price.tail(1)['asks'].values[0][0] - hyperliquid.head(1)['bids'].values[0][0]) / other_exchanges_price.tail(1)['asks'].values[0][0], 4)
                        return_df[f'{self.exchange1_id}_long/short'] = -1
                        print("Short entry conditions met")
                        return True, return_df
                
                return False, return_df
            else:
                # Single-exchange mode: check if the LAST row meets the condition
                if condition_1.iloc[-1]:  # Check if the last row meets threshold & volume conditions
                    last_signal = df_['signal_mean'].iloc[-1]
                    
                    if last_signal > 0:
                        # Positive FR: SHORT to receive funding
                        return_df['position'] = -1
                        print(f"✓ SHORT entry: FR={return_df['annual_fr'].values[0]:.4f} (receive funding)")
                        return True, return_df
                    elif last_signal < 0:
                        # Negative FR: LONG to receive funding
                        return_df['position'] = 1
                        print(f"✓ LONG entry: FR={return_df['annual_fr'].values[0]:.4f} (receive via negative funding)")
                        return True, return_df
                
                return False, return_df
                
        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            return False, return_df

    def get_B2B_funding_arbitrage_list(self):
        shared_symbols = list(self.shared_symbols)  # for easier indexing
        result = []  # Initialize result as a list
        
        # Initialize DataFrame based on mode
        if self.is_cross_exchange:
            result_df = pd.DataFrame(columns=['symbol', 
                                             f'{self.exchange1_id}_annual_fr', 
                                             f'{self.exchange1_id}_last_annual_fr',
                                             f'{self.exchange2_id}_annual_fr', 
                                             f'{self.exchange2_id}_last_annual_fr',
                                             'last_annual_fr_diff', 
                                             'annual_fr_diff',
                                             'spread',
                                             f'{self.exchange1_id}_long/short'])
        else:
            result_df = pd.DataFrame(columns=['symbol', 'annual_fr', 'last_annual_fr', 'position'])

        print(f"Shared symbols: {shared_symbols}")
        # === Concurrency: process symbols in batches ===
        batch_size = self.concurrent_workers
        for i in range(0, len(shared_symbols), batch_size):
            batch = shared_symbols[i:i+batch_size]
            with ThreadPoolExecutor(max_workers=self.concurrent_workers) as executor:
                future_to_symbol = {
                    executor.submit(self.backtest_fundingrate, symbol): symbol
                    for symbol in batch
                }
                for future in as_completed(future_to_symbol):
                    symbol = future_to_symbol[future]
                    try:
                        flag, details = future.result()
                        if flag and details is not None:
                            result.append(symbol)
                            result_df = pd.concat([result_df, details], ignore_index=True)
                    except Exception as e:
                        print(f"Error with symbol {symbol}: {e}")
            print(f"Symbols meeting the conditions: {result}")
        
        # Sort results based on configuration
        if not result_df.empty:
            primary_col = self.sorting_config['primary']
            secondary_col = self.sorting_config['secondary']
            primary_asc = self.sorting_config['ascending_primary']
            secondary_asc = self.sorting_config['ascending_secondary']
            
            # Limit results to max_symbols if specified
            if self.max_symbols and len(result_df) > self.max_symbols:
                result_df = result_df.head(self.max_symbols)
            
            # Sort with error handling for missing columns
            try:
                result_df = result_df.sort_values(
                    by=[primary_col, secondary_col], 
                    ascending=[primary_asc, secondary_asc]
                ).reset_index(drop=True)
            except KeyError as e:
                print(f"Warning: Column {e} not found in DataFrame. Available columns: {list(result_df.columns)}")
                # Fallback: sort by first available column
                if len(result_df) > 0:
                    available_cols = [col for col in [primary_col, secondary_col] if col in result_df.columns]
                    if available_cols:
                        result_df = result_df.sort_values(by=available_cols[0], ascending=primary_asc).reset_index(drop=True)
                    else:
                        print("No valid sorting columns found, keeping original order")
        # Return message based on mode
        if self.is_cross_exchange:
            return f"Cross-exchange ({self.exchange1_id}/{self.exchange2_id}) - Symbols meeting conditions: {result}", result_df
        else:
            return f"Single-exchange ({self.exchange1_id}) - Symbols meeting conditions: {result}", result_df

    def save_results_to_json(self, result_message, result_df, config_path=None):
        import json
        from datetime import datetime
        
        # Save to result.json in the strategy1 directory
        result_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'result.json')
        
        try:
            # Prepare results data
            results_data = {
                "result": {
                    "message": result_message,
                    "symbols_found": len(result_df) if not result_df.empty else 0,
                    "symbols": result_df.to_dict('records') if not result_df.empty else [],
                    "config_used": {
                        "exchange1_id": self.exchange1_id,
                        "exchange2_id": self.exchange2_id,
                        "n_days": self.n_days,
                        "threshold": self.threshold,
                        "value_threshold": self.value_threshold,
                        "is_cross_exchange": self.is_cross_exchange
                    },
                    "num_placed_symbols": result_df['symbol'].iloc[:self.config.get('monitor', {}).get('placed_symbols', 1)].tolist() if not result_df.empty else []
                }
            }
            
            # Save to result.json
            with open(result_file_path, 'w') as f:
                json.dump(results_data, f, indent=2)
            
            print(f"✅ Results saved to {result_file_path}")
            return True
            
        except Exception as e:
            print(f"❌ Error saving results to JSON: {e}")
            return False

    def start_monitoring(self, save_to_json=True, config_path=None):
        self.cleanup_old_data()  # Clean up old data before processing
        self.get_data()
        self.transform_data()
        self.merge_data()
        
        result_message, result_df = self.get_B2B_funding_arbitrage_list()
        
        # Save results to JSON if requested
        if save_to_json:
            self.save_results_to_json(result_message, result_df, config_path)
        
        return result_message, result_df


