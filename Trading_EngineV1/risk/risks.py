from typing import Dict, Optional
from enum import Enum
from datetime import datetime


class AccountStatus(Enum):
    """Portfolio margin account status enumeration"""
    NORMAL = "NORMAL"
    MARGIN_CALL = "MARGIN_CALL"
    SUPPLY_MARGIN = "SUPPLY_MARGIN"
    REDUCE_ONLY = "REDUCE_ONLY"
    NEED_ADJUST = "NEED_ADJUST"
    BANKRUPTED = "BANKRUPTED"


class RiskManager:
    """Risk management for portfolio margin accounts"""
    
    def __init__(self, account_info: Dict):
        """
        Initialize RiskManager with account information
        
        Args:
            account_info: Dictionary containing portfolio margin account data
        """
        self.account_info = account_info
        self._parse_account_data()
    
    def _parse_account_data(self):
        """Parse and validate account data"""
        self.uni_mmr = float(self.account_info.get('uniMMR', 0))
        self.account_equity = float(self.account_info.get('accountEquity', 0))
        self.actual_equity = float(self.account_info.get('actualEquity', 0))
        self.initial_margin = float(self.account_info.get('accountInitialMargin', 0))
        self.maint_margin = float(self.account_info.get('accountMaintMargin', 0))
        self.max_withdraw = float(self.account_info.get('virtualMaxWithdrawAmount', 0))
        self.total_available_balance = float(self.account_info.get('totalAvailableBalance', 0))
        self.margin_open_loss = float(self.account_info.get('totalMarginOpenLoss', 0))
        self.update_time = int(self.account_info.get('updateTime', 0))
        
        # Parse account status with validation
        status_str = self.account_info.get('accountStatus', 'NORMAL')
        if status_str in [status.value for status in AccountStatus]:
            self.account_status = AccountStatus(status_str)
        else:
            # Log warning for unknown status and default to NORMAL
            print(f"Warning: Unknown account status '{status_str}', defaulting to NORMAL")
            self.account_status = AccountStatus.NORMAL
    
    # Getters for account data
    def get_uni_mmr(self) -> float:
        """Get portfolio margin account maintenance margin rate"""
        return self.uni_mmr
    
    def get_account_equity(self) -> float:
        """Get account equity in USD"""
        return self.account_equity
    
    def get_actual_equity(self) -> float:
        """Get account equity without collateral rate in USD"""
        return self.actual_equity
    
    def get_initial_margin(self) -> float:
        """Get account initial margin in USD"""
        return self.initial_margin
    
    def get_maintenance_margin(self) -> float:
        """Get account maintenance margin in USD"""
        return self.maint_margin
    
    def get_max_withdraw_amount(self) -> float:
        """Get maximum withdrawal amount in USD"""
        return self.max_withdraw
    
    def get_account_status(self) -> AccountStatus:
        """Get current account status"""
        return self.account_status
    
    def get_last_update_time(self) -> datetime:
        """Get last update time as datetime object"""
        return datetime.fromtimestamp(self.update_time / 1000)
    

    # Risk assessment methods based on Binance Portfolio Margin formulas
    def get_margin_ratio(self) -> float:
        """
        Calculate margin ratio using Binance formula: Equity / MM
        Where MM = ∑維持保證金 = ∑合約MM * 資產指數價格 + ∑MarginMM * 資產指數價格
        Higher ratio = lower risk
        """
        if self.maint_margin == 0:
            return float('inf')
        return self.account_equity / self.maint_margin
    
    def get_utilization_ratio(self) -> float:
        """
        Calculate margin utilization ratio: MM / Equity
        Higher ratio = higher risk
        """
        if self.account_equity == 0:
            return float('inf')
        return self.maint_margin / self.account_equity
    
    def get_uni_mmr_ratio(self) -> float:
        """
        Get the unified maintenance margin rate (uniMMR) as ratio
        This is Binance's key risk metric for portfolio margin accounts
        """
        return self.uni_mmr / 100.0 if self.uni_mmr > 1 else self.uni_mmr
    
    def get_available_margin_ratio(self) -> float:
        """
        Calculate available margin ratio: (Equity - MM) / Equity
        Higher ratio = more available margin for new positions
        """
        if self.account_equity == 0:
            return 0.0
        available_margin = self.account_equity - self.maint_margin
        return available_margin / self.account_equity
    
    def is_at_risk(self, margin_ratio_threshold: float = 1.5) -> bool:
        """
        Check if account is at risk based on Binance Portfolio Margin logic
        
        Args:
            margin_ratio_threshold: Minimum safe margin ratio (default: 1.5)
        
        Returns:
            True if account is at risk
        """
        # Primary check: margin ratio (Equity / MM)
        margin_ratio = self.get_margin_ratio()
        if margin_ratio < margin_ratio_threshold:
            return True
            
        # Secondary check: account status
        if self.account_status != AccountStatus.NORMAL:
            return True
            
        # Tertiary check: uniMMR threshold (if provided by Binance)
        # uniMMR represents the portfolio's overall maintenance margin rate
        uni_mmr_threshold = 0.8  # 80% - adjust based on your risk tolerance
        if self.get_uni_mmr_ratio() > uni_mmr_threshold:
            return True
            
        return False
    
    def get_liquidation_risk_level(self) -> str:
        """
        Assess liquidation risk level based on Binance Portfolio Margin status and ratios
        
        Returns:
            Risk level: 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
        """
        # Critical states
        if self.account_status == AccountStatus.BANKRUPTED:
            return 'CRITICAL'
        
        # High risk states  
        if self.account_status in [AccountStatus.REDUCE_ONLY, AccountStatus.NEED_ADJUST]:
            return 'HIGH'
            
        # Medium risk states
        if self.account_status in [AccountStatus.MARGIN_CALL, AccountStatus.SUPPLY_MARGIN]:
            return 'MEDIUM'
        
        # For NORMAL accounts, check ratios
        margin_ratio = self.get_margin_ratio()
        uni_mmr_ratio = self.get_uni_mmr_ratio()
        
        # Critical: Very low margin ratio
        if margin_ratio < 1.1:
            return 'CRITICAL'
        # High: Low margin ratio or high uniMMR
        elif margin_ratio < 1.3 or uni_mmr_ratio > 0.9:
            return 'HIGH'
        # Medium: Moderate risk
        elif margin_ratio < 1.5 or uni_mmr_ratio > 0.7:
            return 'MEDIUM'
        # Low: Safe levels
        else:
            return 'LOW'
    
    
    def can_open_position(self, required_margin: float) -> bool:
        """
        Check if account can open a new position requiring specific margin
        
        Args:
            required_margin: Required margin for new position in USD
        
        Returns:
            True if position can be opened safely
        """
        if self.account_status != AccountStatus.NORMAL:
            return False
        
        # Check if we have enough available balance
        if required_margin > self.total_available_balance:
            return False
        
        # Check if new position would keep us above safe margin ratio
        new_total_margin = self.maint_margin + required_margin
        new_margin_ratio = self.account_equity / new_total_margin if new_total_margin > 0 else float('inf')
        
        return new_margin_ratio >= 1.5  # Keep safe margin ratio
    
    def get_max_position_size(self, margin_per_unit: float, safety_ratio: float = 1.5) -> float:
        """
        Calculate maximum position size that can be opened safely
        
        Args:
            margin_per_unit: Margin required per unit of position
            safety_ratio: Minimum margin ratio to maintain (default: 1.5)
        
        Returns:
            Maximum position size in units
        """
        if (self.account_status != AccountStatus.NORMAL or 
            margin_per_unit <= 0 or 
            self.account_equity <= 0):
            return 0
        
        # Calculate max margin we can use while maintaining safety ratio
        max_total_margin = self.account_equity / safety_ratio
        available_margin = max_total_margin - self.maint_margin
        
        if available_margin <= 0:
            return 0
        
        return min(available_margin / margin_per_unit, 
                  self.total_available_balance / margin_per_unit)
    
    def get_risk_summary(self) -> Dict:
        """
        Get comprehensive risk summary
        
        Returns:
            Dictionary with risk metrics and status
        """
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
            'last_update': self.get_last_update_time().isoformat()
        }
    
    def process_balance_data(self, balance_data: list) -> Dict:
        """
        Process balance data from Binance API
        
        Args:
            balance_data: List of balance dictionaries from get_balances()
            
        Returns:
            Dictionary with processed balance information
        """
        processed_balances = {}
        total_usd_value = 0.0
        
        for asset in balance_data:
            asset_name = asset.get('asset', '')
            
            # Calculate total wallet balance (cross margin + futures)
            total_wallet = float(asset.get('totalWalletBalance', 0))
            cross_wallet = float(asset.get('crossMarginAsset', 0))
            um_wallet = float(asset.get('umWalletBalance', 0))
            cm_wallet = float(asset.get('cmWalletBalance', 0))
            
            # Calculate unrealized P&L
            um_unrealized = float(asset.get('umUnrealizedPNL', 0))
            cm_unrealized = float(asset.get('cmUnrealizedPNL', 0))
            total_unrealized = um_unrealized + cm_unrealized
            
            processed_balances[asset_name] = {
                'total_wallet_balance': total_wallet,
                'cross_margin_balance': cross_wallet,
                'futures_balance': um_wallet + cm_wallet,
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
    
    def process_positions_data(self, positions_data: list) -> Dict:
        """
        Process positions data from Binance API
        
        Args:
            positions_data: List of position dictionaries from get_positions()
            
        Returns:
            Dictionary with processed position information
        """
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
            
            # Skip zero positions
            if position_amt == 0:
                continue
            
            entry_price = float(position.get('entryPrice', 0))
            mark_price = float(position.get('markPrice', 0))
            unrealized_pnl = float(position.get('unrealizedProfit', 0))
            notional = float(position.get('notional', 0))
            
            processed_positions[symbol] = {
                'side': 'LONG' if position_amt > 0 else 'SHORT',
                'quantity': abs(position_amt),
                'entry_price': entry_price,
                'mark_price': mark_price,
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
    
    def get_accounts_summary(self, balance_data: list, positions_data: list) -> Dict:
        """
        Generate accounts summary for Discord notifications
        
        Args:
            balance_data: List of balance dictionaries from get_balances()
            positions_data: List of position dictionaries from get_positions()
            
        Returns:
            Dictionary formatted for Discord accounts summary
        """
        balance_info = self.process_balance_data(balance_data)
        position_info = self.process_positions_data(positions_data)
        
        # Calculate leverage (position value / account equity)
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
    
    def get_positions_summary(self, positions_data: list) -> Dict:
        """
        Generate positions summary for Discord notifications
        
        Args:
            positions_data: List of position dictionaries from get_positions()
            
        Returns:
            Dictionary formatted for Discord positions summary
        """
        position_info = self.process_positions_data(positions_data)
        
        return {
            'total_positions': position_info['total_positions'],
            'total_unrealized_pnl': position_info['total_unrealized_pnl'],
            'total_position_value': position_info['total_position_value'],
            'positions': position_info['positions']
        }