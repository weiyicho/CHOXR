# Monitor Folder Architecture & File Relationships

## 📁 File Structure Overview

```
monitor/
├── __init__.py                 # Package initialization
├── README.md                   # Documentation
├── ARCHITECTURE.md            # This file - architecture overview
├── monitoring_system.py       # 🎯 MAIN ORCHESTRATOR
├── position_monitor.py        # 📊 Position tracking
├── performance_monitor.py     # 📈 Performance analytics
├── discord_notifier.py       # 🔔 Discord notifications
└── discord_commander.py     # 🎮 Discord commands
```

## 🔄 File Relationships & Data Flow

### **1. Core Architecture**

```
┌─────────────────────────────────────────────────────────────┐
│                    monitoring_system.py                     │
│                    🎯 MAIN ORCHESTRATOR                      │
│                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │  Discord         │  │  Position       │  │ Performance  │ │
│  │  Integration     │  │  Monitoring     │  │ Analytics    │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
│           │                       │                   │      │
│           ▼                       ▼                   ▼      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ discord_notifier│  │position_monitor │  │performance_  │ │
│  │ discord_commander│ │                 │  │monitor       │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### **2. Detailed Component Relationships**

#### **A. monitoring_system.py (Main Orchestrator)**
```
┌─────────────────────────────────────────────────────────────┐
│                    monitoring_system.py                     │
│                                                             │
│  Dependencies:                                               │
│  ├── from .discord_notifier import DiscordNotifier          │
│  ├── from .discord_commander import DiscordCommander        │
│  ├── from .position_monitor import PositionMonitor         │
│  ├── from .performance_monitor import PerformanceMonitor   │
│  ├── from src.binance_sdk import BinanceFuturesClient      │
│  └── from util.utils import load_config, setup_logging     │
│                                                             │
│  Responsibilities:                                           │
│  ├── 🎯 Orchestrate all monitoring components              │
│  ├── ⚙️ Load configuration from config/monitoring.json     │
│  ├── 🔄 Start/stop monitoring loops                       │
│  ├── 📊 Coordinate alerts and notifications               │
│  └── 📈 Manage automated reporting                        │
└─────────────────────────────────────────────────────────────┘
```

#### **B. position_monitor.py (Position Tracking)**
```
┌─────────────────────────────────────────────────────────────┐
│                    position_monitor.py                      │
│                                                             │
│  Dependencies:                                               │
│  ├── from src.binance_sdk import BinanceFuturesClient      │
│  ├── from util.utils import setup_logging                 │
│  └── from datetime import datetime, timedelta              │
│                                                             │
│  Data Flow:                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│  │ Exchange    │───▶│ Position    │───▶│ Alert       │    │
│  │ Client      │    │ Data        │    │ Callback    │    │
│  └─────────────┘    └─────────────┘    └─────────────┘    │
│                                                             │
│  Responsibilities:                                           │
│  ├── 📊 Real-time position tracking                         │
│  ├── ⚠️ Risk threshold monitoring                          │
│  ├── 🔔 Alert generation and callbacks                     │
│  └── 📈 Position metrics calculation                       │
└─────────────────────────────────────────────────────────────┘
```

#### **C. performance_monitor.py (Performance Analytics)**
```
┌─────────────────────────────────────────────────────────────┐
│                   performance_monitor.py                    │
│                                                             │
│  Dependencies:                                               │
│  ├── from util.utils import setup_logging                 │
│  ├── from datetime import datetime, timedelta              │
│  └── import json                                           │
│                                                             │
│  Data Flow:                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│  │ Trade       │───▶│ Performance │───▶│ Analytics   │    │
│  │ Records     │    │ Metrics     │    │ Reports     │    │
│  └─────────────┘    └─────────────┘    └─────────────┘    │
│                                                             │
│  Responsibilities:                                           │
│  ├── 📈 Trade performance tracking                          │
│  ├── 📊 Win/loss ratio analysis                             │
│  ├── 💰 P&L calculations and metrics                       │
│  ├── 📉 Drawdown monitoring                                 │
│  └── 📋 Report generation and export                        │
└─────────────────────────────────────────────────────────────┘
```

#### **D. discord_notifier.py (Discord Notifications)**
```
┌─────────────────────────────────────────────────────────────┐
│                    discord_notifier.py                      │
│                                                             │
│  Dependencies:                                               │
│  ├── import requests                                        │
│  ├── import json                                           │
│  └── from datetime import datetime                         │
│                                                             │
│  Data Flow:                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│  │ Alert       │───▶│ Discord     │───▶│ Discord     │    │
│  │ Data        │    │ Message     │    │ Channel     │    │
│  └─────────────┘    └─────────────┘    └─────────────┘    │
│                                                             │
│  Responsibilities:                                           │
│  ├── 🔔 Send trade notifications                            │
│  ├── ⚠️ Send risk alerts                                   │
│  ├── 📊 Send performance reports                           │
│  └── 🎨 Format rich embed messages                         │
└─────────────────────────────────────────────────────────────┘
```

#### **E. discord_commander.py (Discord Commands)**
```
┌─────────────────────────────────────────────────────────────┐
│                    discord_commander.py                     │
│                                                             │
│  Dependencies:                                               │
│  ├── import requests                                        │
│  ├── import json                                           │
│  └── from datetime import datetime                         │
│                                                             │
│  Data Flow:                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│  │ Discord     │───▶│ Command     │───▶│ System      │    │
│  │ Commands    │    │ Parser      │    │ Actions     │    │
│  └─────────────┘    └─────────────┘    └─────────────┘    │
│                                                             │
│  Responsibilities:                                           │
│  ├── 🎮 Parse Discord commands                             │
│  ├── 🔄 Execute system actions                             │
│  ├── 📊 Query system status                                  │
│  └── 🛑 Emergency controls                                 │
└─────────────────────────────────────────────────────────────┘
```

## 🔄 Data Flow Diagram

### **Complete System Data Flow:**

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              MONITORING SYSTEM DATA FLOW                        │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Exchange  │    │  Position   │    │ Performance │    │   Discord   │
│   Client    │    │  Monitor    │    │  Monitor    │    │ Integration │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                   │                   │                   │
       ▼                   ▼                   ▼                   ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ Position    │    │ Alert       │    │ Trade       │    │ Notifications│
│ Data        │    │ Generation  │    │ Records     │    │ & Commands  │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                   │                   │                   │
       ▼                   ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        monitoring_system.py                                   │
│                           MAIN ORCHESTRATOR                                   │
│                                                                               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                │
│  │ Configuration   │  │ Alert           │  │ Automated       │                │
│  │ Management     │  │ Coordination    │  │ Reporting       │                │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘                │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## 📊 Component Interaction Matrix

| Component | Uses | Used By | Data Exchange |
|-----------|------|---------|---------------|
| **monitoring_system.py** | All other components | External systems | Orchestrates all |
| **position_monitor.py** | BinanceFuturesClient | monitoring_system.py | Position data, alerts |
| **performance_monitor.py** | None (standalone) | monitoring_system.py | Trade records, metrics |
| **discord_notifier.py** | None (standalone) | monitoring_system.py | Notifications |
| **discord_commander.py** | None (standalone) | monitoring_system.py | Commands, responses |

## 🔧 Configuration Dependencies

### **config/monitoring.json Structure:**
```json
{
  "discord": {
    "webhook_url": "→ discord_notifier.py",
    "channel_id": "→ discord_commander.py"
  },
  "monitoring": {
    "interval": "→ monitoring_system.py",
    "position_monitoring": "→ position_monitor.py"
  },
  "alerts": {
    "position": "→ position_monitor.py",
    "performance": "→ performance_monitor.py"
  }
}
```

## 🧪 Testing Dependencies

### **test_monitoring_system.py:**
```
┌─────────────────────────────────────────────────────────────┐
│                test_monitoring_system.py                    │
│                                                             │
│  Tests:                                                      │
│  ├── Discord Notifications (discord_notifier.py)           │
│  ├── Performance Monitor (performance_monitor.py)          │
│  ├── Position Monitor (position_monitor.py)                │
│  └── Integrated System (monitoring_system.py)              │
│                                                             │
│  Dependencies:                                               │
│  ├── from monitor.monitoring_system import MonitoringSystem │
│  ├── from monitor.discord_notifier import DiscordNotifier  │
│  ├── from monitor.position_monitor import PositionMonitor   │
│  └── from monitor.performance_monitor import PerformanceMonitor │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Integration Points

### **External System Integration:**
- **Binance SDK** → `position_monitor.py`
- **Order Management** → `performance_monitor.py`
- **Risk Management** → `position_monitor.py`
- **Strategy Engine** → `performance_monitor.py`
- **Discord API** → `discord_notifier.py`, `discord_commander.py`

### **Internal Data Flow:**
1. **Exchange Data** → `position_monitor.py` → `monitoring_system.py`
2. **Trade Records** → `performance_monitor.py` → `monitoring_system.py`
3. **Alerts** → `monitoring_system.py` → `discord_notifier.py`
4. **Commands** → `discord_commander.py` → `monitoring_system.py`

## 📈 Scalability & Extensibility

### **Adding New Components:**
1. Create new monitor component
2. Import in `monitoring_system.py`
3. Initialize in `_initialize_components()`
4. Add to monitoring loop
5. Update configuration schema

### **Adding New Alert Types:**
1. Define in `position_monitor.py`
2. Add to `AlertLevel` enum
3. Update `_create_alert()` method
4. Configure thresholds in `config/monitoring.json`

This architecture provides a clean, modular, and extensible monitoring system that can grow with your trading engine needs! 🚀
