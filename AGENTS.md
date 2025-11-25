# Repository Guidelines

## Project Structure & Module Organization

The Trading Engine follows a layered architecture with clear separation of concerns:

```
Trading_EngineV1/
├── src/                    # Exchange SDK interfaces (Binance, Bybit, etc.)
├── config/                 # Configuration files (API keys, strategy params)
├── risk/                   # Risk management and validation
├── order/                  # Order execution and price calculation
├── monitor/                # Discord notifications and monitoring
├── websocket/              # Real-time data streams
├── util/                   # Utility functions and config management
├── tests/                  # Comprehensive test suite
└── strategy/strategy1/     # Trading strategy implementation
    ├── src/                # Core strategy logic & research notebooks
    ├── pipeline/           # Data processing pipeline
    ├── data/               # Market data storage
    └── main.py             # Strategy entry point
```

**Key Modules:**
- **src/**: Exchange interface layer - unified APIs for multiple exchanges (Binance, Bybit)
- **config/**: JSON-based configuration management for API keys and parameters
- **risk/**: Portfolio margin account risk management, liquidation prevention, and exposure monitoring
- **order/**: Order management with tick size abstraction and limit price calculation
- **monitor/**: Discord notifications, performance tracking, and position monitoring
- **strategy/**: Signal generation, order logic, and strategy orchestration
- **tests/**: Extensive testing suite covering SDK, risk management, and live trading scenarios

## Build, Test, and Development Commands

**Development Setup:**
```bash
# Install dependencies
pip install -r requirements.txt

# Run strategy development (Jupyter Notebook)
# Open strategy/strategy1/src/research.ipynb in your preferred editor or run:
jupyter notebook strategy/strategy1/src/research.ipynb

# Run Strategy / Check Account Status
python strategy/strategy1/main.py

# Test exchange connectivity
python -c "from src.binance_sdk import BinanceFuturesClient; print('SDK ready')"
```

**Data Pipeline:**
```bash
# Fetch market data
python pipeline/Loader.py

# Process and merge data
python pipeline/merge.py
```

## Coding Style & Naming Conventions

**Python Standards:**
- Use 4-space indentation
- Follow PEP 8 for function and variable names
- Class names: `PascalCase` (e.g., `BinanceFuturesClient`)
- Function names: `snake_case` (e.g., `place_order`)
- Private methods: `_leading_underscore`

**File Organization:**
- One class per file for core components
- Use `__init__.py` files for package exports
- Store configuration in JSON format (`config/api.json`)
- Keep sensitive credentials in separate config files (excluded from version control)

**Import Conventions:**
```python
# Standard library first
import datetime
import json

# Third-party packages
import pandas as pd
import requests

# Local modules
from util.config_manager import get_api_config
from monitor.discord_notifier import DiscordNotifier
```

## Testing Guidelines

**Testing Framework:**
- Target 80% code coverage minimum for core modules
- Mock exchange APIs for deterministic testing
- Comprehensive test suite in `/tests/` directory covering:
  - Unit tests for SDK and Utils
  - Integration tests for Risk and Order modules
  - Live trading tests (DOGE/USDT)
  - Discord monitoring tests

**Testing Strategy:**
- Mock external API responses for exchange SDKs
- Use synthetic data for strategy validation
- Test risk calculations with known scenarios
- Validate order execution logic with both mock and live (testnet) environments

**Test Naming:**
- Test files: `test_module_name.py`
- Test functions: `test_function_name_behavior`

## Commit & Pull Request Guidelines

**Commit Messages:**
- Use descriptive, present-tense messages
- Include module affected: `feat(src): add order validation`
- Examples: `fix(risk): correct position size calculation`, `docs: update API documentation`

**Pull Request Requirements:**
- Link to related issues or requirements
- Include test coverage for new features
- Update documentation for API changes
- Ensure all existing tests pass

## Architecture Overview

**Data Flow:**
```
Configuration → Strategy → Risk → Exchange SDK → Monitor
```

**Key Principles:**
- **Loose Coupling**: Modules communicate through well-defined interfaces
- **Configuration-Driven**: All parameters stored in JSON files
- **Dependency Direction**: Top-down flow prevents cyclic dependencies
- **Extensibility**: New exchanges and strategies can be added modularly

## Security & Configuration Tips

**API Key Management:**
- Store credentials in `config/api.json` (not in repository)
- Use environment variables for production secrets
- Implement API rate limiting and error handling

**Risk Management:**
- All trades must pass risk validation before execution
- Position limits and exposure caps are enforced
- Real-time monitoring through Discord integration

## Exchange SDK Development

**Adding New Exchanges:**
1. Create `src/exchange_name_sdk.py`
2. Implement standardized interfaces:
   ```python
   get_order_book(symbol: str)
   place_order(symbol: str, side: str, qty: float, price: float)
   fetch_balance()
   ```
3. Return unified data schemas for consistency
4. Add to exchange registry in strategy modules

**Important Notes:**
- Binance SDK is critical and well-tested - preserve core logic
- Function names can be improved for better readability
- Maintain backward compatibility when modifying existing interfaces
- **API endpoints and URLs are correct - DO NOT change without explicit permission**
- Always ask before modifying any web URLs, API endpoints, or network configurations
