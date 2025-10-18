# Monitor Folder - Visual File Relationships

## 🏗️ System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              MONITOR FOLDER ARCHITECTURE                        │
└─────────────────────────────────────────────────────────────────────────────────┘

                    ┌─────────────────────────────────────┐
                    │        monitoring_system.py         │
                    │         🎯 MAIN ORCHESTRATOR        │
                    │                                     │
                    │  • Loads configuration              │
                    │  • Orchestrates all components     │
                    │  • Manages monitoring loops         │
                    │  • Coordinates alerts & reports     │
                    └─────────────────────────────────────┘
                                    │
                    ┌───────────────┬───────────────┬───────────────┐
                    │             │               │               │
                    ▼             ▼               ▼               ▼
        ┌─────────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
        │ discord_notifier│ │position_    │ │performance_ │ │discord_     │
        │ .py             │ │monitor.py   │ │monitor.py   │ │commander.py │
        │                 │ │             │ │             │ │             │
        │ 🔔 Notifications│ │ 📊 Position │ │ 📈 Analytics│ │ 🎮 Commands │
        │ • Trade alerts  │ │ • P&L track │ │ • Win/loss  │ │ • !status   │
        │ • Risk warnings │ │ • Risk mgmt │ │ • Reports   │ │ • !positions│
        │ • Reports       │ │ • Alerts    │ │ • Export    │ │ • !risk     │
        └─────────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
```

## 🔄 Data Flow Relationships

### **1. Position Monitoring Flow:**
```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Binance   │───▶│  Position   │───▶│ Monitoring  │───▶│   Discord   │
│   Exchange  │    │   Monitor   │    │   System    │    │ Notifications│
│   Client    │    │             │    │             │    │             │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                   │                   │                   │
       ▼                   ▼                   ▼                   ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ Position    │    │ Alert       │    │ Alert       │    │ Discord     │
│ Data        │    │ Generation  │    │ Coordination│    │ Messages    │
│ (Real-time) │    │ (Risk mgmt) │    │ (Orchestrator)│    │ (Rich embeds)│
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

### **2. Performance Analytics Flow:**
```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Trade     │───▶│ Performance │───▶│ Monitoring  │───▶│   Discord   │
│   Records   │    │   Monitor   │    │   System    │    │   Reports   │
│             │    │             │    │             │    │             │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                   │                   │                   │
       ▼                   ▼                   ▼                   ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ Trade       │    │ Analytics   │    │ Report      │    │ Automated   │
│ Execution   │    │ & Metrics   │    │ Generation  │    │ Reporting   │
│ (P&L, fees)│    │ (Win/loss)  │    │ (Daily)     │    │ (24h cycle) │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

### **3. Discord Command Flow:**
```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Discord   │───▶│   Discord   │───▶│ Monitoring  │───▶│   System    │
│   Commands  │    │  Commander  │    │   System    │    │   Actions   │
│ (!status)   │    │             │    │             │    │             │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                   │                   │                   │
       ▼                   ▼                   ▼                   ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ User        │    │ Command     │    │ Action      │    │ Response    │
│ Input       │    │ Parsing     │    │ Execution   │    │ Generation  │
│ (!positions)│    │ (!status)   │    │ (Get data)  │    │ (Discord)   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

## 📁 File Dependency Tree

```
monitor/
├── __init__.py
├── README.md
├── ARCHITECTURE.md          ← This file
├── DIAGRAM.md              ← Visual relationships
│
├── monitoring_system.py    ← 🎯 MAIN ENTRY POINT
│   ├── imports discord_notifier
│   ├── imports discord_commander  
│   ├── imports position_monitor
│   ├── imports performance_monitor
│   ├── imports src.binance_sdk
│   └── imports util.utils
│
├── position_monitor.py     ← 📊 POSITION TRACKING
│   ├── imports src.binance_sdk
│   ├── imports util.utils
│   └── imports datetime
│
├── performance_monitor.py  ← 📈 PERFORMANCE ANALYTICS
│   ├── imports util.utils
│   ├── imports datetime
│   └── imports json
│
├── discord_notifier.py     ← 🔔 DISCORD NOTIFICATIONS
│   ├── imports requests
│   ├── imports json
│   └── imports datetime
│
└── discord_commander.py     ← 🎮 DISCORD COMMANDS
    ├── imports requests
    ├── imports json
    └── imports datetime
```

## 🔧 Configuration Integration

```
config/monitoring.json
├── discord/
│   ├── webhook_url     → discord_notifier.py
│   └── channel_id      → discord_commander.py
├── monitoring/
│   ├── interval        → monitoring_system.py
│   └── position_monitoring → position_monitor.py
├── alerts/
│   ├── position        → position_monitor.py
│   └── performance     → performance_monitor.py
└── reports/
    ├── auto            → monitoring_system.py
    └── interval_hours   → monitoring_system.py
```

## 🧪 Testing Integration

```
tests/test_monitoring_system.py
├── imports monitoring_system
├── imports discord_notifier
├── imports position_monitor
├── imports performance_monitor
└── tests all components
```

## 🚀 External Dependencies

```
External Systems
├── Binance Exchange API
│   └── → position_monitor.py
├── Discord API
│   ├── → discord_notifier.py
│   └── → discord_commander.py
├── Trading Engine
│   ├── → monitoring_system.py
│   └── → performance_monitor.py
└── Configuration Files
    ├── → monitoring_system.py
    └── → all components
```

## 📊 Component Responsibilities Matrix

| Component | Primary Role | Data Input | Data Output | External Dependencies |
|-----------|-------------|------------|-------------|---------------------|
| **monitoring_system.py** | Orchestrator | Config, Alerts | System Control | All other components |
| **position_monitor.py** | Position Tracking | Exchange Data | Position Alerts | BinanceFuturesClient |
| **performance_monitor.py** | Analytics | Trade Records | Performance Metrics | None (standalone) |
| **discord_notifier.py** | Notifications | Alert Data | Discord Messages | Discord Webhook API |
| **discord_commander.py** | Command Interface | Discord Commands | System Actions | Discord Webhook API |

## 🔄 Real-time Data Flow Example

```
1. Exchange Data Update
   └── BinanceFuturesClient.get_positions()
       └── position_monitor.py._get_current_positions()
           └── position_monitor.py._check_positions()
               └── position_monitor.py._create_alert()
                   └── monitoring_system.py._handle_position_alert()
                       └── discord_notifier.py.send_embed()

2. Trade Execution
   └── Trading Engine.record_trade()
       └── monitoring_system.py.record_trade()
           └── performance_monitor.py.record_trade()
               └── discord_notifier.py.send_embed()

3. Discord Command
   └── Discord User: "!status"
       └── discord_commander.py.parse_command()
           └── monitoring_system.py.get_system_status()
               └── discord_notifier.py.send_embed()
```

This architecture provides a clean, modular, and highly integrated monitoring system! 🎯
