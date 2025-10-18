#!/usr/bin/env python3
"""
Setup script for API configuration.
This script helps you set up your API credentials securely.
"""

import json
import os
from getpass import getpass


def setup_api_config():
    """Interactive setup for API configuration."""
    print("🔧 Binance SDK API Configuration Setup")
    print("=" * 40)
    print()
    print("This script will help you configure your API credentials.")
    print("For safety, we recommend using Binance Testnet API keys.")
    print()
    
    # Check if config already exists
    config_path = "../config/api.json"
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            existing_config = json.load(f)
            if existing_config.get("binance", {}).get("api_key") and existing_config.get("binance", {}).get("api_key") != "YOUR_BINANCE_API_KEY_HERE":
                print("⚠️  API configuration already exists!")
                response = input("Do you want to overwrite it? (y/N): ").strip().lower()
                if response != 'y':
                    print("Configuration setup cancelled.")
                    return
    
    print("Please enter your Binance API credentials:")
    print("(Leave empty to skip)")
    print()
    
    # Get API credentials
    api_key = input("Binance API Key: ").strip()
    if not api_key:
        print("❌ API Key is required!")
        return
    
    api_secret = getpass("Binance API Secret: ").strip()
    if not api_secret:
        print("❌ API Secret is required!")
        return
    
    # Ask about testnet
    use_testnet = input("Use testnet? (Y/n): ").strip().lower()
    use_testnet = use_testnet != 'n'
    
    # Get timeout
    try:
        timeout = int(input("Request timeout (seconds, default 30): ").strip() or "30")
    except ValueError:
        timeout = 30
    
    # Create configuration
    config = {
        "binance": {
            "api_key": api_key,
            "api_secret": api_secret,
            "testnet": use_testnet,
            "timeout": timeout,
            "base_url": "https://testnet.binance.vision" if use_testnet else "https://api.binance.com",
            "futures_url": "https://testnet.binancefuture.com" if use_testnet else "https://fapi.binance.com"
        },
        "bybit": {
            "api_key": "YOUR_BYBIT_API_KEY_HERE",
            "api_secret": "YOUR_BYBIT_API_SECRET_HERE",
            "testnet": True,
            "timeout": 30,
            "base_url": "https://api-testnet.bybit.com"
        },
        "discord": {
            "webhook_url": "YOUR_DISCORD_WEBHOOK_URL_HERE",
            "bot_token": "YOUR_DISCORD_BOT_TOKEN_HERE",
            "channel_id": "YOUR_DISCORD_CHANNEL_ID_HERE"
        },
        "general": {
            "timeout": timeout,
            "max_retries": 3,
            "retry_delay": 1,
            "log_level": "INFO"
        }
    }
    
    # Save configuration
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        print()
        print("✅ Configuration saved successfully!")
        print(f"📁 Configuration file: {config_path}")
        print()
        print("🔒 Security reminder:")
        print("- Never commit your API keys to version control")
        print("- Use testnet keys for development")
        print("- Regularly rotate your API keys")
        print()
        print("🚀 You can now run: python3 test_binance_sdk.py")
        
    except Exception as e:
        print(f"❌ Failed to save configuration: {e}")


def validate_config():
    """Validate existing configuration."""
    config_path = "../config/api.json"
    
    if not os.path.exists(config_path):
        print("❌ Configuration file not found!")
        return False
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        binance_config = config.get("binance", {})
        
        if not binance_config.get("api_key") or binance_config.get("api_key") == "YOUR_BINANCE_API_KEY_HERE":
            print("❌ Binance API key not configured!")
            return False
        
        if not binance_config.get("api_secret") or binance_config.get("api_secret") == "YOUR_BINANCE_API_SECRET_HERE":
            print("❌ Binance API secret not configured!")
            return False
        
        print("✅ Configuration is valid!")
        print(f"📊 Testnet mode: {binance_config.get('testnet', False)}")
        print(f"⏱️  Timeout: {binance_config.get('timeout', 30)}s")
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration validation failed: {e}")
        return False


def main():
    """Main function."""
    print("Binance SDK Configuration Manager")
    print("=" * 35)
    print()
    print("Choose an option:")
    print("1. Setup new API configuration")
    print("2. Validate existing configuration")
    print("3. Exit")
    print()
    
    choice = input("Enter your choice (1-3): ").strip()
    
    if choice == "1":
        setup_api_config()
    elif choice == "2":
        validate_config()
    elif choice == "3":
        print("Goodbye!")
    else:
        print("Invalid choice!")


if __name__ == "__main__":
    main()
