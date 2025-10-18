"""
Discord 通知器
發送交易通知到 Discord
"""
import requests
import json
from datetime import datetime
from typing import Dict, List, Optional


class DiscordNotifier:
    """Discord 通知器"""
    
    def __init__(self, webhook_url: str, enabled: bool = True):
        """
        初始化 Discord 通知器
        
        Args:
            webhook_url: Discord Webhook URL
            enabled: 是否啟用通知
        """
        self.webhook_url = webhook_url
        self.enabled = enabled and webhook_url  # 有 URL 才啟用
        
        if self.enabled:
            print("✓ Discord 通知已啟用")
        else:
            print("⚠️  Discord 通知未啟用（未設置 webhook_url）")
    
    def send_message(self, content: str, username: str = "Trading Engine") -> bool:
        """
        發送文字訊息
        
        Args:
            content: 訊息內容
            username: 顯示名稱
        
        Returns:
            是否發送成功
        """
        if not self.enabled:
            return False
        
        try:
            data = {
                "content": content,
                "username": username,
                "embeds": []
            }
            
            headers = {"Content-Type": "application/json"}
            response = requests.post(
                self.webhook_url,
                data=json.dumps(data),
                headers=headers,
                timeout=5
            )
            
            if response.status_code == 204:
                return True
            else:
                print(f"Discord 發送失敗: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"Discord 發送錯誤: {e}")
            return False
    
    def send_embed(
        self,
        title: str,
        description: str = "",
        color: int = 0x00ff00,
        fields: Optional[List[Dict]] = None,
        username: str = "Trading Engine"
    ) -> bool:
        """
        發送嵌入訊息（更美觀）
        
        Args:
            title: 標題
            description: 描述
            color: 顏色（十六進位）
            fields: 欄位列表 [{"name": "...", "value": "...", "inline": True}, ...]
            username: 顯示名稱
        
        Returns:
            是否發送成功
        """
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
            
            data = {
                "username": username,
                "embeds": [embed]
            }
            
            headers = {"Content-Type": "application/json"}
            response = requests.post(
                self.webhook_url,
                data=json.dumps(data),
                headers=headers,
                timeout=5
            )
            
            if response.status_code == 204:
                return True
            else:
                print(f"Discord 發送失敗: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"Discord 發送錯誤: {e}")
            return False
    
    def notify_scan_result(self, opportunities: List[Dict]) -> bool:
        """
        通知掃描結果
        
        Args:
            opportunities: 機會列表
        
        Returns:
            是否發送成功
        """
        if not opportunities:
            return self.send_embed(
                title="📊 Funding Rate 掃描完成",
                description="未發現符合條件的交易對",
                color=0xffa500  # 橙色
            )
        
        fields = []
        for opp in opportunities[:10]:  # 最多顯示 10 個
            symbol = opp.get('symbol', 'Unknown')
            annual_fr = opp.get('annual_fr', 0)
            position = opp.get('position', 0)
            position_str = "SHORT" if position == -1 else "LONG"
            
            fields.append({
                "name": f"💰 {symbol}",
                "value": f"FR: {annual_fr:.2%}\n方向: {position_str}",
                "inline": True
            })
        
        return self.send_embed(
            title=f"✅ 發現 {len(opportunities)} 個機會！",
            description=f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            color=0x00ff00,  # 綠色
            fields=fields
        )
    
    def notify_order_placed(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: Optional[float],
        order_type: str,
        account_type: str
    ) -> bool:
        """
        通知訂單已下達
        
        Args:
            symbol: 交易對
            side: 方向
            quantity: 數量
            price: 價格
            order_type: 訂單類型
            account_type: 帳戶類型
        
        Returns:
            是否發送成功
        """
        price_str = f"${price:.4f}" if price else "MARKET"
        
        return self.send_embed(
            title=f"📋 訂單已提交",
            description=f"**{symbol}** - {account_type.upper()}",
            color=0x0099ff,  # 藍色
            fields=[
                {"name": "方向", "value": side, "inline": True},
                {"name": "數量", "value": f"{quantity:.6f}", "inline": True},
                {"name": "價格", "value": price_str, "inline": True},
                {"name": "類型", "value": order_type, "inline": True},
                {"name": "時間", "value": datetime.now().strftime('%H:%M:%S'), "inline": True}
            ]
        )
    
    def notify_order_filled(
        self,
        symbol: str,
        side: str,
        quantity: float,
        avg_price: float
    ) -> bool:
        """
        通知訂單已成交
        
        Args:
            symbol: 交易對
            side: 方向
            quantity: 數量
            avg_price: 平均成交價
        
        Returns:
            是否發送成功
        """
        return self.send_embed(
            title=f"✅ 訂單已成交",
            description=f"**{symbol}**",
            color=0x00ff00,  # 綠色
            fields=[
                {"name": "方向", "value": side, "inline": True},
                {"name": "數量", "value": f"{quantity:.6f}", "inline": True},
                {"name": "成交價", "value": f"${avg_price:.4f}", "inline": True}
            ]
        )
    
    def notify_risk_warning(self, risk_level: str, message: str) -> bool:
        """
        通知風險警告
        
        Args:
            risk_level: 風險等級
            message: 訊息
        
        Returns:
            是否發送成功
        """
        color_map = {
            'LOW': 0x00ff00,      # 綠色
            'MEDIUM': 0xffa500,   # 橙色
            'HIGH': 0xff6600,     # 深橙色
            'CRITICAL': 0xff0000  # 紅色
        }
        
        return self.send_embed(
            title=f"⚠️ 風險警告 - {risk_level}",
            description=message,
            color=color_map.get(risk_level, 0xff0000)
        )
    
    def notify_error(self, error_message: str) -> bool:
        """
        通知錯誤
        
        Args:
            error_message: 錯誤訊息
        
        Returns:
            是否發送成功
        """
        return self.send_embed(
            title="❌ 系統錯誤",
            description=error_message,
            color=0xff0000  # 紅色
        )
    
    def notify_strategy_status(
        self,
        strategy_id: str,
        active_symbols: List[str],
        account_summary: Dict
    ) -> bool:
        """
        通知策略狀態
        
        Args:
            strategy_id: 策略ID
            active_symbols: 活躍交易對列表
            account_summary: 帳戶摘要
        
        Returns:
            是否發送成功
        """
        account = account_summary.get('account', {})
        risk = account_summary.get('risk', {})
        positions = account_summary.get('positions', {})
        
        fields = [
            {
                "name": "💰 帳戶權益",
                "value": f"${account.get('equity', 0):,.2f}",
                "inline": True
            },
            {
                "name": "📊 保證金比率",
                "value": f"{account.get('margin_ratio', 0):.2f}",
                "inline": True
            },
            {
                "name": "⚠️ 風險等級",
                "value": risk.get('level', 'UNKNOWN'),
                "inline": True
            },
            {
                "name": "📈 活躍倉位",
                "value": f"{positions.get('total_positions', 0)} 個",
                "inline": True
            },
            {
                "name": "💵 未實現盈虧",
                "value": f"${positions.get('total_unrealized_pnl', 0):,.2f}",
                "inline": True
            }
        ]
        
        if active_symbols:
            fields.append({
                "name": "🎯 活躍交易對",
                "value": ", ".join(active_symbols[:5]),  # 最多顯示 5 個
                "inline": False
            })
        
        return self.send_embed(
            title=f"📊 策略狀態 - {strategy_id}",
            description=f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            color=0x0099ff,  # 藍色
            fields=fields
        )

