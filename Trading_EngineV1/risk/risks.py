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