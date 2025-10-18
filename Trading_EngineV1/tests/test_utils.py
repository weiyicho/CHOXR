"""
Unit tests for utility functions.
"""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime, timezone

from util.utils import (
    setup_logging,
    load_config,
    save_config,
    get_utc_timestamp,
    get_utc_datetime,
    format_timestamp,
    calculate_percentage_change,
    calculate_position_size,
    validate_price,
    validate_quantity,
    calculate_pnl,
    ensure_directory_exists
)


class TestUtils:
    """Test utility functions."""
    
    def test_setup_logging(self):
        """Test logging setup."""
        logger = setup_logging("DEBUG")
        assert logger.level == 10  # DEBUG level
        assert logger.name == "trading_engine"
    
    def test_load_config_json(self):
        """Test loading JSON configuration."""
        test_config = {"api_key": "test", "timeout": 30}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_config, f)
            temp_path = f.name
        
        try:
            loaded_config = load_config(temp_path)
            assert loaded_config == test_config
        finally:
            Path(temp_path).unlink()
    
    def test_save_config_json(self):
        """Test saving JSON configuration."""
        test_config = {"api_key": "test", "timeout": 30}
        
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            save_config(test_config, temp_path)
            with open(temp_path, 'r') as f:
                loaded_config = json.load(f)
            assert loaded_config == test_config
        finally:
            Path(temp_path).unlink()
    
    def test_get_utc_timestamp(self):
        """Test UTC timestamp generation."""
        timestamp = get_utc_timestamp()
        assert isinstance(timestamp, float)
        assert timestamp > 0
    
    def test_get_utc_datetime(self):
        """Test UTC datetime generation."""
        dt = get_utc_datetime()
        assert isinstance(dt, datetime)
        assert dt.tzinfo == timezone.utc
    
    def test_format_timestamp(self):
        """Test timestamp formatting."""
        dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        formatted = format_timestamp(dt)
        assert formatted == "2023-01-01 12:00:00"
    
    def test_calculate_percentage_change(self):
        """Test percentage change calculation."""
        assert calculate_percentage_change(100, 110) == 10.0
        assert calculate_percentage_change(100, 90) == -10.0
        assert calculate_percentage_change(0, 100) == float('inf')
    
    def test_calculate_position_size(self):
        """Test position size calculation."""
        size = calculate_position_size(10000, 2.0, 100, 98)
        assert size == 1000.0  # 2% risk on 10k account, $2 stop loss
    
    def test_validate_price(self):
        """Test price validation."""
        assert validate_price(100.0) == True
        assert validate_price(0) == False
        assert validate_price(-10) == False
    
    def test_validate_quantity(self):
        """Test quantity validation."""
        assert validate_quantity(1.0) == True
        assert validate_quantity(0) == False
        assert validate_quantity(-1) == False
    
    def test_calculate_pnl_long(self):
        """Test PnL calculation for long position."""
        pnl = calculate_pnl(100, 110, 10, 'long')
        assert pnl == 100.0  # (110-100) * 10
    
    def test_calculate_pnl_short(self):
        """Test PnL calculation for short position."""
        pnl = calculate_pnl(100, 90, 10, 'short')
        assert pnl == 100.0  # (100-90) * 10
    
    def test_ensure_directory_exists(self):
        """Test directory creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            new_dir = Path(temp_dir) / "new_subdir"
            result_path = ensure_directory_exists(new_dir)
            assert result_path.exists()
            assert result_path.is_dir()
