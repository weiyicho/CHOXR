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
└── strategy/strategy1/     # Trading strategy implementation
    ├── src/                # Core strategy logic
    ├── pipeline/           # Data processing pipeline
    └── data/               # Market data storage
```

**Key Modules:**
- **src/**: Exchange interface layer - unified APIs for multiple exchanges
- **config/**: JSON-based configuration management for API keys and parameters
- **risk/**: Trade validation, position limits, and exposure monitoring
- **strategy/**: Signal generation, order logic, and strategy orchestration

## Build, Test, and Development Commands

**Development Setup:**
```bash
# Install dependencies
pip install -r requirements.txt

# Run strategy development
cd strategy/strategy1
python -m src.research  # Jupyter notebook for strategy research

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
- Store configuration in JSON format
- Keep sensitive credentials in separate config files

**Import Conventions:**
```python
# Standard library first
import datetime
import json

# Third-party packages
import pandas as pd
import requests

# Local modules
from .adapters.storage import FundingRateStorage
```

## Testing Guidelines

**Testing Framework:**
- Target 80% code coverage minimum for core modules
- Mock exchange APIs for deterministic testing
- Unit tests under `/tests/` directory (to be implemented)

**Testing Strategy:**
- Mock external API responses for exchange SDKs
- Use synthetic data for strategy validation
- Test risk calculations with known scenarios
- Validate order execution logic without live trading

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
