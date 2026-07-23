# Monitoring System

Comprehensive monitoring and alerting system for the Trading Engine.

## 📁 Components

### **Core Monitoring Components**

- **`monitoring_system.py`** - Integrated monitoring system that orchestrates all components
- **`position_monitor.py`** - Real-time position monitoring and risk assessment
- **`performance_monitor.py`** - Performance tracking and analytics
- **`discord_notifier.py`** - Discord notifications for trades, alerts, and reports
- **`discord_commander.py`** - Discord command interface for system control

## 🚀 Features

### **Position Monitoring**
- Real-time position tracking
- P&L change alerts
- Risk threshold monitoring
- Position size validation
- Margin requirement checks
- Leverage monitoring

### **Performance Tracking**
- Trade performance analytics
- Win/loss ratio tracking
- P&L analysis
- Drawdown monitoring
- Sharpe ratio calculation
- Strategy performance comparison

### **Discord Integration**
- Real-time trade notifications
- Risk alerts and warnings
- Automated performance reports
- System status updates
- Command interface for remote control

### **Automated Reporting**
- Daily performance summaries
- Position status reports
- Risk metrics analysis
- Trade history exports
- Custom report generation

## ⚙️ Configuration

### **Monitoring Configuration (`config/monitoring.json`)**

```json
{
  "discord": {
    "webhook_url": "YOUR_DISCORD_WEBHOOK_URL",
    "channel_id": "YOUR_DISCORD_CHANNEL_ID",
    "enabled": true
  },
  "monitoring": {
    "interval": 5,
    "position_monitoring": true,
    "performance_monitoring": true
  },
  "alerts": {
    "position": {
      "pnl_loss_threshold": -10.0,
      "position_value_threshold": 1000.0,
      "leverage_threshold": 10.0
    }
  },
  "reports": {
    "auto": true,
    "interval_hours": 24
  }
}
```

### **Discord Setup**

1. **Create Discord Webhook:**
   - Go to your Discord server settings
   - Navigate to Integrations → Webhooks
   - Create a new webhook
   - Copy the webhook URL

2. **Configure Monitoring:**
   ```bash
   # Update config/monitoring.json with your webhook URL
   python3 tests/setup_api_config.py
   ```

## 🧪 Testing

### **Run Monitoring System Tests**

```bash
# Test all monitoring components
python3 tests/test_monitoring_system.py

# Test individual components
python3 -c "from tests.test_monitoring_system import MonitoringSystemTester; tester = MonitoringSystemTester(); tester.test_discord_notifications()"
```

### **Test Components**

- **Discord Notifications** - Test webhook connectivity and message formatting
- **Performance Monitor** - Test trade recording and analytics
- **Position Monitor** - Test real-time position tracking
- **Integrated System** - Test complete monitoring workflow

## 📊 Usage Examples

### **Basic Monitoring Setup**

```python
from monitor.monitoring_system import MonitoringSystem
from src.binance_sdk import BinanceFuturesClient

# Initialize monitoring system
monitoring = MonitoringSystem("config/monitoring.json")

# Set exchange client
exchange_client = BinanceFuturesClient(api_key, api_secret, testnet=True)
monitoring.set_exchange_client(exchange_client)

# Start monitoring
monitoring.start_monitoring()
```

### **Discord Notifications**

```python
from monitor.discord_notifier import DiscordNotifier

# Initialize notifier
notifier = DiscordNotifier(webhook_url="YOUR_WEBHOOK_URL")

# Send trade notification
notifier.notify_order_placed(
    symbol="DOGEUSDT",
    side="BUY",
    quantity=100.0,
    price=0.08,
    order_type="LIMIT",
    account_type="TEST"
)
```

### **Performance Tracking**

```python
from monitor.performance_monitor import PerformanceMonitor

# Initialize performance monitor
perf_monitor = PerformanceMonitor()

# Record a trade
perf_monitor.record_trade(
    symbol="DOGEUSDT",
    side="BUY",
    quantity=100.0,
    entry_price=0.08,
    exit_price=0.082,
    entry_time=datetime.now() - timedelta(minutes=30),
    exit_time=datetime.now(),
    fees=0.1,
    strategy="test_strategy"
)

# Get performance metrics
metrics = perf_monitor.get_performance_metrics()
print(f"Win Rate: {metrics.win_rate:.1f}%")
print(f"Net P&L: ${metrics.net_pnl:.2f}")
```

### **Position Monitoring**

```python
from monitor.position_monitor import PositionMonitor

# Initialize position monitor
pos_monitor = PositionMonitor(
    exchange_client=exchange_client,
    monitoring_interval=5
)

# Start monitoring
pos_monitor.start_monitoring()

# Get position summary
summary = pos_monitor.get_position_summary()
print(f"Total Positions: {summary['total_positions']}")
print(f"Total P&L: ${summary['total_pnl']:.2f}")
```

## 🔧 Discord Commands

The Discord command interface supports:

- `!status` - Get system status
- `!positions` - View current positions
- `!risk` - Check risk metrics
- `!report` - Generate performance report
- `!stop` - Emergency stop
- `!cancel` - Cancel all orders
- `!help` - Show available commands

## 📈 Alert Levels

### **Position Alerts**
- **INFO** - Position changes, P&L updates
- **WARNING** - Risk threshold breaches
- **CRITICAL** - Significant losses, margin issues
- **EMERGENCY** - System failures, connectivity issues

### **Risk Thresholds**
- **P&L Loss** - Maximum percentage loss per position
- **Position Value** - Maximum position size
- **Leverage** - Maximum leverage allowed
- **Margin Ratio** - Maximum margin usage

## 📊 Performance Metrics

### **Trade Analytics**
- Total trades count
- Win/loss ratio
- Average win/loss amounts
- Profit factor
- Sharpe ratio
- Maximum drawdown

### **Risk Metrics**
- Position exposure
- Margin utilization
- Leverage analysis
- Correlation analysis
- Volatility metrics

## 🛡️ Safety Features

- **Real-time monitoring** - Continuous position tracking
- **Automated alerts** - Immediate notification of issues
- **Risk controls** - Configurable risk thresholds
- **Emergency stops** - Remote system control
- **Audit logging** - Complete activity tracking

## 📁 File Structure

```
monitor/
├── README.md                    # This file
├── monitoring_system.py         # Integrated monitoring system
├── position_monitor.py          # Position monitoring
├── performance_monitor.py       # Performance tracking
├── discord_notifier.py         # Discord notifications
├── discord_commander.py        # Discord commands
└── __init__.py                 # Package initialization
```

## 🔄 Integration

The monitoring system integrates with:

- **Binance SDK** - Real-time position data
- **Order Management** - Trade execution tracking
- **Risk Management** - Risk assessment and alerts
- **Strategy Engine** - Performance attribution
- **Discord** - Notifications and control interface

## 📝 Logging

All monitoring activities are logged with:

- **Timestamp** - Precise timing information
- **Level** - Alert severity classification
- **Context** - Relevant position and trade data
- **Actions** - System responses and notifications

## 🚨 Troubleshooting

### **Common Issues**

1. **Discord Notifications Not Working**
   - Check webhook URL configuration
   - Verify Discord server permissions
   - Test webhook connectivity

2. **Position Monitoring Issues**
   - Verify exchange client connection
   - Check API credentials
   - Ensure sufficient permissions

3. **Performance Data Missing**
   - Check file permissions for data storage
   - Verify trade recording calls
   - Review data export functionality

### **Debug Mode**

Enable debug logging for troubleshooting:

```python
import logging
logging.getLogger("monitor").setLevel(logging.DEBUG)
```
