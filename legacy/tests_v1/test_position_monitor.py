#!/usr/bin/env python3
"""
Test script for Position Monitor functionality.
Tests position tracking, risk assessment, and alert generation.
"""

import sys
import os
import json
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

# Add the parent directory to the path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from monitor.position_monitor import PositionMonitor, AlertLevel, PositionAlert, PositionMetrics
from src.binance_sdk import BinanceFuturesClient
from util.utils import load_config, setup_logging


class PositionMonitorTester:
    """Test class for Position Monitor functionality."""
    
    def __init__(self):
        """Initialize the tester."""
        self.logger = setup_logging("INFO")
        
        # Load API configuration
        try:
            api_config = load_config("../config/api.json")
            self.api_key = api_config.get('binance', {}).get('api_key', '')
            self.api_secret = api_config.get('binance', {}).get('api_secret', '')
            self.testnet = api_config.get('binance', {}).get('testnet', True)
        except Exception as e:
            self.logger.error(f"Error loading API config: {e}")
            self.api_key = ""
            self.api_secret = ""
            self.testnet = True
            
        # Initialize exchange client if available
        if self.api_key and self.api_secret:
            self.exchange_client = BinanceFuturesClient(
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet
            )
            print("✅ Real exchange client initialized")
        else:
            self.exchange_client = None
            print("⚠️ No API credentials, will use mock client for testing")
            
    def test_data_structures(self):
        """Test position monitor data structures."""
        print("\n=== Testing Data Structures ===")
        
        # Test AlertLevel enum
        print("Testing AlertLevel enum...")
        levels = [AlertLevel.INFO, AlertLevel.WARNING, AlertLevel.CRITICAL, AlertLevel.EMERGENCY]
        for level in levels:
            print(f"  ✅ {level.value}")
            
        # Test PositionAlert creation
        print("Testing PositionAlert creation...")
        alert = PositionAlert(
            symbol="DOGEUSDT",
            alert_type="test_alert",
            level=AlertLevel.INFO,
            message="Test alert message",
            timestamp=datetime.now(),
            data={"test_key": "test_value"}
        )
        print(f"  ✅ Alert created: {alert.symbol} - {alert.level.value}")
        
        # Test PositionMetrics creation
        print("Testing PositionMetrics creation...")
        metrics = PositionMetrics(
            symbol="DOGEUSDT",
            side="LONG",
            quantity=100.0,
            entry_price=0.08,
            current_price=0.082,
            unrealized_pnl=0.20,
            pnl_percentage=2.5,
            position_value=8.2,
            margin_used=0.82,
            leverage=10.0,
            timestamp=datetime.now()
        )
        print(f"  ✅ Metrics created: {metrics.symbol} - P&L: ${metrics.unrealized_pnl:.2f}")
        
        return True
        
    def test_position_monitor_initialization(self):
        """Test position monitor initialization."""
        print("\n=== Testing Position Monitor Initialization ===")
        
        # Test with mock exchange client
        mock_client = Mock()
        monitor = PositionMonitor(
            exchange_client=mock_client,
            monitoring_interval=10
        )
        print("✅ Position monitor initialized with mock client")
        
        # Test risk thresholds
        thresholds = monitor.get_risk_thresholds()
        print(f"✅ Risk thresholds loaded: {len(thresholds)} settings")
        for key, value in thresholds.items():
            print(f"  - {key}: {value}")
            
        # Test threshold updates
        new_thresholds = {
            'max_pnl_loss_percent': -5.0,
            'max_position_value': 500.0
        }
        monitor.update_risk_thresholds(new_thresholds)
        print("✅ Risk thresholds updated successfully")
        
        return True
        
    def test_position_data_parsing(self):
        """Test position data parsing with mock data."""
        print("\n=== Testing Position Data Parsing ===")
        
        # Create mock exchange client
        mock_client = Mock()
        
        # Mock position data
        mock_positions = [
            {
                'symbol': 'DOGEUSDT',
                'positionAmt': '100.00000000',
                'entryPrice': '0.08000000',
                'markPrice': '0.08200000',
                'unRealizedProfit': '0.20000000',
                'initialMargin': '0.80000000',
                'leverage': '10'
            },
            {
                'symbol': 'BTCUSDT',
                'positionAmt': '-0.00100000',
                'entryPrice': '45000.00000000',
                'markPrice': '44800.00000000',
                'unRealizedProfit': '0.20000000',
                'initialMargin': '45.00000000',
                'leverage': '5'
            }
        ]
        
        mock_client.get_positions.return_value = mock_positions
        
        # Initialize position monitor
        monitor = PositionMonitor(exchange_client=mock_client, monitoring_interval=10)
        
        # Test position parsing
        positions = monitor._get_current_positions()
        print(f"✅ Parsed {len(positions)} positions from mock data")
        
        for symbol, pos in positions.items():
            print(f"  📊 {symbol}: {pos.side} {pos.quantity:.6f} @ ${pos.entry_price:.4f}")
            print(f"      P&L: ${pos.unrealized_pnl:.2f} ({pos.pnl_percentage:.2f}%)")
            print(f"      Value: ${pos.position_value:.2f}, Leverage: {pos.leverage:.1f}x")
            
        return True
        
    def test_alert_generation(self):
        """Test alert generation functionality."""
        print("\n=== Testing Alert Generation ===")
        
        # Create mock exchange client
        mock_client = Mock()
        monitor = PositionMonitor(exchange_client=mock_client, monitoring_interval=10)
        
        # Track alerts
        alerts_received = []
        
        def alert_callback(alert):
            alerts_received.append(alert)
            print(f"  🚨 Alert: {alert.level.value} - {alert.symbol} - {alert.message}")
            
        monitor.alert_callback = alert_callback
        
        # Test P&L loss threshold alert
        print("Testing P&L loss threshold alert...")
        monitor._create_alert(
            symbol="DOGEUSDT",
            alert_type="pnl_loss_threshold",
            level=AlertLevel.CRITICAL,
            message="P&L loss exceeded threshold: -15.0%",
            data={"pnl_percentage": -15.0, "threshold": -10.0}
        )
        
        # Test position value threshold alert
        print("Testing position value threshold alert...")
        monitor._create_alert(
            symbol="BTCUSDT",
            alert_type="position_value_threshold",
            level=AlertLevel.WARNING,
            message="Position value exceeded threshold: $1500.0",
            data={"position_value": 1500.0, "threshold": 1000.0}
        )
        
        # Test leverage threshold alert
        print("Testing leverage threshold alert...")
        monitor._create_alert(
            symbol="ETHUSDT",
            alert_type="leverage_threshold",
            level=AlertLevel.WARNING,
            message="Leverage exceeded threshold: 15.0x",
            data={"leverage": 15.0, "threshold": 10.0}
        )
        
        print(f"✅ Generated {len(alerts_received)} alerts")
        
        # Test alert history
        alert_history = monitor.get_alert_history()
        print(f"✅ Alert history contains {len(alert_history)} alerts")
        
        return True
        
    def test_position_comparison(self):
        """Test position comparison functionality."""
        print("\n=== Testing Position Comparison ===")
        
        # Create mock exchange client
        mock_client = Mock()
        monitor = PositionMonitor(exchange_client=mock_client, monitoring_interval=10)
        
        # Track alerts
        alerts_received = []
        
        def alert_callback(alert):
            alerts_received.append(alert)
            print(f"  🔔 Position Alert: {alert.level.value} - {alert.symbol} - {alert.message}")
            
        monitor.alert_callback = alert_callback
        
        # Set up initial positions
        initial_positions = {
            'DOGEUSDT': PositionMetrics(
                symbol='DOGEUSDT',
                side='LONG',
                quantity=100.0,
                entry_price=0.08,
                current_price=0.08,
                unrealized_pnl=0.0,
                pnl_percentage=0.0,
                position_value=8.0,
                margin_used=0.8,
                leverage=10.0,
                timestamp=datetime.now()
            )
        }
        
        monitor.last_positions = initial_positions
        
        # Simulate position changes
        updated_positions = {
            'DOGEUSDT': PositionMetrics(
                symbol='DOGEUSDT',
                side='LONG',
                quantity=100.0,
                entry_price=0.08,
                current_price=0.082,
                unrealized_pnl=0.20,
                pnl_percentage=2.5,
                position_value=8.2,
                margin_used=0.82,
                leverage=10.0,
                timestamp=datetime.now()
            ),
            'BTCUSDT': PositionMetrics(
                symbol='BTCUSDT',
                side='SHORT',
                quantity=0.001,
                entry_price=45000.0,
                current_price=44800.0,
                unrealized_pnl=0.20,
                pnl_percentage=0.44,
                position_value=44.8,
                margin_used=4.5,
                leverage=5.0,
                timestamp=datetime.now()
            )
        }
        
        # Test position comparison
        monitor._compare_positions(updated_positions)
        
        print(f"✅ Position comparison generated {len(alerts_received)} alerts")
        
        return True
        
    def test_risk_metrics_calculation(self):
        """Test risk metrics calculation."""
        print("\n=== Testing Risk Metrics Calculation ===")
        
        # Create mock exchange client
        mock_client = Mock()
        monitor = PositionMonitor(exchange_client=mock_client, monitoring_interval=10)
        
        # Track alerts
        alerts_received = []
        
        def alert_callback(alert):
            alerts_received.append(alert)
            print(f"  ⚠️ Risk Alert: {alert.level.value} - {alert.symbol} - {alert.message}")
            
        monitor.alert_callback = alert_callback
        
        # Test positions with various risk scenarios
        test_positions = {
            'DOGEUSDT': PositionMetrics(
                symbol='DOGEUSDT',
                side='LONG',
                quantity=100.0,
                entry_price=0.08,
                current_price=0.072,  # -10% loss
                unrealized_pnl=-0.80,
                pnl_percentage=-10.0,
                position_value=7.2,
                margin_used=0.72,
                leverage=10.0,
                timestamp=datetime.now()
            ),
            'BTCUSDT': PositionMetrics(
                symbol='BTCUSDT',
                side='LONG',
                quantity=0.01,
                entry_price=45000.0,
                current_price=46000.0,
                unrealized_pnl=10.0,
                pnl_percentage=2.22,
                position_value=460.0,
                margin_used=45.0,
                leverage=20.0,  # High leverage
                timestamp=datetime.now()
            )
        }
        
        # Test risk metrics calculation
        monitor._check_risk_metrics(test_positions)
        
        print(f"✅ Risk metrics calculation generated {len(alerts_received)} alerts")
        
        return True
        
    def test_position_summary(self):
        """Test position summary functionality."""
        print("\n=== Testing Position Summary ===")
        
        # Create mock exchange client
        mock_client = Mock()
        monitor = PositionMonitor(exchange_client=mock_client, monitoring_interval=10)
        
        # Mock position data
        mock_positions = [
            {
                'symbol': 'DOGEUSDT',
                'positionAmt': '100.00000000',
                'entryPrice': '0.08000000',
                'markPrice': '0.08200000',
                'unRealizedProfit': '0.20000000',
                'initialMargin': '0.80000000',
                'leverage': '10'
            },
            {
                'symbol': 'BTCUSDT',
                'positionAmt': '-0.00100000',
                'entryPrice': '45000.00000000',
                'markPrice': '44800.00000000',
                'unRealizedProfit': '0.20000000',
                'initialMargin': '45.00000000',
                'leverage': '5'
            }
        ]
        
        mock_client.get_positions.return_value = mock_positions
        
        # Test position summary
        summary = monitor.get_position_summary()
        print("✅ Position Summary:")
        print(f"  Total Positions: {summary['total_positions']}")
        print(f"  Total Value: ${summary['total_value']:.2f}")
        print(f"  Total P&L: ${summary['total_pnl']:.2f}")
        print(f"  Total Margin: ${summary['total_margin']:.2f}")
        
        if summary['positions']:
            print("  Position Details:")
            for pos in summary['positions']:
                print(f"    {pos['symbol']}: {pos['side']} ${pos['position_value']:.2f} P&L: ${pos['unrealized_pnl']:.2f}")
                
        return True
        
    def test_real_exchange_integration(self):
        """Test integration with real exchange client."""
        print("\n=== Testing Real Exchange Integration ===")
        
        if not self.exchange_client:
            print("⚠️ No real exchange client available, skipping real integration test")
            return True
            
        try:
            # Initialize position monitor with real client
            monitor = PositionMonitor(
                exchange_client=self.exchange_client,
                monitoring_interval=30  # 30 seconds for testing
            )
            print("✅ Position monitor initialized with real exchange client")
            
            # Test getting real positions
            print("Testing real position data retrieval...")
            positions = monitor._get_current_positions()
            print(f"✅ Retrieved {len(positions)} real positions")
            
            for symbol, pos in positions.items():
                print(f"  📊 {symbol}: {pos.side} {pos.quantity:.6f} @ ${pos.entry_price:.4f}")
                print(f"      P&L: ${pos.unrealized_pnl:.2f} ({pos.pnl_percentage:.2f}%)")
                
            # Test position summary with real data
            summary = monitor.get_position_summary()
            print(f"✅ Real position summary: {summary['total_positions']} positions, ${summary['total_value']:.2f} value")
            
            return True
            
        except Exception as e:
            print(f"❌ Real exchange integration test failed: {e}")
            return False
            
    def run_all_tests(self):
        """Run all position monitor tests."""
        print("🧪 Position Monitor Test Suite")
        print("=" * 50)
        
        tests = [
            ("Data Structures", self.test_data_structures),
            ("Initialization", self.test_position_monitor_initialization),
            ("Position Data Parsing", self.test_position_data_parsing),
            ("Alert Generation", self.test_alert_generation),
            ("Position Comparison", self.test_position_comparison),
            ("Risk Metrics Calculation", self.test_risk_metrics_calculation),
            ("Position Summary", self.test_position_summary),
            ("Real Exchange Integration", self.test_real_exchange_integration)
        ]
        
        results = {}
        
        for test_name, test_func in tests:
            print(f"\n🔍 Running {test_name} test...")
            try:
                result = test_func()
                results[test_name] = result
                status = "✅ PASSED" if result else "❌ FAILED"
                print(f"{test_name}: {status}")
            except Exception as e:
                print(f"❌ {test_name} failed with error: {e}")
                results[test_name] = False
                
        # Summary
        print("\n" + "=" * 50)
        print("📊 Test Results Summary:")
        
        passed = sum(1 for result in results.values() if result)
        total = len(results)
        
        for test_name, result in results.items():
            status = "✅ PASSED" if result else "❌ FAILED"
            print(f"  {test_name}: {status}")
            
        print(f"\nOverall: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All position monitor tests passed!")
        else:
            print("⚠️ Some tests failed. Check the output above for details.")
            
        return passed == total


def main():
    """Main test function."""
    tester = PositionMonitorTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
