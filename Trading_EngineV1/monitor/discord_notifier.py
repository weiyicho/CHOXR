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
    
    def send_accounts_summary(self, formatted_content: str) -> bool:
        """Send pre-formatted accounts summary to Discord."""
        if not self.enabled:
            return False
            
        try:
            return self.send_message(formatted_content)
            
        except Exception as e:
            print(f"Discord accounts summary error: {e}")
            return False
    
    def send_positions_summary(self, formatted_content: str) -> bool:
        """Send pre-formatted positions summary to Discord."""
        if not self.enabled:
            return False
            
        try:
            return self.send_message(formatted_content)
            
        except Exception as e:
            print(f"Discord positions summary error: {e}")
            return False
    
    def send_performance_summary(self, formatted_content: str) -> bool:
        """Send pre-formatted performance summary to Discord."""
        if not self.enabled:
            return False
            
        try:
            return self.send_message(formatted_content)
            
        except Exception as e:
            print(f"Discord performance summary error: {e}")
            return False
    def send_picture(self, pic_path, username="Webhook Bot"):

        with open(pic_path, "rb") as pic_file:
            data = {"username": username, "embeds": []}
            files = {"file": pic_file}
            response = requests.post(self.webhook_url, data=data, files=files)

        if response.status_code == 200:
            print("success!")
        else:
            print(f"error: {response.status_code}")

        return response.status_code