from B2B import B2B_monitor
import json
import os
import sys

# Add project root to path for ConfigManager
project_root = os.path.join(os.path.dirname(__file__), '..', '..')
if project_root not in sys.path:
    sys.path.append(project_root)
from util.config_manager import get_strategy_config

# from monitor import Monitor
class TradingSignal:
    def __init__(self, config=None, config_path=None):
        """
        Initialize TradingSignal with configuration-driven B2B monitor.
        
        Args:
            config: Configuration dictionary (optional, will use ConfigManager if None)
            config_path: Path to configuration file (optional)
        """
        if config_path is None:
            # Use ConfigManager for automatic path resolution
            self.b2b_monitor = B2B_monitor(None)  # None will trigger ConfigManager usage
        else:
            # Use specific path if provided
            self.b2b_monitor = B2B_monitor(config_path)

    def get_trading_signal(self):
        return self.b2b_monitor.get_trading_signal()
    

if __name__ == "__main__":
    # Use ConfigManager for automatic path resolution
    trading_signal = TradingSignal()  # No config needed - ConfigManager handles it
    # Start monitoring and save results to JSON
    result, result_df = trading_signal.b2b_monitor.start_monitoring(
        save_to_json=True, 
        config_path=None,  # None will trigger ConfigManager usage
    )
    
    print("=" * 60)
    print("B2B FUNDING ARBITRAGE RESULTS")
    print("=" * 60)
    print(result)
    print("\nDetailed Results:")
    print(result_df)
    print("\n✅ Results have been saved to strategy1.json")
