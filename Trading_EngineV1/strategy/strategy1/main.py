#!/usr/bin/env python3
"""
Main entry point for the trading strategy.
"""

import sys
import os

# Add project root to Python path
project_root = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, project_root)

from order_engine import RealTradingBot
from src.binance_sdk import BinanceFuturesClient
from util.utils import load_config
from util.config_manager import get_api_config
from monitor.discord_notifier import DiscordNotifier
from datetime import datetime
import json

discord = DiscordNotifier(webhook_url='https://discord.com/api/webhooks/1429433339390984312/_om9YEt7c-Bcu_xZXtSZZw5U9Yi-HdvUtMb4k7e-pkNoUDSlq1Z9QEaWjSognZsZ9HrB', enabled=True)

def format_account_info(account_info):
    """Format account info into a concise Discord embed."""
    if not account_info:
        return None
        
    equity = float(account_info.get('accountEquity', 0))
    available = float(account_info.get('totalAvailableBalance', 0))
    status_emoji = "✅" if account_info.get('accountStatus') == 'NORMAL' else "⚠️"
    
    return {
        "title": "📊 **Account Status**",
        "description": f"```\n{status_emoji} Status: {account_info.get('accountStatus', 'Unknown')}\n💰 Equity: ${equity:,.2f}\n💵 Available: ${available:,.2f}\n```",
        "color": 0x0099ff
    }

def format_balance_info(balance):
    """Format balance info into a concise Discord embed."""
    if not balance:
        return None
        
    balance_text = "```\n"
    balance_text += "Asset  | Balance   | P&L\n"
    balance_text += "-------|-----------|------\n"
    
    for asset_info in balance:
        asset = asset_info.get('asset', 'Unknown')
        wallet_balance = float(asset_info.get('totalWalletBalance', 0))
        unrealized_pnl = float(asset_info.get('umUnrealizedPNL', 0))
        
        if wallet_balance > 0 or unrealized_pnl != 0:  # Only show non-zero balances
            pnl_emoji = "📈" if unrealized_pnl > 0 else "📉" if unrealized_pnl < 0 else "➖"
            balance_text += f"{asset:<5} | ${wallet_balance:<8.2f} | {pnl_emoji}${unrealized_pnl:.2f}\n"
    
    balance_text += "```"
    
    return {
        "title": "💰 **Balances**",
        "description": balance_text,
        "color": 0x00ff00
    }

def format_positions_info(positions):
    """Format positions info into a concise Discord embed."""
    if not positions:
        return {
            "title": "📈 **Positions**",
            "description": "```\nNo active positions\n```",
            "color": 0x808080
        }
    
    # Filter positions with non-zero amounts
    active_positions = [pos for pos in positions if float(pos.get('positionAmt', 0)) != 0]
    
    if not active_positions:
        return {
            "title": "📈 **Positions**",
            "description": "```\nNo active positions\n```",
            "color": 0x808080
        }
    
    position_text = "```\n"
    position_text += "Symbol    | Side | Amount | P&L\n"
    position_text += "----------|------|--------|-----\n"
    
    total_unrealized_pnl = 0
    
    for pos in active_positions:
        symbol = pos.get('symbol', 'Unknown')
        position_amt = float(pos.get('positionAmt', 0))
        unrealized_pnl = float(pos.get('unrealizedPnl', 0))
        
        side = "LONG" if position_amt > 0 else "SHORT"
        side_emoji = "🟢" if position_amt > 0 else "🔴"
        
        total_unrealized_pnl += unrealized_pnl
        position_text += f"{symbol:<9} | {side_emoji}{side:<4} | {position_amt:<6.1f} | ${unrealized_pnl:.2f}\n"
    
    position_text += "```"
    
    pnl_color = 0x00ff00 if total_unrealized_pnl > 0 else 0xff0000 if total_unrealized_pnl < 0 else 0x808080
    
    return {
        "title": "📈 **Positions**",
        "description": position_text,
        "color": pnl_color
    }

def create_performance_summary(account_info=None, balance=None, positions=None):
    """Create a concise performance summary."""
    
    # Calculate unrealized P&L from positions
    total_unrealized_pnl = 0.0
    if positions:
        for pos in positions:
            if float(pos.get('positionAmt', 0)) != 0:
                total_unrealized_pnl += float(pos.get('unrealizedPnl', 0))
    
    # Get account value
    account_value = float(account_info.get('accountEquity', 0)) if account_info else 0.0
    available_balance = float(account_info.get('totalAvailableBalance', 0)) if account_info else 0.0
    
    summary_text = "```\n"
    summary_text += f"Trades: 0 | Win Rate: 0.0%\n"
    summary_text += f"Net P&L: $0.00 | Fees: $0.00\n"
    summary_text += f"Account: ${account_value:.2f}\n"
    summary_text += f"Available: ${available_balance:.2f}\n"
    summary_text += f"Position P&L: ${total_unrealized_pnl:.2f}\n"
    summary_text += "```"
    
    return {
        "title": "📊 **Performance Summary**",
        "description": summary_text,
        "color": 0x0099ff
    }

def check_symbol_and_account_status(config_path: str = None):
    """Check account status and positions."""
    try:
        if config_path is None:
            # Use ConfigManager for automatic path resolution
            binance_config = get_api_config("binance")
        else:
            # Fallback to direct loading if specific path provided
            config = load_config(config_path)
            binance_config = config.get("binance", {})
        mock_exchange = type('MockExchange', (), {'id': 'binance'})()
        
        binance_client = BinanceFuturesClient(binance_config, mock_exchange)
        account_info = binance_client.get_account_info()
        positions = binance_client.get_positions()
        balance = binance_client.get_balances()
        
        # Print to console
        print("Account info:", account_info)
        print("Balance:", balance)
        
        # Send beautiful Discord notifications
        # 1. Account Information
        account_embed = format_account_info(account_info)
        discord.send_embed(**account_embed)
        
        # 2. Balance Information
        balance_embed = format_balance_info(balance)
        discord.send_embed(**balance_embed)
        
        # 3. Positions Information
        positions_embed = format_positions_info(positions)
        discord.send_embed(**positions_embed)
        
        # 4. Performance Summary
        performance_embed = create_performance_summary(account_info, balance, positions)
        discord.send_embed(**performance_embed)
        
        # Check if there are active positions
        active_positions = [pos for pos in positions if float(pos.get('positionAmt', 0)) != 0]
        
        if active_positions:
            print('✅ Positions found')
            for pos in active_positions:
                print(f"   {pos['symbol']}: {pos['positionAmt']}")
            return True
        else:
            print('📊 No active positions found')
            return False
            
    except Exception as e:
        print(f'❌ Error checking account status: {e}')
        return False

def main():
    # Use ConfigManager for automatic path resolution
    check_symbol_and_account_status()  # No path needed - ConfigManager handles it
    ### first check the symbol and account status 
    ### do any trading if needed
    
if __name__ == "__main__":
    main()