"""
Simple performance monitoring for trade tracking.
"""
import json
from datetime import datetime
from typing import Dict, List
from dataclasses import dataclass

from util.utils import setup_logging


@dataclass
class TradeRecord:
    """Simple trade record."""
    symbol: str
    side: str
    quantity: float
    entry_price: float
    exit_price: float
    pnl: float
    entry_time: datetime
    exit_time: datetime
    fees: float = 0.0


class PerformanceMonitor:
    """Simple performance monitoring."""
    
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
                        entry_time=datetime.fromisoformat(trade['entry_time']),
                        exit_time=datetime.fromisoformat(trade['exit_time']),
                        fees=trade.get('fees', 0.0)
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
                        'entry_time': trade.entry_time.isoformat(),
                        'exit_time': trade.exit_time.isoformat(),
                        'fees': trade.fees
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
        pnl = (exit_price - entry_price) * quantity if side == 'BUY' else (entry_price - exit_price) * quantity
        
        trade = TradeRecord(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            entry_time=entry_time,
            exit_time=exit_time,
            fees=fees
        )
        
        self.trades.append(trade)
        self._save_data()
        
        self.logger.info(f"Recorded trade: {symbol} {side} P&L: ${pnl:.2f}")
        
    def get_simple_metrics(self) -> Dict:
        """Get simple performance metrics."""
        if not self.trades:
            return {
                'total_trades': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'net_pnl': 0.0,
                'best_trade': 0.0,
                'worst_trade': 0.0
            }
        
        total_trades = len(self.trades)
        winning_trades = len([t for t in self.trades if t.pnl > 0])
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
        
        total_pnl = sum(t.pnl for t in self.trades)
        total_fees = sum(t.fees for t in self.trades)
        net_pnl = total_pnl - total_fees
        
        best_trade = max(t.pnl for t in self.trades) if self.trades else 0
        worst_trade = min(t.pnl for t in self.trades) if self.trades else 0
        
        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'net_pnl': net_pnl,
            'best_trade': best_trade,
            'worst_trade': worst_trade
        }
        
    def generate_simple_report(self) -> str:
        """Generate simple performance report."""
        metrics = self.get_simple_metrics()
        
        report = f"""📊 Trading Performance Report
{'=' * 40}

Total Trades: {metrics['total_trades']}
Win Rate: {metrics['win_rate']:.1f}%
Total P&L: ${metrics['total_pnl']:.2f}
Net P&L: ${metrics['net_pnl']:.2f}
Best Trade: ${metrics['best_trade']:.2f}
Worst Trade: ${metrics['worst_trade']:.2f}"""
        
        return report