"""
Discord notification system for trading engine.
"""
import requests
import json
from datetime import datetime
from typing import Dict, List, Optional


class DiscordNotifier:
    """Discord notification handler for trading system."""
    
    def __init__(self, webhook_url: str, enabled: bool = True):
        """Initialize Discord notifier."""
        self.webhook_url = webhook_url
        self.enabled = enabled and webhook_url
        
        if self.enabled:
            print("✓ Discord notifications enabled")
        else:
            print("⚠️ Discord notifications disabled (no webhook URL)")
    
    def send_message(self, content: str, username: str = "Trading Engine") -> bool:
        """Send text message to Discord channel."""
        if not self.enabled:
            return False
        
        try:
            formatted_content = f"```\n{content}\n```"
            data = {"content": formatted_content, "username": username}
            headers = {"Content-Type": "application/json"}
            
            response = requests.post(
                self.webhook_url,
                data=json.dumps(data),
                headers=headers,
                timeout=5
            )
            
            return response.status_code == 204
                
        except Exception as e:
            print(f"Discord send error: {e}")
            return False
    
    def send_embed(self, title: str, description: str = "", color: int = 0x00ff00, 
                   fields: Optional[List[Dict]] = None, username: str = "Trading Engine") -> bool:
        """Send embed message to Discord."""
        if not self.enabled:
            return False
        
        try:
            embed = {
                "title": title,
                "description": description,
                "color": color,
                "timestamp": datetime.utcnow().isoformat(),
            }
            
            if fields:
                embed["fields"] = fields
            
            data = {"username": username, "embeds": [embed]}
            headers = {"Content-Type": "application/json"}
            
            response = requests.post(
                self.webhook_url,
                data=json.dumps(data),
                headers=headers,
                timeout=5
            )
            
            return response.status_code == 204
                
        except Exception as e:
            print(f"Discord embed error: {e}")
            return False
    
    def send_accounts_summary(self, accounts_data: List[Dict]) -> bool:
        """Send accounts summary in table format."""
        if not self.enabled:
            return False
            
        try:
            total_account_value = sum(acc.get('account_value', 0) for acc in accounts_data)
            total_position_value = sum(acc.get('position_value', 0) for acc in accounts_data)
            total_available = sum(acc.get('available_balance', 0) for acc in accounts_data)
            
            weighted_leverage = 0
            total_margin = 0
            for acc in accounts_data:
                margin = acc.get('position_value', 0) / acc.get('leverage', 1) if acc.get('leverage', 1) > 0 else 0
                weighted_leverage += acc.get('leverage', 1) * margin
                total_margin += margin
            
            avg_leverage = weighted_leverage / total_margin if total_margin > 0 else 0
            
            content = "Accounts:\n"
            content += "exchange    | account_value | position_value | leverage | available_balance\n"
            content += "---------------------------------------------------------------------------\n"
            
            for acc in accounts_data:
                exchange = acc.get('exchange', '').ljust(12)
                account_val = f"{acc.get('account_value', 0):>10,.2f}"
                position_val = f"{acc.get('position_value', 0):>13,.2f}"
                leverage = f"{acc.get('leverage', 0):>7,.2f}"
                available = f"{acc.get('available_balance', 0):>15,.2f}"
                content += f"{exchange} | {account_val} | {position_val} | {leverage} | {available}\n"
            
            content += "---------------------------------------------------------------------------\n"
            content += f"{'TOTAL':>12} | {total_account_value:>10,.2f} | {total_position_value:>13,.2f} | {avg_leverage:>7,.2f} | {total_available:>15,.2f}"
            
            return self.send_message(content)
            
        except Exception as e:
            print(f"Discord accounts summary error: {e}")
            return False
    
    def send_positions_summary(self, positions_data: List[Dict]) -> bool:
        """Send positions summary in table format."""
        if not self.enabled:
            return False
            
        try:
            if not positions_data:
                content = "Positions:\nNo active positions"
                return self.send_message(content)
            
            total_pnl = sum(pos.get('unrealized_pnl', 0) for pos in positions_data)
            total_pnl_pct = sum(pos.get('pnl_percentage', 0) for pos in positions_data) / len(positions_data) if positions_data else 0
            
            content = "Positions:\n"
            content += "symbol      | side | quantity  | entry_price | current_price | pnl  | pnl_pct\n"
            content += "---------------------------------------------------------------------------\n"
            
            for pos in positions_data:
                symbol = pos.get('symbol', '').ljust(12)
                side = pos.get('side', '').ljust(4)
                quantity = f"{pos.get('quantity', 0):>9,.4f}"
                entry_price = f"{pos.get('entry_price', 0):>11,.4f}"
                current_price = f"{pos.get('current_price', 0):>13,.4f}"
                pnl = f"{pos.get('unrealized_pnl', 0):>4,.2f}"
                pnl_pct = f"{pos.get('pnl_percentage', 0):>7,.2f}%"
                content += f"{symbol} | {side} | {quantity} | {entry_price} | {current_price} | {pnl} | {pnl_pct}\n"
            
            content += "---------------------------------------------------------------------------\n"
            content += f"{'TOTAL':>12} | {'':4} | {'':9} | {'':11} | {'':13} | {total_pnl:>4,.2f} | {total_pnl_pct:>7,.2f}%"
            
            return self.send_message(content)
            
        except Exception as e:
            print(f"Discord positions summary error: {e}")
            return False
    
    def send_performance_summary(self, performance_data: Dict) -> bool:
        """Send performance summary in simple format."""
        if not self.enabled:
            return False
            
        try:
            content = "Performance Summary:\n"
            content += f"Period: {performance_data.get('period', 'Last 24 Hours')}\n"
            content += f"Total Trades: {performance_data.get('total_trades', 0)}\n"
            content += f"Win Rate: {performance_data.get('win_rate', 0):.1f}%\n"
            content += f"Net P&L: ${performance_data.get('net_pnl', 0):.2f}\n"
            content += f"Total Fees: ${performance_data.get('total_fees', 0):.2f}\n"
            content += f"Profit Factor: {performance_data.get('profit_factor', 0):.2f}\n"
            content += f"Best Trade: {performance_data.get('best_trade', 'N/A')}\n"
            content += f"Worst Trade: {performance_data.get('worst_trade', 'N/A')}\n"
            content += f"Max Drawdown: ${performance_data.get('max_drawdown', 0):.2f}"
            
            return self.send_message(content)
            
        except Exception as e:
            print(f"Discord performance summary error: {e}")
            return False