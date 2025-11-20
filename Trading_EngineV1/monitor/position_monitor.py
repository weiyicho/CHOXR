"""
Simple position monitoring system.
"""
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

from src.binance_sdk import BinanceFuturesClient
from util.utils import setup_logging


@dataclass
class SimplePosition:
    """Simple position data."""
    symbol: str
    side: str
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    position_value: float


class PositionMonitor:
    """Simple position monitoring system."""
    
    def __init__(self, exchange_client: BinanceFuturesClient, monitoring_interval: int = 5):
        """Initialize position monitor."""
        self.exchange_client = exchange_client
        self.monitoring_interval = monitoring_interval
        
        # Monitoring state
        self.is_monitoring = False
        self.monitor_thread = None
        self.last_positions = {}
        
        # Simple risk thresholds
        self.max_pnl_loss_percent = -10.0
        self.max_position_value = 1000.0
        
        self.logger = setup_logging("INFO")
        
    def start_monitoring(self):
        """Start position monitoring."""
        if self.is_monitoring:
            self.logger.warning("Position monitoring already running")
            return
            
        self.is_monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        
        self.logger.info("Position monitoring started")
        
    def stop_monitoring(self):
        """Stop position monitoring."""
        self.is_monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
            
        self.logger.info("Position monitoring stopped")
        
    def _monitoring_loop(self):
        """Main monitoring loop."""
        while self.is_monitoring:
            try:
                self.check_positions()
                time.sleep(self.monitoring_interval)
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")
                time.sleep(self.monitoring_interval)
                
    def check_positions(self):
        """Check all positions for alerts."""
        try:
            current_positions = self._get_current_positions()
            self._check_risk_metrics(current_positions)
            self.last_positions = current_positions
            
        except Exception as e:
            self.logger.error(f"Error checking positions: {e}")
                
    def _get_current_positions(self) -> Dict[str, SimplePosition]:
        """Get current positions from exchange."""
        try:
            positions = self.exchange_client.get_positions()
            current_positions = {}
            
            for pos in positions:
                if abs(pos.get('positionAmt', 0)) > 0:
                    symbol = pos.get('symbol', '')
                    side = 'LONG' if pos.get('positionAmt', 0) > 0 else 'SHORT'
                    quantity = abs(pos.get('positionAmt', 0))
                    entry_price = pos.get('entryPrice', 0)
                    current_price = pos.get('markPrice', 0)
                    unrealized_pnl = pos.get('unRealizedProfit', 0)
                    position_value = quantity * current_price
                    
                    current_positions[symbol] = SimplePosition(
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        entry_price=entry_price,
                        current_price=current_price,
                        unrealized_pnl=unrealized_pnl,
                        position_value=position_value
                    )
                    
            return current_positions
            
        except Exception as e:
            self.logger.error(f"Error getting positions: {e}")
            return {}
            
    def _check_risk_metrics(self, positions: Dict[str, SimplePosition]):
        """Check simple risk metrics for all positions."""
        for symbol, pos in positions.items():
            # Check P&L loss percentage
            if pos.entry_price > 0:
                pnl_percentage = (pos.unrealized_pnl / (pos.quantity * pos.entry_price)) * 100
                if pnl_percentage < self.max_pnl_loss_percent:
                    self.logger.warning(f"High loss detected for {symbol}: {pnl_percentage:.2f}%")
                
            # Check position value
            if pos.position_value > self.max_position_value:
                self.logger.warning(f"Large position detected for {symbol}: ${pos.position_value:.2f}")
                
    def get_position_summary(self) -> Dict:
        """Get current position summary."""
        try:
            positions = self._get_current_positions()
            
            if not positions:
                return {
                    'total_positions': 0,
                    'total_value': 0,
                    'total_pnl': 0,
                    'positions': []
                }
                
            total_value = sum(pos.position_value for pos in positions.values())
            total_pnl = sum(pos.unrealized_pnl for pos in positions.values())
            
            return {
                'total_positions': len(positions),
                'total_value': total_value,
                'total_pnl': total_pnl,
                'positions': [
                    {
                        'symbol': pos.symbol,
                        'side': pos.side,
                        'quantity': pos.quantity,
                        'entry_price': pos.entry_price,
                        'current_price': pos.current_price,
                        'unrealized_pnl': pos.unrealized_pnl,
                        'position_value': pos.position_value
                    }
                    for pos in positions.values()
                ]
            }
            
        except Exception as e:
            self.logger.error(f"Error getting position summary: {e}")
            return {'error': str(e)}