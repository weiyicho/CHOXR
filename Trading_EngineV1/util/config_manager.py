#!/usr/bin/env python3
"""
Simplified configuration management for the Trading Engine.

This module provides a clean, simple interface for loading configuration files
with automatic path resolution and caching.
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging

from .utils import load_config


class ConfigManager:
    """
    Simplified configuration manager for the Trading Engine.
    
    Features:
    - Automatic project root detection
    - Configuration caching for performance
    - Path resolution from any module location
    - Simple, clean API
    """
    
    def __init__(self, project_root: Optional[Path] = None):
        """Initialize the configuration manager."""
        self.logger = logging.getLogger(__name__)
        self.project_root = project_root or self._find_project_root()
        self.config_dir = self.project_root / "config"
        self._cache = {}
        
        self.logger.info(f"ConfigManager initialized - Project root: {self.project_root}")
    
    def _find_project_root(self) -> Path:
        """Automatically detect the project root directory."""
        current_dir = Path(__file__).resolve().parent
        
        # Walk up the directory tree looking for project markers
        while current_dir != current_dir.parent:
            if (current_dir / "config").exists() and (current_dir / "src").exists():
                return current_dir
            elif (current_dir / ".git").exists() and (current_dir / "Trading_EngineV1").exists():
                return current_dir / "Trading_EngineV1"
            current_dir = current_dir.parent
        
        # Fallback: assume we're in the project root
        return Path(__file__).resolve().parent.parent
    
    def _load_config(self, config_path: Path, cache_key: str) -> Dict[str, Any]:
        """Load and cache configuration from file."""
        if cache_key not in self._cache:
            try:
                if config_path.exists():
                    self._cache[cache_key] = load_config(config_path)
                    self.logger.debug(f"Loaded config: {config_path}")
                else:
                    self.logger.warning(f"Config file not found: {config_path}")
                    self._cache[cache_key] = {}
            except Exception as e:
                self.logger.error(f"Failed to load config {config_path}: {e}")
                self._cache[cache_key] = {}
        
        return self._cache[cache_key]
    
    def get_api_config(self, exchange: str = "binance") -> Dict[str, Any]:
        """Get API configuration for a specific exchange."""
        config = self._load_config(self.config_dir / "api.json", "api")
        return config.get(exchange, {})
    
    def get_strategy_config(self, strategy_name: str = "strategy1") -> Dict[str, Any]:
        """Get strategy-specific configuration."""
        if strategy_name == "strategy1":
            config_path = self.config_dir / "strategy1" / "strategy1.json"
        else:
            config_path = self.config_dir / strategy_name / f"{strategy_name}.json"
        
        return self._load_config(config_path, f"strategy_{strategy_name}")
    
    def get_monitoring_config(self) -> Dict[str, Any]:
        """Get monitoring system configuration."""
        return self._load_config(self.config_dir / "monitoring.json", "monitoring")
    
    def get_discord_config(self) -> Dict[str, Any]:
        """Get Discord notification configuration."""
        # Try strategy config first (unified approach)
        strategy_config = self.get_strategy_config()
        if "discord" in strategy_config:
            return strategy_config["discord"]
        
        # Fallback to monitoring config
        monitoring_config = self.get_monitoring_config()
        return monitoring_config.get("discord", {})
    
    def clear_cache(self):
        """Clear the configuration cache."""
        self._cache.clear()
        self.logger.info("Configuration cache cleared")


# Global instance for easy access
_config_manager = None

def get_config_manager() -> ConfigManager:
    """Get the global configuration manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


# Convenience functions for common operations
def get_api_config(exchange: str = "binance") -> Dict[str, Any]:
    """Get API configuration for an exchange."""
    return get_config_manager().get_api_config(exchange)

def get_strategy_config(strategy_name: str = "strategy1") -> Dict[str, Any]:
    """Get strategy configuration."""
    return get_config_manager().get_strategy_config(strategy_name)

def get_monitoring_config() -> Dict[str, Any]:
    """Get monitoring configuration."""
    return get_config_manager().get_monitoring_config()

def get_discord_config() -> Dict[str, Any]:
    """Get Discord configuration."""
    return get_config_manager().get_discord_config()
