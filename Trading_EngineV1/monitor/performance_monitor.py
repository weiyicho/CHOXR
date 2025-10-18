"""
Performance monitoring and analytics system for trade tracking and reporting.
"""
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict

from util.utils import setup_logging


@dataclass
class TradeRecord:
    """Individual trade record."""
    symbol: str
    side: str
    quantity: float
    entry_price: float
    exit_price: float
    pnl: float
    pnl_percentage: float
    entry_time: datetime
    exit_time: datetime
    duration_minutes: float
    fees: float
    strategy: str = ""


@dataclass
class PerformanceMetrics:
    """Performance metrics summary."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    total_fees: float
    net_pnl: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_drawdown: float
    sharpe_ratio: float
    avg_trade_duration: float
    best_trade: float
    worst_trade: float
    period_start: datetime
    period_end: datetime


class PerformanceMonitor:
    """Performance monitoring and analytics system."""
    
    def __init__(self, data_file: str = "monitor/performance_data.json"):
        """Initialize performance monitor."""
        self.data_file = data_file
        self.trades: List[TradeRecord] = []
        self.logger = setup_logging("INFO")
        
        self._load_data()
        
    def _load_data(self):
        """Load performance data from file."""
        try:
            with open(self.data_file, 'r') as f:
                data = json.load(f)
                self.trades = [
                    TradeRecord(
                        symbol=trade['symbol'],
                        side=trade['side'],
                        quantity=trade['quantity'],
                        entry_price=trade['entry_price'],
                        exit_price=trade['exit_price'],
                        pnl=trade['pnl'],
                        pnl_percentage=trade['pnl_percentage'],
                        entry_time=datetime.fromisoformat(trade['entry_time']),
                        exit_time=datetime.fromisoformat(trade['exit_time']),
                        duration_minutes=trade['duration_minutes'],
                        fees=trade['fees'],
                        strategy=trade.get('strategy', '')
                    )
                    for trade in data.get('trades', [])
                ]
        except FileNotFoundError:
            self.logger.info("No existing performance data found, starting fresh")
        except Exception as e:
            self.logger.error(f"Error loading performance data: {e}")
            
    def _save_data(self):
        """Save performance data to file."""
        try:
            data = {
                'trades': [
                    {
                        'symbol': trade.symbol,
                        'side': trade.side,
                        'quantity': trade.quantity,
                        'entry_price': trade.entry_price,
                        'exit_price': trade.exit_price,
                        'pnl': trade.pnl,
                        'pnl_percentage': trade.pnl_percentage,
                        'entry_time': trade.entry_time.isoformat(),
                        'exit_time': trade.exit_time.isoformat(),
                        'duration_minutes': trade.duration_minutes,
                        'fees': trade.fees,
                        'strategy': trade.strategy
                    }
                    for trade in self.trades
                ],
                'last_updated': datetime.now().isoformat()
            }
            
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Error saving performance data: {e}")
            
    def record_trade(self, symbol: str, side: str, quantity: float, entry_price: float, 
                     exit_price: float, entry_time: datetime, exit_time: datetime, 
                     fees: float = 0.0, strategy: str = ""):
        """Record a completed trade."""
        duration_minutes = (exit_time - entry_time).total_seconds() / 60
        pnl = (exit_price - entry_price) * quantity if side == 'BUY' else (entry_price - exit_price) * quantity
        pnl_percentage = (pnl / (entry_price * quantity)) * 100 if entry_price > 0 else 0
        
        trade = TradeRecord(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            pnl_percentage=pnl_percentage,
            entry_time=entry_time,
            exit_time=exit_time,
            duration_minutes=duration_minutes,
            fees=fees,
            strategy=strategy
        )
        
        self.trades.append(trade)
        self._save_data()
        
        self.logger.info(f"Recorded trade: {symbol} {side} P&L: ${pnl:.2f} ({pnl_percentage:.2f}%)")
        
    def get_performance_metrics(self, start_date: Optional[datetime] = None, 
                               end_date: Optional[datetime] = None, 
                               strategy: Optional[str] = None) -> PerformanceMetrics:
        """Calculate performance metrics for a period."""
        # Filter trades
        filtered_trades = self.trades
        
        if start_date:
            filtered_trades = [t for t in filtered_trades if t.entry_time >= start_date]
        if end_date:
            filtered_trades = [t for t in filtered_trades if t.entry_time <= end_date]
        if strategy:
            filtered_trades = [t for t in filtered_trades if t.strategy == strategy]
            
        if not filtered_trades:
            return PerformanceMetrics(
                total_trades=0, winning_trades=0, losing_trades=0, win_rate=0.0,
                total_pnl=0.0, total_fees=0.0, net_pnl=0.0, avg_win=0.0, avg_loss=0.0,
                profit_factor=0.0, max_drawdown=0.0, sharpe_ratio=0.0, avg_trade_duration=0.0,
                best_trade=0.0, worst_trade=0.0, period_start=start_date or datetime.min,
                period_end=end_date or datetime.max
            )
            
        # Calculate basic metrics
        total_trades = len(filtered_trades)
        winning_trades = len([t for t in filtered_trades if t.pnl > 0])
        losing_trades = len([t for t in filtered_trades if t.pnl < 0])
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
        
        total_pnl = sum(t.pnl for t in filtered_trades)
        total_fees = sum(t.fees for t in filtered_trades)
        net_pnl = total_pnl - total_fees
        
        # Calculate win/loss averages
        wins = [t.pnl for t in filtered_trades if t.pnl > 0]
        losses = [t.pnl for t in filtered_trades if t.pnl < 0]
        
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        
        # Profit factor
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Drawdown and Sharpe ratio
        max_drawdown = self._calculate_max_drawdown(filtered_trades)
        sharpe_ratio = self._calculate_sharpe_ratio(filtered_trades)
        
        # Duration metrics
        avg_trade_duration = sum(t.duration_minutes for t in filtered_trades) / total_trades
        
        # Best/worst trades
        best_trade = max(t.pnl for t in filtered_trades) if filtered_trades else 0
        worst_trade = min(t.pnl for t in filtered_trades) if filtered_trades else 0
        
        return PerformanceMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_pnl=total_pnl,
            total_fees=total_fees,
            net_pnl=net_pnl,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            avg_trade_duration=avg_trade_duration,
            best_trade=best_trade,
            worst_trade=worst_trade,
            period_start=min(t.entry_time for t in filtered_trades),
            period_end=max(t.exit_time for t in filtered_trades)
        )
        
    def _calculate_max_drawdown(self, trades: List[TradeRecord]) -> float:
        """Calculate maximum drawdown."""
        if not trades:
            return 0.0
            
        sorted_trades = sorted(trades, key=lambda t: t.entry_time)
        
        peak = 0
        max_dd = 0
        running_pnl = 0
        
        for trade in sorted_trades:
            running_pnl += trade.pnl
            if running_pnl > peak:
                peak = running_pnl
            drawdown = peak - running_pnl
            if drawdown > max_dd:
                max_dd = drawdown
                
        return max_dd
        
    def _calculate_sharpe_ratio(self, trades: List[TradeRecord]) -> float:
        """Calculate simplified Sharpe ratio."""
        if len(trades) < 2:
            return 0.0
            
        pnls = [t.pnl for t in trades]
        mean_pnl = sum(pnls) / len(pnls)
        
        variance = sum((pnl - mean_pnl) ** 2 for pnl in pnls) / len(pnls)
        std_dev = variance ** 0.5
        
        if std_dev == 0:
            return 0.0
            
        return mean_pnl / std_dev
        
    def get_strategy_performance(self) -> Dict[str, PerformanceMetrics]:
        """Get performance metrics by strategy."""
        strategies = set(t.strategy for t in self.trades if t.strategy)
        performance = {}
        
        for strategy in strategies:
            performance[strategy] = self.get_performance_metrics(strategy=strategy)
            
        return performance
        
    def generate_report(self, start_date: Optional[datetime] = None, 
                       end_date: Optional[datetime] = None) -> str:
        """Generate performance report."""
        metrics = self.get_performance_metrics(start_date, end_date)
        
        report = f"""
