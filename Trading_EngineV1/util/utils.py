"""
Shared utility functions for the Trading Engine.
Provides logging, math operations, time utilities, and JSON/YAML parsing.
"""

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union
import yaml


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> logging.Logger:
    """
    Set up logging configuration for the trading engine.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("trading_engine")
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper()))
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def load_config(config_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Load configuration from JSON or YAML file.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Configuration dictionary
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config file format is invalid
    """
    config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        if config_path.suffix.lower() in ['.yaml', '.yml']:
            return yaml.safe_load(f)
        elif config_path.suffix.lower() == '.json':
            return json.load(f)
        else:
            raise ValueError(f"Unsupported config file format: {config_path.suffix}")


def save_config(config: Dict[str, Any], config_path: Union[str, Path]) -> None:
    """
    Save configuration to JSON or YAML file.
    
    Args:
        config: Configuration dictionary
        config_path: Path to save configuration file
    """
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(config_path, 'w') as f:
        if config_path.suffix.lower() in ['.yaml', '.yml']:
            yaml.dump(config, f, default_flow_style=False, indent=2)
        elif config_path.suffix.lower() == '.json':
            json.dump(config, f, indent=2)
        else:
            raise ValueError(f"Unsupported config file format: {config_path.suffix}")


def get_utc_timestamp() -> float:
    """
    Get current UTC timestamp.
    
    Returns:
        Current UTC timestamp as float
    """
    return datetime.now(timezone.utc).timestamp()


def get_utc_datetime() -> datetime:
    """
    Get current UTC datetime.
    
    Returns:
        Current UTC datetime
    """
    return datetime.now(timezone.utc)


def format_timestamp(timestamp: Union[float, datetime], format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Format timestamp to string.
    
    Args:
        timestamp: Timestamp (float or datetime)
        format_str: Format string
        
    Returns:
        Formatted timestamp string
    """
    if isinstance(timestamp, datetime):
        return timestamp.strftime(format_str)
    else:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime(format_str)


def calculate_percentage_change(old_value: float, new_value: float) -> float:
    """
    Calculate percentage change between two values.
    
    Args:
        old_value: Original value
        new_value: New value
        
    Returns:
        Percentage change (positive for increase, negative for decrease)
    """
    if old_value == 0:
        return 0.0 if new_value == 0 else float('inf')
    return ((new_value - old_value) / old_value) * 100


def calculate_position_size(
    account_balance: float, 
    risk_percentage: float, 
    entry_price: float, 
    stop_loss_price: float
) -> float:
    """
    Calculate position size based on risk management parameters.
    
    Args:
        account_balance: Total account balance
        risk_percentage: Risk percentage (e.g., 2.0 for 2%)
        entry_price: Entry price
        stop_loss_price: Stop loss price
        
    Returns:
        Position size in base currency
    """
    risk_amount = account_balance * (risk_percentage / 100)
    price_difference = abs(entry_price - stop_loss_price)
    
    if price_difference == 0:
        return 0.0
    
    return risk_amount / price_difference


def round_to_precision(value: float, precision: int) -> float:
    """
    Round value to specified decimal precision.
    
    Args:
        value: Value to round
        precision: Number of decimal places
        
    Returns:
        Rounded value
    """
    return round(value, precision)


def validate_price(price: float) -> bool:
    """
    Validate if price is reasonable for trading.
    
    Args:
        price: Price to validate
        
    Returns:
        True if price is valid, False otherwise
    """
    return price > 0 and not math.isnan(price) and not math.isinf(price)


def validate_quantity(quantity: float) -> bool:
    """
    Validate if quantity is reasonable for trading.
    
    Args:
        quantity: Quantity to validate
        
    Returns:
        True if quantity is valid, False otherwise
    """
    return quantity > 0 and not math.isnan(quantity) and not math.isinf(quantity)


def calculate_pnl(
    entry_price: float, 
    current_price: float, 
    quantity: float, 
    side: str
) -> float:
    """
    Calculate profit and loss for a position.
    
    Args:
        entry_price: Entry price
        current_price: Current market price
        quantity: Position quantity
        side: Position side ('long' or 'short')
        
    Returns:
        PnL amount (positive for profit, negative for loss)
    """
    if side.lower() == 'long':
        return (current_price - entry_price) * quantity
    elif side.lower() == 'short':
        return (entry_price - current_price) * quantity
    else:
        raise ValueError("Side must be 'long' or 'short'")


def ensure_directory_exists(directory_path: Union[str, Path]) -> Path:
    """
    Ensure directory exists, create if it doesn't.
    
    Args:
        directory_path: Path to directory
        
    Returns:
        Path object of the directory
    """
    directory_path = Path(directory_path)
    directory_path.mkdir(parents=True, exist_ok=True)
    return directory_path


# Default logger instance
logger = setup_logging()
