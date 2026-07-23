
from typing import Dict, List
from enum import Enum
from datetime import datetime


class AccountStatus(Enum):
    """Portfolio margin account status enumeration"""
    NORMAL = "NORMAL"
    MARGIN_CALL = "MARGIN_CALL"
    SUPPLY_MARGIN = "SUPPLY_MARGIN"
    REDUCE_ONLY = "REDUCE_ONLY"
    ACTIVE_LIQUIDATION = "ACTIVE_LIQUIDATION"
    FORCE_LIQUIDATION = "FORCE_LIQUIDATION"
    BANKRUPTED = "BANKRUPTED"


class RiskManager:
    """Risk management for portfolio margin accounts"""
    
    def __init__(self, account_info: Dict):
        """Initialize RiskManager with account information"""
        # Parse and store account data
        self.uni_mmr = float(account_info.get('uniMMR', 0))
        self.account_equity = float(account_info.get('accountEquity', 0))
        self.actual_equity = float(account_info.get('actualEquity', 0))
        self.initial_margin = float(account_info.get('accountInitialMargin', 0))
        self.maint_margin = float(account_info.get('accountMaintMargin', 0))
        self.max_withdraw = float(account_info.get('virtualMaxWithdrawAmount', 0))
        self.total_available_balance = float(account_info.get('totalAvailableBalance', 0))
        self.margin_open_loss = float(account_info.get('totalMarginOpenLoss', 0))
        self.update_time = int(account_info.get('updateTime', 0))
        
        # Parse account status with validation
        status_str = account_info.get('accountStatus', 'NORMAL')
        try:
            self.account_status = AccountStatus(status_str)
        except ValueError:
            print(f"Warning: Unknown account status '{status_str}', defaulting to NORMAL")
            self.account_status = AccountStatus.NORMAL
    
    # Core risk metrics
    def get_mmr(self) -> float:
        """Calculate margin ratio: Equity / MM (higher = lower risk)"""
        return self.uni_mmr
    
        
    
    def get_liquidation_risk_level(self) -> str:
        # Check ratios for NORMAL accounts
        margin_ratio = self.get_mmr()
        uni_mmr_ratio = self.uni_mmr / 100.0 if self.uni_mmr > 1 else self.uni_mmr
        
        if margin_ratio > 3:
            return 'NORMAL'
        elif margin_ratio < 3 and uni_mmr_ratio > 2:
            return 'NEED_ADJUST'
        elif margin_ratio < 1.5 and uni_mmr_ratio > 1:
            return 'Close all positions'
        return 
    
    def can_open_position(self, required_margin: float, safety_ratio: float = 1.5) -> bool:
        """Check if account can safely open a new position"""
        if self.account_status != AccountStatus.NORMAL or required_margin > self.total_available_balance:
            return False
        
        new_total_margin = self.maint_margin + required_margin
        new_margin_ratio = self.account_equity / new_total_margin if new_total_margin > 0 else float('inf')
        return new_margin_ratio >= safety_ratio
    
    def get_max_position_size(self, margin_per_unit: float, safety_ratio: float = 1.5) -> float:
        """Calculate maximum position size that can be opened safely"""
        if (self.account_status != AccountStatus.NORMAL or 
            margin_per_unit <= 0 or self.account_equity <= 0):
            return 0.0
        
        max_total_margin = self.account_equity / safety_ratio
        available_margin = max(0, max_total_margin - self.maint_margin)
        
        return min(available_margin / margin_per_unit, 
                  self.total_available_balance / margin_per_unit)
    
    def get_risk_summary(self) -> Dict:
        """Get comprehensive risk summary"""
        return {
            'account_status': self.account_status.value,
            'liquidation_risk': self.get_liquidation_risk_level(),
            'margin_ratio': round(self.get_margin_ratio(), 4),
            'utilization_ratio': round(self.get_utilization_ratio(), 4),
            'available_margin_ratio': round(self.get_available_margin_ratio(), 4),
            'is_at_risk': self.is_at_risk(),
            'account_equity_usd': self.account_equity,
            'maintenance_margin_usd': self.maint_margin,
            'max_withdraw_usd': self.max_withdraw,
            'last_update': datetime.fromtimestamp(self.update_time / 1000).isoformat()
        }
    
    def process_balance_data(self, balance_data: List[Dict]) -> Dict:
        """Process balance data from Binance API"""
        processed_balances = {}
        total_usd_value = 0.0
        
        for asset in balance_data:
            asset_name = asset.get('asset', '')
            total_wallet = float(asset.get('totalWalletBalance', 0))
            um_unrealized = float(asset.get('umUnrealizedPNL', 0))
            cm_unrealized = float(asset.get('cmUnrealizedPNL', 0))
            total_unrealized = um_unrealized + cm_unrealized
            
            processed_balances[asset_name] = {
                'total_wallet_balance': total_wallet,
                'cross_margin_balance': float(asset.get('crossMarginAsset', 0)),
                'futures_balance': float(asset.get('umWalletBalance', 0)) + float(asset.get('cmWalletBalance', 0)),
                'unrealized_pnl': total_unrealized,
                'available_balance': float(asset.get('crossMarginFree', 0)),
                'locked_balance': float(asset.get('crossMarginLocked', 0))
            }
            
            # For USDT, assume 1:1 with USD
            if asset_name == 'USDT':
                total_usd_value += total_wallet + total_unrealized
        
        return {
            'balances': processed_balances,
            'total_usd_value': total_usd_value,
            'num_assets': len(processed_balances)
        }
    
    def process_positions_data(self, positions_data: List[Dict]) -> Dict:
        """Process positions data from Binance API"""
        if not positions_data:
            return {
                'total_positions': 0,
                'total_unrealized_pnl': 0.0,
                'total_position_value': 0.0,
                'positions': {}
            }
        
        processed_positions = {}
        total_unrealized_pnl = 0.0
        total_position_value = 0.0
        
        for position in positions_data:
            symbol = position.get('symbol', '')
            position_amt = float(position.get('positionAmt', 0))
            
            if position_amt == 0:  # Skip zero positions
                continue
            
            entry_price = float(position.get('entryPrice', 0))
            unrealized_pnl = float(position.get('unrealizedProfit', 0))
            notional = float(position.get('notional', 0))
            
            processed_positions[symbol] = {
                'side': 'LONG' if position_amt > 0 else 'SHORT',
                'quantity': abs(position_amt),
                'entry_price': entry_price,
                'mark_price': float(position.get('markPrice', 0)),
                'unrealized_pnl': unrealized_pnl,
                'position_value': notional,
                'pnl_percentage': (unrealized_pnl / (abs(position_amt) * entry_price) * 100) if entry_price > 0 else 0.0
            }
            
            total_unrealized_pnl += unrealized_pnl
            total_position_value += notional
        
        return {
            'total_positions': len(processed_positions),
            'total_unrealized_pnl': total_unrealized_pnl,
            'total_position_value': total_position_value,
            'positions': processed_positions
        }
    
    def get_accounts_summary(self, balance_data: List[Dict], positions_data: List[Dict]) -> Dict:
        """Generate accounts summary for Discord notifications"""
        balance_info = self.process_balance_data(balance_data)
        position_info = self.process_positions_data(positions_data)
        leverage = position_info['total_position_value'] / self.account_equity if self.account_equity > 0 else 0.0
        
        return {
            'exchange': 'binance',
            'account_value': self.account_equity,
            'position_value': position_info['total_position_value'],
            'leverage': round(leverage, 2),
            'available_balance': self.total_available_balance,
            'unrealized_pnl': position_info['total_unrealized_pnl'],
            'margin_ratio': self.get_margin_ratio(),
            'risk_level': self.get_liquidation_risk_level()
        }
    
    def get_positions_summary(self, positions_data: List[Dict]) -> Dict:
        """Generate positions summary for Discord notifications"""
        position_info = self.process_positions_data(positions_data)
        return {
            'total_positions': position_info['total_positions'],
            'total_unrealized_pnl': position_info['total_unrealized_pnl'],
            'total_position_value': position_info['total_position_value'],
            'positions': position_info['positions']
        }