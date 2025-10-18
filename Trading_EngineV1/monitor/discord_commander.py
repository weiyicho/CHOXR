"""
Discord 命令控制器
通過 Discord 消息來控制交易引擎
"""
import requests
import json
import time
from typing import Optional, Callable, Dict
from datetime import datetime
from threading import Thread


class DiscordCommander:
    """
    Discord 命令控制器
    
    監聽 Discord 頻道的命令，並執行相應的操作
    """
    
    def __init__(self, webhook_url: str, channel_id: Optional[str] = None):
        """
        初始化 Discord 命令控制器
        
        Args:
            webhook_url: Discord Webhook URL
            channel_id: Discord 頻道 ID（可選）
        """
        self.webhook_url = webhook_url
        self.channel_id = channel_id
        self.enabled = bool(webhook_url)
        
        # 命令處理器
        self.command_handlers: Dict[str, Callable] = {}
        
        # 運行狀態
        self.is_running = False
        self.last_message_id = None
        
        if self.enabled:
            print("✓ Discord 命令控制器已啟用")
        else:
            print("⚠️  Discord 命令控制器未啟用（未設置 webhook_url）")
    
    def register_command(self, command: str, handler: Callable):
        """
        註冊命令處理器
        
        Args:
            command: 命令名稱（如 'stop', 'status'）
            handler: 處理函數
        """
        self.command_handlers[command.lower()] = handler
        print(f"✓ 已註冊命令: {command}")
    
    def send_command_response(self, response: str, color: int = 0x0099ff):
        """
        發送命令響應
        
        Args:
            response: 響應內容
            color: 顏色
        """
        if not self.enabled:
            return
        
        try:
            embed = {
                "title": "🤖 命令執行結果",
                "description": response,
                "color": color,
                "timestamp": datetime.utcnow().isoformat(),
            }
            
            data = {
                "username": "Trading Engine Commander",
                "embeds": [embed]
            }
            
            headers = {"Content-Type": "application/json"}
            requests.post(
                self.webhook_url,
                data=json.dumps(data),
                headers=headers,
                timeout=5
            )
        except Exception as e:
            print(f"發送命令響應失敗: {e}")
    
    def send_help_message(self):
        """發送幫助信息"""
        help_text = """
**可用命令：**

`!stop` - 緊急停止（取消所有訂單並停止系統）
`!cancel` - 取消所有訂單
`!cancel SYMBOL` - 取消特定交易對的訂單（如：!cancel BTCUSDT）
`!status` - 查看系統狀態
`!positions` - 查看當前倉位
`!risk` - 查看風險狀態
`!help` - 顯示此幫助信息

**範例：**
```
!stop
!cancel
!cancel BTCUSDT
!status
```
        """
        
        self.send_command_response(help_text, color=0x00ff00)


