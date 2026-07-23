#!/usr/bin/env python3
"""
Setup script for Discord webhook configuration.
This script helps you set up your Discord webhook URL for testing.
"""

import json
import os
from getpass import getpass


def setup_discord_webhook():
    """Interactive setup for Discord webhook configuration."""
    print("🔧 Discord Webhook Configuration Setup")
    print("=" * 50)
    print()
    print("This script will help you configure your Discord webhook URL.")
    print("You'll need to create a webhook in your Discord server first.")
    print()
    
    print("📋 Steps to create a Discord webhook:")
    print("1. Go to your Discord server")
    print("2. Click on Server Settings (gear icon)")
    print("3. Go to Integrations → Webhooks")
    print("4. Click 'Create Webhook'")
    print("5. Give it a name like 'Trading Engine Bot'")
    print("6. Choose a channel for notifications")
    print("7. Copy the webhook URL")
    print()
    
    # Get webhook URL
    webhook_url = input("Enter your Discord webhook URL: ").strip()
    
    if not webhook_url:
        print("❌ No webhook URL provided. Exiting.")
        return False
        
    if not webhook_url.startswith('https://discord.com/api/webhooks/'):
        print("⚠️  Warning: This doesn't look like a valid Discord webhook URL.")
        print("   Discord webhook URLs should start with: https://discord.com/api/webhooks/")
        
        confirm = input("Do you want to continue anyway? (y/N): ").strip().lower()
        if confirm not in ['y', 'yes']:
            print("❌ Setup cancelled.")
            return False
    
    # Get channel ID (optional)
    channel_id = input("Enter Discord channel ID (optional): ").strip()
    
    # Create monitoring config
    config_path = "../config/monitoring.json"
    
    # Check if config file exists
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except Exception as e:
            print(f"⚠️  Error reading existing config: {e}")
            config = {}
    else:
        config = {}
    
    # Update Discord configuration
    if 'discord' not in config:
        config['discord'] = {}
    
    config['discord']['webhook_url'] = webhook_url
    config['discord']['enabled'] = True
    
    if channel_id:
        config['discord']['channel_id'] = channel_id
    
    # Ensure other required sections exist
    if 'monitoring' not in config:
        config['monitoring'] = {
            'interval': 5,
            'position_monitoring': True,
            'performance_monitoring': True,
            'health_checks': True
        }
    
    if 'alerts' not in config:
        config['alerts'] = {
            'position': {
                'enabled': True,
                'pnl_loss_threshold': -10.0,
                'position_value_threshold': 1000.0,
                'leverage_threshold': 10.0,
                'margin_ratio_threshold': 0.8
            },
            'performance': {
                'enabled': True,
                'daily_loss_threshold': -100.0,
                'drawdown_threshold': -500.0,
                'win_rate_threshold': 30.0
            },
            'risk': {
                'enabled': True,
                'max_position_size': 1000.0,
                'max_total_exposure': 5000.0,
                'max_daily_trades': 50
            }
        }
    
    if 'reports' not in config:
        config['reports'] = {
            'auto': True,
            'interval_hours': 24,
            'include_positions': True,
            'include_performance': True,
            'include_risk_metrics': True
        }
    
    # Save configuration
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"✅ Discord webhook configuration saved to {config_path}")
        print()
        print("🎉 Setup complete! You can now test Discord notifications.")
        print()
        print("To test your Discord integration, run:")
        print("  python3 tests/test_discord_realtime.py")
        
        return True
        
    except Exception as e:
        print(f"❌ Error saving configuration: {e}")
        return False


if __name__ == "__main__":
    success = setup_discord_webhook()
    exit(0 if success else 1)
