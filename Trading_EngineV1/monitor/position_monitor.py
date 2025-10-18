"""
Position Monitor
Real-time position monitoring and risk assessment
"""
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum

from src.binance_sdk import BinanceFuturesClient
from util.utils import setup_logging


class AlertLevel(Enum):
    """Alert levels for monitoring"""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"


@dataclass
class PositionAlert:
    """Position alert data structure"""
    symbol: str
    alert_type: str
    level: AlertLevel
    message: str
    timestamp: datetime
    data: Dict


@dataclass
class PositionMetrics:
    """Position metrics for monitoring"""
    symbol: str
    side: str
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    pnl_percentage: float
    position_value: float
    margin_used: float
    leverage: float
    timestamp: datetime


class PositionMonitor:
    """
    Real-time position monitoring system
    
    Monitors positions for:
    - P&L changes
    - Risk threshold breaches
    - Position size changes
    - Margin requirements
    - Stop loss triggers
    """
    
    def __init__(
        self,
        exchange_client: BinanceFuturesClient,
        alert_callback: Optional[Callable] = None,
        monitoring_interval: int = 5
    ):
        """
        Initialize position monitor
        
        Args:
            exchange_client: Exchange client for data fetching
            alert_callback: Callback function for alerts
            monitoring_interval: Monitoring interval in seconds
        """
        self.exchange_client = exchange_client
        self.alert_callback = alert_callback
        self.monitoring_interval = monitoring_interval
        
        # Monitoring state
        self.is_monitoring = False
        self.monitor_thread = None
        self.last_positions = {}
        self.alert_history = []
        
        # Risk thresholds
        self.risk_thresholds = {
            'max_pnl_loss_percent': -10.0,  # -10% P&L loss
            'max_position_value': 1000.0,   # $1000 max position
            'max_margin_ratio': 0.8,        # 80% margin usage
            'max_leverage': 10.0,           # 10x max leverage
            'stop_loss_percent': -5.0       # -5% stop loss
        }
        
        # Setup logging
        self.logger = setup_logging("PositionMonitor")
        
    def start_monitoring(self):
        """Start position monitoring"""
        if self.is_monitoring:
            self.logger.warning("Position monitoring already running")
            return
            
        self.is_monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        
        self.logger.info("Position monitoring started")
        
    def stop_monitoring(self):
        """Stop position monitoring"""
        self.is_monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
            
        self.logger.info("Position monitoring stopped")
        
    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.is_monitoring:
            try:
                self._check_positions()
                time.sleep(self.monitoring_interval)
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")
                time.sleep(self.monitoring_interval)
                
    def _check_positions(self):
        """Check all positions for alerts"""
        try:
            # Get current positions
            current_positions = self._get_current_positions()
            
            # Compare with previous positions
            self._compare_positions(current_positions)
            
            # Check risk metrics
            self._check_risk_metrics(current_positions)
            
            # Update last positions
            self.last_positions = current_positions
            
        except Exception as e:
            self.logger.error(f"Error checking positions: {e}")
            
    def _get_current_positions(self) -> Dict[str, PositionMetrics]:
        """Get current positions from exchange"""
        try:
            positions = self.exchange_client.get_positions()
            current_positions = {}
            
            for pos in positions:
                if abs(pos.get('positionAmt', 0)) > 0:  # Only non-zero positions
                    symbol = pos.get('symbol', '')
                    side = 'LONG' if pos.get('positionAmt', 0) > 0 else 'SHORT'
                    quantity = abs(pos.get('positionAmt', 0))
                    entry_price = pos.get('entryPrice', 0)
                    current_price = pos.get('markPrice', 0)
                    unrealized_pnl = pos.get('unRealizedProfit', 0)
                    
                    # Calculate metrics
                    position_value = quantity * current_price
                    pnl_percentage = (unrealized_pnl / (quantity * entry_price)) * 100 if entry_price > 0 else 0
                    margin_used = pos.get('initialMargin', 0)
                    leverage = pos.get('leverage', 1)
                    
                    current_positions[symbol] = PositionMetrics(
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        entry_price=entry_price,
                        current_price=current_price,
                        unrealized_pnl=unrealized_pnl,
                        pnl_percentage=pnl_percentage,
                        position_value=position_value,
                        margin_used=margin_used,
                        leverage=leverage,
                        timestamp=datetime.now()
                    )
                    
            return current_positions
            
        except Exception as e:
            self.logger.error(f"Error getting positions: {e}")
            return {}
            
    def _compare_positions(self, current_positions: Dict[str, PositionMetrics]):
        """Compare current positions with previous positions"""
        for symbol, current_pos in current_positions.items():
            if symbol in self.last_positions:
                last_pos = self.last_positions[symbol]
                
                # Check for significant P&L changes
                pnl_change = current_pos.unrealized_pnl - last_pos.unrealized_pnl
                if abs(pnl_change) > 10:  # $10 change threshold
                    self._create_alert(
                        symbol=symbol,
                        alert_type="pnl_change",
                        level=AlertLevel.INFO,
                        message=f"P&L changed by ${pnl_change:.2f}",
                        data={
                            'old_pnl': last_pos.unrealized_pnl,
                            'new_pnl': current_pos.unrealized_pnl,
                            'change': pnl_change
                        }
                    )
                    
                # Check for position size changes
                if current_pos.quantity != last_pos.quantity:
                    self._create_alert(
                        symbol=symbol,
                        alert_type="position_change",
                        level=AlertLevel.WARNING,
                        message=f"Position size changed from {last_pos.quantity:.6f} to {current_pos.quantity:.6f}",
                        data={
                            'old_quantity': last_pos.quantity,
                            'new_quantity': current_pos.quantity
                        }
                    )
            else:
                # New position
                self._create_alert(
                    symbol=symbol,
                    alert_type="new_position",
                    level=AlertLevel.INFO,
                    message=f"New {current_pos.side} position opened",
                    data={
                        'quantity': current_pos.quantity,
                        'entry_price': current_pos.entry_price,
                        'side': current_pos.side
                    }
                )
                
    def _check_risk_metrics(self, positions: Dict[str, PositionMetrics]):
        """Check risk metrics for all positions"""
        total_pnl = sum(pos.unrealized_pnl for pos in positions.values())
        total_position_value = sum(pos.position_value for pos in positions.values())
        total_margin = sum(pos.margin_used for pos in positions.values())
        
        # Check individual position risks
        for symbol, pos in positions.items():
            # P&L loss threshold
            if pos.pnl_percentage < self.risk_thresholds['max_pnl_loss_percent']:
                self._create_alert(
                    symbol=symbol,
                    alert_type="pnl_loss_threshold",
                    level=AlertLevel.CRITICAL,
                    message=f"P&L loss exceeded threshold: {pos.pnl_percentage:.2f}%",
                    data={
                        'pnl_percentage': pos.pnl_percentage,
                        'threshold': self.risk_thresholds['max_pnl_loss_percent']
                    }
                )
                
            # Position value threshold
            if pos.position_value > self.risk_thresholds['max_position_value']:
                self._create_alert(
                    symbol=symbol,
                    alert_type="position_value_threshold",
                    level=AlertLevel.WARNING,
                    message=f"Position value exceeded threshold: ${pos.position_value:.2f}",
                    data={
                        'position_value': pos.position_value,
                        'threshold': self.risk_thresholds['max_position_value']
                    }
                )
                
            # Leverage threshold
            if pos.leverage > self.risk_thresholds['max_leverage']:
                self._create_alert(
                    symbol=symbol,
                    alert_type="leverage_threshold",
                    level=AlertLevel.WARNING,
                    message=f"Leverage exceeded threshold: {pos.leverage:.1f}x",
                    data={
                        'leverage': pos.leverage,
                        'threshold': self.risk_thresholds['max_leverage']
                    }
                )
                
        # Check overall account risk
        if total_margin > 0:
            margin_ratio = total_margin / (total_margin + total_pnl) if total_pnl > 0 else 1.0
            if margin_ratio > self.risk_thresholds['max_margin_ratio']:
                self._create_alert(
                    symbol="ACCOUNT",
                    alert_type="margin_ratio_threshold",
                    level=AlertLevel.CRITICAL,
                    message=f"Margin ratio exceeded threshold: {margin_ratio:.2f}",
                    data={
                        'margin_ratio': margin_ratio,
                        'threshold': self.risk_thresholds['max_margin_ratio'],
                        'total_margin': total_margin,
                        'total_pnl': total_pnl
                    }
                )
                
    def _create_alert(
        self,
        symbol: str,
        alert_type: str,
        level: AlertLevel,
        message: str,
        data: Dict
    ):
        """Create and process alert"""
        alert = PositionAlert(
            symbol=symbol,
            alert_type=alert_type,
            level=level,
            message=message,
            timestamp=datetime.now(),
            data=data
        )
        
        # Add to history
        self.alert_history.append(alert)
        
        # Keep only last 100 alerts
        if len(self.alert_history) > 100:
            self.alert_history = self.alert_history[-100:]
            
        # Log alert
        self.logger.info(f"Alert [{level.value}] {symbol}: {message}")
        
        # Call callback if provided
        if self.alert_callback:
            try:
                self.alert_callback(alert)
            except Exception as e:
                self.logger.error(f"Alert callback error: {e}")
                
    def get_alert_history(self, limit: int = 50) -> List[PositionAlert]:
        """Get recent alert history"""
        return self.alert_history[-limit:]
        
    def get_position_summary(self) -> Dict:
        """Get current position summary"""
        try:
            positions = self._get_current_positions()
            
            if not positions:
                return {
                    'total_positions': 0,
                    'total_value': 0,
                    'total_pnl': 0,
                    'total_margin': 0,
                    'positions': []
                }
                
            total_value = sum(pos.position_value for pos in positions.values())
            total_pnl = sum(pos.unrealized_pnl for pos in positions.values())
            total_margin = sum(pos.margin_used for pos in positions.values())
            
            return {
                'total_positions': len(positions),
                'total_value': total_value,
                'total_pnl': total_pnl,
                'total_margin': total_margin,
                'positions': [
                    {
                        'symbol': pos.symbol,
                        'side': pos.side,
                        'quantity': pos.quantity,
                        'entry_price': pos.entry_price,
                        'current_price': pos.current_price,
                        'unrealized_pnl': pos.unrealized_pnl,
                        'pnl_percentage': pos.pnl_percentage,
                        'position_value': pos.position_value,
                        'leverage': pos.leverage
                    }
                    for pos in positions.values()
                ]
            }
            
        except Exception as e:
            self.logger.error(f"Error getting position summary: {e}")
            return {'error': str(e)}
            
    def update_risk_thresholds(self, thresholds: Dict):
        """Update risk thresholds"""
        self.risk_thresholds.update(thresholds)
        self.logger.info(f"Risk thresholds updated: {thresholds}")
        
    def get_risk_thresholds(self) -> Dict:
        """Get current risk thresholds"""
        return self.risk_thresholds.copy()
