"""
Integrated monitoring system that orchestrates all monitoring components.
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
from risk.risks import RiskManager, AccountStatus
from util.utils import load_config, setup_logging


@dataclass
class MonitoringConfig:
    """Monitoring system configuration."""
    discord_webhook_url: str
    discord_channel_id: Optional[str] = None
    monitoring_interval: int = 5
    position_alerts_enabled: bool = True
    performance_alerts_enabled: bool = True
    risk_alerts_enabled: bool = True
    auto_reports_enabled: bool = True
    report_interval_hours: int = 24


class MonitoringSystem:
    """Integrated monitoring system orchestrator."""
    
    def __init__(self, config_file: str = "config/monitoring.json"):
        """Initialize monitoring system."""
        self.config_file = config_file
        self.logger = setup_logging("INFO")
        
        # Load configuration
        self.config = self._load_config()
        
        # Initialize components
        self.exchange_client = None
        self.risk_manager = None
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
        """Load monitoring configuration."""
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
            return MonitoringConfig(discord_webhook_url="")
            
    def _initialize_components(self):
        """Initialize monitoring components."""
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
        """Set exchange client for monitoring."""
        self.exchange_client = exchange_client
        
        # Initialize components with exchange client
        if self.exchange_client:
            # Initialize position monitor with exchange client
            self.position_monitor = PositionMonitor(
                exchange_client=exchange_client,
                alert_callback=self._handle_position_alert,
                monitoring_interval=self.config.monitoring_interval
            )
            self.logger.info("Position monitor initialized with exchange client")
            
            # Initialize risk manager (will be populated with data during monitoring)
            self.risk_manager = None  # Will be initialized when we get account data
            self.logger.info("Risk manager placeholder initialized")
            
    def start_monitoring(self):
        """Start the monitoring system."""
        if self.is_running:
            self.logger.warning("Monitoring system already running")
            return
            
        if not self.exchange_client:
            self.logger.error("Exchange client not set, cannot start monitoring")
            return
            
        self.is_running = True
        
        # Initialize RiskManager with current account data
        self._initialize_risk_manager()
        
        # Start position monitoring
        if self.position_monitor:
            self.position_monitor.start_monitoring()
            
        # Start main monitoring loop
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        
        # Send startup notification
        if self.discord_notifier:
            self.discord_notifier.send_message("🚀 Monitoring System Started\nTrading engine monitoring is now active")
            
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
            self.discord_notifier.send_message("🛑 Monitoring System Stopped\nTrading engine monitoring has been stopped")
            
        self.logger.info("Monitoring system stopped")
        
    def _monitoring_loop(self):
        """Main monitoring loop."""
        while self.is_running:
            try:
                # Check for automated reports
                if self.config.auto_reports_enabled:
                    self._check_automated_reports()
                    
                # Check system health (including RiskManager health)
                self._check_system_health()
                
                # Refresh RiskManager with latest data periodically
                if self.risk_manager:
                    self._initialize_risk_manager()
                
                time.sleep(self.config.monitoring_interval)
                
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")
                time.sleep(self.config.monitoring_interval)
                
    def _handle_position_alert(self, alert: PositionAlert):
        """Handle position alerts."""
        if not self.discord_notifier:
            return
            
        # Create alert message
        alert_message = f"Alert: {alert.symbol}\nType: {alert.alert_type}\nLevel: {alert.level.value}\nMessage: {alert.message}"
        
        # Add data fields
        if alert.data:
            alert_message += "\nData:"
            for key, value in alert.data.items():
                if isinstance(value, (int, float)):
                    alert_message += f"\n  {key}: {value:.2f}"
                else:
                    alert_message += f"\n  {key}: {value}"
                    
        self.discord_notifier.send_message(alert_message)
        
    def _check_automated_reports(self):
        """Check if it's time for automated reports."""
        now = datetime.now()
        time_since_last_report = now - self.last_report_time
        
        if time_since_last_report >= timedelta(hours=self.config.report_interval_hours):
            self._send_automated_report()
            self.last_report_time = now
            
    def _send_automated_report(self):
        """Send automated performance report."""
        if not self.discord_notifier:
            return
            
        try:
            # Get performance metrics for last 24 hours
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=24)
            
            metrics = self.performance_monitor.get_performance_metrics(start_time, end_time)
            
            # Create report message
            report_message = f"""Daily Performance Report
Period: Last 24 Hours
Total Trades: {metrics.total_trades}
Win Rate: {metrics.win_rate:.1f}%
Net P&L: ${metrics.net_pnl:.2f}
Total P&L: ${metrics.total_pnl:.2f}
Fees: ${metrics.total_fees:.2f}
Profit Factor: {metrics.profit_factor:.2f}"""
            
            # Add position summary if available
            if self.position_monitor:
                position_summary = self.position_monitor.get_position_summary()
                if position_summary.get('total_positions', 0) > 0:
                    report_message += f"""
Active Positions: {position_summary['total_positions']}
Position Value: ${position_summary['total_value']:.2f}
Unrealized P&L: ${position_summary['total_pnl']:.2f}"""
                    
            self.discord_notifier.send_message(report_message)
            
        except Exception as e:
            self.logger.error(f"Error sending automated report: {e}")
            
    def _initialize_risk_manager(self):
        """Initialize RiskManager with current account data."""
        if not self.exchange_client:
            return False
            
        try:
            # Get current account data
            account_data = self.exchange_client.get_account_info()
            
            # Initialize RiskManager with account data
            self.risk_manager = RiskManager(account_data)
            
            self.logger.info("RiskManager initialized with current account data")
            return True
            
        except Exception as e:
            self.logger.error(f"Error initializing RiskManager: {e}")
            return False
    
    def get_accounts_summary(self):
        """Get accounts summary using RiskManager."""
        if not self.exchange_client or not self.risk_manager:
            return None
            
        try:
            # Get current data
            balance_data = self.exchange_client.get_balances()
            positions_data = self.exchange_client.get_positions()
            
            # Use RiskManager to generate summary
            accounts_summary = self.risk_manager.get_accounts_summary(balance_data, positions_data)
            
            return accounts_summary
            
        except Exception as e:
            self.logger.error(f"Error getting accounts summary: {e}")
            return None
    
    def get_positions_summary(self):
        """Get positions summary using RiskManager."""
        if not self.exchange_client or not self.risk_manager:
            return None
            
        try:
            # Get current positions data
            positions_data = self.exchange_client.get_positions()
            
            # Use RiskManager to generate summary
            positions_summary = self.risk_manager.get_positions_summary(positions_data)
            
            return positions_summary
            
        except Exception as e:
            self.logger.error(f"Error getting positions summary: {e}")
            return None
    
    def get_performance_summary(self):
        """Get performance summary using PerformanceMonitor."""
        if not self.performance_monitor:
            return None
            
        try:
            # Get performance metrics for last 24 hours
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=24)
            
            metrics = self.performance_monitor.get_performance_metrics(start_time, end_time)
            
            return {
                'period': 'Last 24 Hours',
                'total_trades': metrics.total_trades,
                'win_rate': metrics.win_rate,
                'net_pnl': metrics.net_pnl,
                'total_fees': metrics.total_fees,
                'profit_factor': metrics.profit_factor,
                'best_trade': metrics.best_trade,
                'worst_trade': metrics.worst_trade,
                'max_drawdown': metrics.max_drawdown
            }
            
        except Exception as e:
            self.logger.error(f"Error getting performance summary: {e}")
            return None
    
    def _format_accounts_summary(self, accounts_data: list) -> str:
        """Format accounts data into Discord table format."""
        if not accounts_data:
            return "Accounts:\nNo account data available"
        
        total_account_value = sum(acc.get('account_value', 0) for acc in accounts_data)
        total_position_value = sum(acc.get('position_value', 0) for acc in accounts_data)
        total_available = sum(acc.get('available_balance', 0) for acc in accounts_data)
        
        # Calculate weighted leverage
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
        
        return content
    
    def send_accounts_summary(self):
        """Send accounts summary to Discord using RiskManager data."""
        if not self.discord_notifier:
            self.logger.warning("Discord notifier not available")
            return False
            
        try:
            accounts_summary = self.get_accounts_summary()
            if not accounts_summary:
                self.logger.warning("Could not generate accounts summary")
                return False
                
            # Format the data
            formatted_content = self._format_accounts_summary([accounts_summary])
            
            # Send using Discord notifier
            self.discord_notifier.send_accounts_summary(formatted_content)
            
            self.logger.info("Accounts summary sent to Discord")
            return True
            
        except Exception as e:
            self.logger.error(f"Error sending accounts summary: {e}")
            return False
    
    def _format_positions_summary(self, positions_data: dict) -> str:
        """Format positions data into Discord table format."""
        positions = positions_data.get('positions', {})
        
        if not positions:
            return "Positions:\nNo active positions"
        
        total_pnl = sum(pos.get('unrealized_pnl', 0) for pos in positions.values())
        total_pnl_pct = sum(pos.get('pnl_percentage', 0) for pos in positions.values()) / len(positions) if positions else 0
        
        content = "Positions:\n"
        content += "symbol      | side | quantity  | entry_price | current_price | pnl  | pnl_pct\n"
        content += "---------------------------------------------------------------------------\n"
        
        for symbol, pos in positions.items():
            symbol_name = symbol.ljust(12)
            side = pos.get('side', '').ljust(4)
            quantity = f"{pos.get('quantity', 0):>9,.4f}"
            entry_price = f"{pos.get('entry_price', 0):>11,.4f}"
            current_price = f"{pos.get('mark_price', 0):>13,.4f}"
            pnl = f"{pos.get('unrealized_pnl', 0):>4,.2f}"
            pnl_pct = f"{pos.get('pnl_percentage', 0):>7,.2f}%"
            content += f"{symbol_name} | {side} | {quantity} | {entry_price} | {current_price} | {pnl} | {pnl_pct}\n"
        
        content += "---------------------------------------------------------------------------\n"
        content += f"{'TOTAL':>12} | {'':4} | {'':9} | {'':11} | {'':13} | {total_pnl:>4,.2f} | {total_pnl_pct:>7,.2f}%"
        
        return content
    
    def send_positions_summary(self):
        """Send positions summary to Discord using RiskManager data."""
        if not self.discord_notifier:
            self.logger.warning("Discord notifier not available")
            return False
            
        try:
            positions_summary = self.get_positions_summary()
            if not positions_summary:
                self.logger.warning("Could not generate positions summary")
                return False
                
            # Format the data
            formatted_content = self._format_positions_summary(positions_summary)
            
            # Send using Discord notifier
            self.discord_notifier.send_positions_summary(formatted_content)
            
            self.logger.info("Positions summary sent to Discord")
            return True
            
        except Exception as e:
            self.logger.error(f"Error sending positions summary: {e}")
            return False
    
    def _format_performance_summary(self, performance_data: dict) -> str:
        """Format performance data into Discord summary format."""
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
        
        return content
    
    def send_performance_summary(self):
        """Send performance summary to Discord using PerformanceMonitor data."""
        if not self.discord_notifier:
            self.logger.warning("Discord notifier not available")
            return False
            
        try:
            performance_summary = self.get_performance_summary()
            if not performance_summary:
                self.logger.warning("Could not generate performance summary")
                return False
                
            # Format the data
            formatted_content = self._format_performance_summary(performance_summary)
            
            # Send using Discord notifier
            self.discord_notifier.send_performance_summary(formatted_content)
            
            self.logger.info("Performance summary sent to Discord")
            return True
            
        except Exception as e:
            self.logger.error(f"Error sending performance summary: {e}")
            return False
    
    def _check_system_health(self):
        """Check system health and send alerts if needed."""
        try:
            # Check exchange connectivity
            if self.exchange_client:
                account_info = self.exchange_client.get_account_info()
                if not account_info:
                    self._send_health_alert("Exchange connectivity issue detected")
                    return
            
            # Check risk status using RiskManager
            if self.risk_manager:
                if self.risk_manager.is_at_risk():
                    risk_level = self.risk_manager.get_liquidation_risk_level()
                    if risk_level in ['HIGH', 'CRITICAL']:
                        self._send_health_alert(f"High risk detected: {risk_level} risk level")
                
                # Check account status
                account_status = self.risk_manager.get_account_status()
                if account_status != AccountStatus.NORMAL:
                    self._send_health_alert(f"Account status alert: {account_status.value}")
                    
        except Exception as e:
            self.logger.error(f"System health check error: {e}")
            self._send_health_alert(f"System health check failed: {str(e)}")
            
    def _send_health_alert(self, message: str):
        """Send system health alert."""
        if self.discord_notifier:
            self.discord_notifier.send_message(f"🚨 System Health Alert\n{message}")
            
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
        """Send manual performance report."""
        if not self.discord_notifier:
            return False
            
        try:
            # Get comprehensive performance report
            report = self.performance_monitor.generate_report()
            
            # Split report into chunks if too long
            if len(report) > 2000:
                chunks = [report[i:i+2000] for i in range(0, len(report), 2000)]
                for i, chunk in enumerate(chunks):
                    self.discord_notifier.send_message(f"Performance Report {i+1}\n{chunk}")
            else:
                self.discord_notifier.send_message(report)
                
            return True
            
        except Exception as e:
            self.logger.error(f"Error sending manual report: {e}")
            return False