def create_discord_command_handler(engine, notifier):
    """
    創建 Discord 命令處理器
    
    Args:
        engine: 交易引擎實例
        notifier: Discord 通知器實例
    
    Returns:
        命令處理函數字典
    """
    
    def handle_stop():
        """處理停止命令"""
        try:
            engine.emergency_stop()
            return "✅ **系統已緊急停止**\n已取消所有訂單並停止交易引擎"
        except Exception as e:
            return f"❌ **停止失敗**\n錯誤: {str(e)}"
    
    def handle_cancel(symbol: Optional[str] = None):
        """處理取消訂單命令"""
        try:
            if symbol:
                count = engine.cancel_all_orders(symbol)
                return f"✅ **已取消 {symbol} 的訂單**\n取消數量: {count}"
            else:
                count = engine.cancel_all_orders()
                return f"✅ **已取消所有訂單**\n取消數量: {count}"
        except Exception as e:
            return f"❌ **取消訂單失敗**\n錯誤: {str(e)}"
    
    def handle_status():
        """處理狀態查詢命令"""
        try:
            summary = engine.get_account_summary()
            
            account = summary.get('account', {})
            risk = summary.get('risk', {})
            positions = summary.get('positions', {})
            
            status_text = f"""
**📊 系統狀態**

**帳戶:**
💰 權益: ${account.get('equity', 0):,.2f}
📊 保證金比率: {account.get('margin_ratio', 0):.2f}
💵 可用餘額: ${account.get('available', 0):,.2f}

**風險:**
⚠️ 等級: {risk.get('level', 'UNKNOWN')}
📈 有效槓桿: {risk.get('effective_leverage', 0):.2f}x

**倉位:**
📌 活躍倉位: {positions.get('total_positions', 0)} 個
💵 總價值: ${positions.get('total_value', 0):,.2f}
📊 未實現盈虧: ${positions.get('total_unrealized_pnl', 0):,.2f}

**訂單:**
📋 活躍訂單: {summary.get('active_orders', 0)} 個
            """
            
            return status_text.strip()
        except Exception as e:
            return f"❌ **獲取狀態失敗**\n錯誤: {str(e)}"
    
    def handle_positions():
        """處理倉位查詢命令"""
        try:
            positions = engine.get_positions()
            
            if not positions:
                return "📊 **當前無倉位**"
            
            pos_text = "**📊 當前倉位:**\n\n"
            
            for pos in positions:
                pnl_emoji = "📈" if pos.unrealized_pnl >= 0 else "📉"
                pos_text += f"""
**{pos.symbol}**
方向: {pos.side.value}
數量: {pos.quantity:.6f}
入場價: ${pos.entry_price:.4f}
當前價: ${pos.current_price:.4f}
{pnl_emoji} 盈虧: ${pos.unrealized_pnl:.2f} ({pos.get_pnl_percentage():.2f}%)
---
                """
            
            return pos_text.strip()
        except Exception as e:
            return f"❌ **獲取倉位失敗**\n錯誤: {str(e)}"
    
    def handle_risk():
        """處理風險查詢命令"""
        try:
            metrics = engine.risk_manager.get_risk_metrics()
            
            risk_emoji = {
                'LOW': '🟢',
                'MEDIUM': '🟡',
                'HIGH': '🟠',
                'CRITICAL': '🔴'
            }
            
            emoji = risk_emoji.get(metrics.risk_level, '⚪')
            
            risk_text = f"""
**⚠️ 風險狀態**

{emoji} **風險等級: {metrics.risk_level}**

**帳戶指標:**
💰 權益: ${metrics.account_equity:,.2f}
📊 保證金: ${metrics.total_margin:,.2f}
💵 可用: ${metrics.available_margin:,.2f}

**風險指標:**
📈 保證金比率: {metrics.margin_ratio:.2f}
⚡ 有效槓桿: {metrics.effective_leverage:.2f}x

**倉位:**
📌 總倉位價值: ${metrics.total_position_value:,.2f}
📊 未實現盈虧: ${metrics.total_unrealized_pnl:,.2f}

{'⚠️ **警告：帳戶存在風險！**' if metrics.is_at_risk else '✅ 帳戶狀態健康'}
            """
            
            return risk_text.strip()
        except Exception as e:
            return f"❌ **獲取風險信息失敗**\n錯誤: {str(e)}"
    
    return {
        'stop': handle_stop,
        'cancel': handle_cancel,
        'status': handle_status,
        'positions': handle_positions,
        'risk': handle_risk
    }


def parse_discord_command(message: str) -> tuple:
    """
    解析 Discord 命令
    
    Args:
        message: Discord 消息內容
    
    Returns:
        (command, args) 元組
    """
    # 移除前綴 !
    if not message.startswith('!'):
        return None, None
    
    parts = message[1:].strip().split()
    
    if not parts:
        return None, None
    
    command = parts[0].lower()
    args = parts[1:] if len(parts) > 1 else []
    
    return command, args

