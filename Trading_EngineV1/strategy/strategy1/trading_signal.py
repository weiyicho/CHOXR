from B2B import B2B_monitor
import json
import os

class TradingSignal:
    def __init__(self, config, config_path=None):
        """
        Initialize TradingSignal with configuration-driven B2B monitor.
        
        Args:
            config: Configuration dictionary
            config_path: Path to configuration file (optional)
        """
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'strategy1.json')
        self.b2b_monitor = B2B_monitor(config_path)

    def get_trading_signal(self):
        return self.b2b_monitor.get_trading_signal()
    

if __name__ == "__main__":
    # Fix path to find config file from strategy1 directory
    config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'strategy1.json')
    config = json.load(open(config_path))
    trading_signal = TradingSignal(config)
    # Start monitoring and save results to JSON
    result, result_df = trading_signal.b2b_monitor.start_monitoring(
        save_to_json=True, 
        config_path=config_path,
    )
    
    print("=" * 60)
    print("B2B FUNDING ARBITRAGE RESULTS")
    print("=" * 60)
    print(result)
    print("\nDetailed Results:")
    print(result_df)
    print("\n✅ Results have been saved to strategy1.json")
    