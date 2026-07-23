"""
Simple monitoring system for trading engine.
"""
import time
import threading
from datetime import datetime
from typing import Dict, Optional

from .discord_notifier import DiscordNotifier
from .position_monitor import PositionMonitor
from .performance_monitor import PerformanceMonitor
from src.binance_sdk import BinanceFuturesClient
from util.utils import setup_logging


class MonitoringSystem:
    """Simple monitoring system."""
    
    def __init__(self, webhook_url: str = ""):
        """Initialize monitoring system."""
        self.logger = setup_logging("INFO")
        
        # Simple configuration
        self.webhook_url = webhook_url
        self.monitoring_interval = 5  # seconds
        
        # Components
        self.exchange_client = None
        self.discord_notifier = None
        self.position_monitor = None
        self.performance_monitor = None
        
        # System state
        self.is_running = False
        self.monitoring_thread = None
        
        # Initialize components
        self._initialize_components()
        
    def _initialize_components(self):
        """Initialize monitoring components."""
        try:
            # Initialize Discord notifier
            if self.webhook_url:
                self.discord_notifier = DiscordNotifier(
                    webhook_url=self.webhook_url,
                    enabled=True
                )
                self.logger.info("Discord notifier initialized")
            else:
                self.logger.warning("Discord webhook URL not provided")
                
            # Initialize performance monitor
            self.performance_monitor = PerformanceMonitor()
            self.logger.info("Performance monitor initialized")
            
        except Exception as e:
            self.logger.error(f"Error initializing components: {e}")
            
    def set_exchange_client(self, exchange_client: BinanceFuturesClient):
        """Set exchange client for monitoring."""
        self.exchange_client = exchange_client
        
        # Initialize position monitor with exchange client
        if self.exchange_client:
            self.position_monitor = PositionMonitor(
                exchange_client=exchange_client,
                monitoring_interval=self.monitoring_interval
            )
            self.logger.info("Position monitor initialized")
            
    def start_monitoring(self):
        """Start the monitoring system."""
        if self.is_running:
            self.logger.warning("Monitoring system already running")
            return
            
        if not self.exchange_client:
            self.logger.error("Exchange client not set, cannot start monitoring")
            return
            
        self.is_running = True
        
        # Start position monitoring
        if self.position_monitor:
            self.position_monitor.start_monitoring()
            
        # Start main monitoring loop
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        
        # Send startup notification
        if self.discord_notifier:
            self.discord_notifier.send_message("🚀 Monitoring System Started")
            
        self.logger.info("Monitoring system started")
        
    def stop_monitoring(self):
        """Stop the monitoring system."""
        self.is_running = False
        
        # Stop position monitoring
        if self.position_monitor:
            self.position_monitor.stop_monitoring()
            
        # Wait for monitoring thread
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
            
        # Send shutdown notification
        if self.discord_notifier:
            self.discord_notifier.send_message("🛑 Monitoring System Stopped")
            
        self.logger.info("Monitoring system stopped")
        
    def _monitoring_loop(self):
        """Main monitoring loop."""
        while self.is_running:
            try:
                # Simple monitoring - just check positions
                if self.position_monitor:
                    self.position_monitor.check_positions()
                
                time.sleep(self.monitoring_interval)
                
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")
                time.sleep(self.monitoring_interval)
                
    def record_trade(self, symbol: str, side: str, quantity: float, entry_price: float,
                     exit_price: float, entry_time: datetime, exit_time: datetime,
                     fees: float = 0.0, strategy: str = ""):
        """Record a completed trade."""
        if self.performance_monitor:
            self.performance_monitor.record_trade(
                symbol=symbol,
                side=side,
                quantity=quantity,
                entry_price=entry_price,
                exit_price=exit_price,
                entry_time=entry_time,
                exit_time=exit_time,
                fees=fees,
                strategy=strategy
            )
            
        # Send trade notification
        if self.discord_notifier:
            pnl = (exit_price - entry_price) * quantity if side == 'BUY' else (entry_price - exit_price) * quantity
            pnl_percentage = (pnl / (entry_price * quantity)) * 100 if entry_price > 0 else 0
            
            trade_message = f"""Trade Completed
Symbol: {symbol}
Side: {side}
Quantity: {quantity:.6f}
Entry Price: ${entry_price:.4f}
Exit Price: ${exit_price:.4f}
P&L: ${pnl:.2f}
P&L %: {pnl_percentage:.2f}%
Fees: ${fees:.2f}"""
            
            self.discord_notifier.send_message(trade_message)
            
    def get_system_status(self) -> Dict:
        """Get current system status."""
        status = {
            'monitoring_active': self.is_running,
            'exchange_connected': bool(self.exchange_client),
            'discord_enabled': bool(self.discord_notifier),
            'position_monitoring': bool(self.position_monitor and self.position_monitor.is_monitoring)
        }
        
        # Add position summary
        if self.position_monitor:
            status['positions'] = self.position_monitor.get_position_summary()
            
        return status