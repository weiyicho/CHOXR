"""
Integrated Monitoring System
Combines all monitoring components into a unified system
"""
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass

from .discord_notifier import DiscordNotifier
from .discord_commander import DiscordCommander
from .position_monitor import PositionMonitor, AlertLevel, PositionAlert
from .performance_monitor import PerformanceMonitor
from src.binance_sdk import BinanceFuturesClient
from util.utils import load_config, setup_logging


@dataclass
class MonitoringConfig:
    """Monitoring system configuration"""
    discord_webhook_url: str
    discord_channel_id: Optional[str] = None
    monitoring_interval: int = 5
    position_alerts_enabled: bool = True
    performance_alerts_enabled: bool = True
    risk_alerts_enabled: bool = True
    auto_reports_enabled: bool = True
    report_interval_hours: int = 24


class MonitoringSystem:
    """
    Integrated monitoring system that combines:
    - Position monitoring
    - Performance tracking
    - Discord notifications
    - Risk management
    - Automated reporting
    """
    
    def __init__(self, config_file: str = "config/monitoring.json"):
        """
        Initialize monitoring system
        
        Args:
            config_file: Configuration file path
        """
        self.config_file = config_file
        self.logger = setup_logging("MonitoringSystem")
        
        # Load configuration
        self.config = self._load_config()
        
        # Initialize components
        self.exchange_client = None
        self.discord_notifier = None
        self.discord_commander = None
        self.position_monitor = None
        self.performance_monitor = None
        
        # System state
        self.is_running = False
        self.monitoring_thread = None
        self.last_report_time = datetime.now()
        
        # Initialize components
        self._initialize_components()
        
    def _load_config(self) -> MonitoringConfig:
        """Load monitoring configuration"""
        try:
            config_data = load_config(self.config_file)
            return MonitoringConfig(
                discord_webhook_url=config_data.get('discord', {}).get('webhook_url', ''),
                discord_channel_id=config_data.get('discord', {}).get('channel_id'),
                monitoring_interval=config_data.get('monitoring', {}).get('interval', 5),
                position_alerts_enabled=config_data.get('alerts', {}).get('position', True),
                performance_alerts_enabled=config_data.get('alerts', {}).get('performance', True),
                risk_alerts_enabled=config_data.get('alerts', {}).get('risk', True),
                auto_reports_enabled=config_data.get('reports', {}).get('auto', True),
                report_interval_hours=config_data.get('reports', {}).get('interval_hours', 24)
            )
        except Exception as e:
            self.logger.error(f"Error loading monitoring config: {e}")
            # Return default config
            return MonitoringConfig(discord_webhook_url="")
            
    def _initialize_components(self):
        """Initialize monitoring components"""
        try:
            # Initialize Discord components
            if self.config.discord_webhook_url:
                self.discord_notifier = DiscordNotifier(
                    webhook_url=self.config.discord_webhook_url,
                    enabled=True
                )
                self.discord_commander = DiscordCommander(
                    webhook_url=self.config.discord_webhook_url,
                    channel_id=self.config.discord_channel_id
                )
                self.logger.info("Discord components initialized")
            else:
                self.logger.warning("Discord webhook URL not configured")
                
            # Initialize performance monitor
            self.performance_monitor = PerformanceMonitor()
            self.logger.info("Performance monitor initialized")
            
        except Exception as e:
            self.logger.error(f"Error initializing components: {e}")
            
    def set_exchange_client(self, exchange_client: BinanceFuturesClient):
        """Set exchange client for monitoring"""
        self.exchange_client = exchange_client
        
        # Initialize position monitor with exchange client
        if self.exchange_client:
            self.position_monitor = PositionMonitor(
                exchange_client=exchange_client,
                alert_callback=self._handle_position_alert,
                monitoring_interval=self.config.monitoring_interval
            )
            self.logger.info("Position monitor initialized with exchange client")
            
    def start_monitoring(self):
        """Start the monitoring system"""
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
            self.discord_notifier.send_embed(
                title="🚀 Monitoring System Started",
                description="Trading engine monitoring is now active",
                color=0x00ff00
            )
            
        self.logger.info("Monitoring system started")
        
    def stop_monitoring(self):
        """Stop the monitoring system"""
        self.is_running = False
        
        # Stop position monitoring
        if self.position_monitor:
            self.position_monitor.stop_monitoring()
            
        # Wait for monitoring thread
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
            
        # Send shutdown notification
        if self.discord_notifier:
            self.discord_notifier.send_embed(
                title="🛑 Monitoring System Stopped",
                description="Trading engine monitoring has been stopped",
                color=0xff0000
            )
            
        self.logger.info("Monitoring system stopped")
        
    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.is_running:
            try:
                # Check for automated reports
                if self.config.auto_reports_enabled:
                    self._check_automated_reports()
                    
                # Check system health
                self._check_system_health()
                
                time.sleep(self.config.monitoring_interval)
                
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")
                time.sleep(self.config.monitoring_interval)
                
    def _handle_position_alert(self, alert: PositionAlert):
        """Handle position alerts"""
        if not self.discord_notifier:
            return
            
        # Determine alert color based on level
        color_map = {
            AlertLevel.INFO: 0x0099ff,      # Blue
            AlertLevel.WARNING: 0xffa500,    # Orange
            AlertLevel.CRITICAL: 0xff6600,   # Dark Orange
            AlertLevel.EMERGENCY: 0xff0000   # Red
        }
        
        color = color_map.get(alert.level, 0xff0000)
        
        # Create alert message
        fields = [
            {"name": "Symbol", "value": alert.symbol, "inline": True},
            {"name": "Type", "value": alert.alert_type, "inline": True},
            {"name": "Level", "value": alert.level.value, "inline": True}
        ]
        
        # Add data fields
        for key, value in alert.data.items():
            if isinstance(value, (int, float)):
                fields.append({"name": key.title(), "value": f"{value:.2f}", "inline": True})
            else:
                fields.append({"name": key.title(), "value": str(value), "inline": True})
                
        self.discord_notifier.send_embed(
            title=f"⚠️ Position Alert - {alert.level.value}",
            description=alert.message,
            color=color,
            fields=fields
        )
        
    def _check_automated_reports(self):
        """Check if it's time for automated reports"""
        now = datetime.now()
        time_since_last_report = now - self.last_report_time
        
        if time_since_last_report >= timedelta(hours=self.config.report_interval_hours):
            self._send_automated_report()
            self.last_report_time = now
            
    def _send_automated_report(self):
        """Send automated performance report"""
        if not self.discord_notifier:
            return
            
        try:
            # Get performance metrics for last 24 hours
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=24)
            
            metrics = self.performance_monitor.get_performance_metrics(start_time, end_time)
            
            # Create report
            fields = [
                {"name": "Total Trades", "value": str(metrics.total_trades), "inline": True},
                {"name": "Win Rate", "value": f"{metrics.win_rate:.1f}%", "inline": True},
                {"name": "Net P&L", "value": f"${metrics.net_pnl:.2f}", "inline": True},
                {"name": "Total P&L", "value": f"${metrics.total_pnl:.2f}", "inline": True},
                {"name": "Fees", "value": f"${metrics.total_fees:.2f}", "inline": True},
                {"name": "Profit Factor", "value": f"{metrics.profit_factor:.2f}", "inline": True}
            ]
            
            # Add position summary if available
            if self.position_monitor:
                position_summary = self.position_monitor.get_position_summary()
                if position_summary.get('total_positions', 0) > 0:
                    fields.extend([
                        {"name": "Active Positions", "value": str(position_summary['total_positions']), "inline": True},
                        {"name": "Position Value", "value": f"${position_summary['total_value']:.2f}", "inline": True},
                        {"name": "Unrealized P&L", "value": f"${position_summary['total_pnl']:.2f}", "inline": True}
                    ])
                    
            self.discord_notifier.send_embed(
                title="📊 Daily Performance Report",
                description=f"Performance summary for the last 24 hours",
                color=0x0099ff,
                fields=fields
            )
            
        except Exception as e:
            self.logger.error(f"Error sending automated report: {e}")
            
    def _check_system_health(self):
        """Check system health and send alerts if needed"""
        try:
            # Check exchange connectivity
            if self.exchange_client:
                # Simple connectivity check
                account_info = self.exchange_client.get_account_info()
                if not account_info:
                    self._send_health_alert("Exchange connectivity issue detected")
                    
        except Exception as e:
            self.logger.error(f"System health check error: {e}")
            self._send_health_alert(f"System health check failed: {str(e)}")
            
    def _send_health_alert(self, message: str):
        """Send system health alert"""
        if self.discord_notifier:
            self.discord_notifier.send_embed(
                title="🚨 System Health Alert",
                description=message,
                color=0xff0000
            )
            
    def record_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        exit_price: float,
        entry_time: datetime,
        exit_time: datetime,
        fees: float = 0.0,
        strategy: str = ""
    ):
        """Record a completed trade"""
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
            
            color = 0x00ff00 if pnl > 0 else 0xff0000
            emoji = "📈" if pnl > 0 else "📉"
            
            self.discord_notifier.send_embed(
                title=f"{emoji} Trade Completed",
                description=f"**{symbol}** {side}",
                color=color,
                fields=[
                    {"name": "Quantity", "value": f"{quantity:.6f}", "inline": True},
                    {"name": "Entry Price", "value": f"${entry_price:.4f}", "inline": True},
                    {"name": "Exit Price", "value": f"${exit_price:.4f}", "inline": True},
                    {"name": "P&L", "value": f"${pnl:.2f}", "inline": True},
                    {"name": "P&L %", "value": f"{pnl_percentage:.2f}%", "inline": True},
                    {"name": "Fees", "value": f"${fees:.2f}", "inline": True}
                ]
            )
            
    def get_system_status(self) -> Dict:
        """Get current system status"""
        status = {
            'monitoring_active': self.is_running,
            'exchange_connected': bool(self.exchange_client),
            'discord_enabled': bool(self.discord_notifier),
            'position_monitoring': bool(self.position_monitor and self.position_monitor.is_monitoring),
            'last_report_time': self.last_report_time.isoformat(),
            'config': {
                'monitoring_interval': self.config.monitoring_interval,
                'auto_reports': self.config.auto_reports_enabled,
                'report_interval_hours': self.config.report_interval_hours
            }
        }
        
        # Add position summary
        if self.position_monitor:
            status['positions'] = self.position_monitor.get_position_summary()
            
        # Add performance summary
        if self.performance_monitor:
            metrics = self.performance_monitor.get_performance_metrics()
            status['performance'] = {
                'total_trades': metrics.total_trades,
                'win_rate': metrics.win_rate,
                'net_pnl': metrics.net_pnl,
                'profit_factor': metrics.profit_factor
            }
            
        return status
        
    def send_manual_report(self):
        """Send manual performance report"""
        if not self.discord_notifier:
            return False
            
        try:
            # Get comprehensive performance report
            report = self.performance_monitor.generate_report()
            
            # Split report into chunks if too long
            if len(report) > 2000:
                chunks = [report[i:i+2000] for i in range(0, len(report), 2000)]
                for i, chunk in enumerate(chunks):
                    self.discord_notifier.send_message(
                        content=f"```\n{chunk}\n```",
                        username=f"Performance Report {i+1}"
                    )
            else:
                self.discord_notifier.send_message(
                    content=f"```\n{report}\n```",
                    username="Performance Report"
                )
                
            return True
            
        except Exception as e:
            self.logger.error(f"Error sending manual report: {e}")
            return False