📊 **Trading Performance Report**
{'=' * 50}

**Period:** {metrics.period_start.strftime('%Y-%m-%d')} to {metrics.period_end.strftime('%Y-%m-%d')}

**Trade Statistics:**
• Total Trades: {metrics.total_trades}
• Winning Trades: {metrics.winning_trades}
• Losing Trades: {metrics.losing_trades}
• Win Rate: {metrics.win_rate:.1f}%

**Financial Performance:**
• Total P&L: ${metrics.total_pnl:.2f}
• Total Fees: ${metrics.total_fees:.2f}
• Net P&L: ${metrics.net_pnl:.2f}
• Average Win: ${metrics.avg_win:.2f}
• Average Loss: ${metrics.avg_loss:.2f}
• Profit Factor: {metrics.profit_factor:.2f}

**Risk Metrics:**
• Max Drawdown: ${metrics.max_drawdown:.2f}
• Sharpe Ratio: {metrics.sharpe_ratio:.2f}
• Avg Trade Duration: {metrics.avg_trade_duration:.1f} minutes

**Best/Worst Trades:**
• Best Trade: ${metrics.best_trade:.2f}
• Worst Trade: ${metrics.worst_trade:.2f}
        """
        
        return report.strip()
        
    def export_trades(self, filename: str = None) -> str:
        """Export trades to CSV file."""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"monitor/trades_export_{timestamp}.csv"
            
        try:
            import csv
            
            with open(filename, 'w', newline='') as csvfile:
                fieldnames = [
                    'symbol', 'side', 'quantity', 'entry_price', 'exit_price',
                    'pnl', 'pnl_percentage', 'entry_time', 'exit_time',
                    'duration_minutes', 'fees', 'strategy'
                ]
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for trade in self.trades:
                    writer.writerow({
                        'symbol': trade.symbol,
                        'side': trade.side,
                        'quantity': trade.quantity,
                        'entry_price': trade.entry_price,
                        'exit_price': trade.exit_price,
                        'pnl': trade.pnl,
                        'pnl_percentage': trade.pnl_percentage,
                        'entry_time': trade.entry_time.isoformat(),
                        'exit_time': trade.exit_time.isoformat(),
                        'duration_minutes': trade.duration_minutes,
                        'fees': trade.fees,
                        'strategy': trade.strategy
                    })
                    
            self.logger.info(f"Trades exported to {filename}")
            return filename
            
        except Exception as e:
            self.logger.error(f"Error exporting trades: {e}")
            return ""