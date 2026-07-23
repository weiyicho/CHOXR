#!/usr/bin/env python3
"""
Example usage of the ConfigManager.

This file demonstrates how to use the ConfigManager in your modules.
"""

from config_manager import ConfigManager, get_api_config, get_strategy_config, get_discord_config


def example_usage():
    """Example of how to use ConfigManager in your modules."""
    
    # Method 1: Using the global instance (recommended)
    print("=== Using Global ConfigManager ===")
    
    # Get API configuration
    api_config = get_api_config("binance")
    print(f"Binance API Config: {api_config}")
    
    # Get strategy configuration
    strategy_config = get_strategy_config("strategy1")
    print(f"Strategy Config: {strategy_config}")
    
    # Get Discord configuration
    discord_config = get_discord_config()
    print(f"Discord Config: {discord_config}")
    
    print("\n=== Using ConfigManager Instance ===")
    
    # Method 2: Using ConfigManager instance
    config_manager = ConfigManager()
    
    # Get API config
    api_config = config_manager.get_api_config("binance")
    print(f"API Config: {api_config}")
    
    # Get strategy config
    strategy_config = config_manager.get_strategy_config("strategy1")
    print(f"Strategy Config: {strategy_config}")
    
    # Get monitoring config
    monitoring_config = config_manager.get_monitoring_config()
    print(f"Monitoring Config: {monitoring_config}")
    
    # Get Discord config (unified)
    discord_config = config_manager.get_discord_config()
    print(f"Discord Config: {discord_config}")
    
    print("\n=== Path Information ===")
    print(f"Project Root: {config_manager.project_root}")
    print(f"Config Directory: {config_manager.config_dir}")


def example_in_module():
    """Example of how to use ConfigManager in your existing modules."""
    
    # This is how you would replace the old pattern in B2B.py:
    # OLD:
    # config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'strategy1.json')
    # with open(config_path, 'r') as f:
    #     self.config = json.load(f)
    
    # NEW:
    from config_manager import get_strategy_config
    config = get_strategy_config("strategy1")
    
    # Extract configuration sections
    monitor_config = config.get('monitor', {})
    order_config = config.get('order', {})
    discord_config = config.get('discord', {})
    
    print("=== Module Usage Example ===")
    print(f"Monitor Config: {monitor_config}")
    print(f"Order Config: {order_config}")
    print(f"Discord Config: {discord_config}")


if __name__ == "__main__":
    try:
        example_usage()
        example_in_module()
        print("\n✅ ConfigManager example completed successfully!")
    except Exception as e:
        print(f"❌ Error in ConfigManager example: {e}")
        import traceback
        traceback.print_exc()
