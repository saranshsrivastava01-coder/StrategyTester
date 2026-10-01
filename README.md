# Strategy Backtester v1

A comprehensive Python-based backtesting system for algorithmic trading strategies with Pine Script to Python conversion and side-by-side reconciliation against TradingView results.

## Features

✅ **OHLC Data Loading** - CSV import with case-insensitive column detection and timezone handling
✅ **Pine Script to Python Conversion** - Automatic parameter extraction from `input()` calls
✅ **Dynamic Strategy Loading** - Load and execute Python strategies from uploaded code
✅ **Bar-by-Bar Backtest Engine** - TradingView-compatible order execution logic:
  - Market orders fill at next bar's open
  - Strategy.exit stops handled correctly
  - Reversal logic closes existing trades
  - Pyramiding and max entry limits

✅ **9 KPI Reconciliation**:
  1. Total Trades
  2. Winning Trades
  3. Losing Trades
  4. Win Rate
  5. Max Profit
  6. Max Loss
  7. Total PnL
  8. Max Drawdown (Close-to-Close)
  9. Max Drawdown (Intrabar)
  10. Profit Factor

✅ **Web UI** - Side-by-side TradingView vs Python comparison with:
  - File uploads (Pine Script, Excel, Python, OHLC CSV)
  - Parameter extraction from Excel Properties tab
  - Real-time backtest execution
  - Dark/Light mode toggle
  - Automatic KPI matching and status display

✅ **Parameter Optimization** - Test multiple parameter combinations with detailed results

## Project Structure

```
.
├── strategy_ui.py              # Flask backend server
├── base_strategy.py            # Abstract strategy framework
├── pine_script_converter.py    # Pine Script parser and parameter extraction
├── strategy_optimizer.py       # Strategy loading and parameter testing
├── ohlc_loader.py             # CSV loader with validation
├── utils.py                   # Technical indicators library
├── templates/
│   └── strategy_ui.html       # Web UI (dark/light mode, KPI tables)
├── static/
│   └── js/app.js             # Frontend JavaScript
├── uploads/                   # User uploaded files
├── input/                     # Input data directory
├── output/                    # Backtest results
└── README.md                  # This file
```

## Installation

### Prerequisites
- Python 3.8+
- pip

### Setup

1. **Clone the repository**
```bash
git clone <repo-url>
cd StrategyTester_v1
```

2. **Create virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install flask pandas numpy openpyxl
```

## Usage

### Starting the Web UI

```bash
python3 strategy_ui.py
```

Visit `http://localhost:5001` in your browser.

### Web UI Workflow

1. **Left Column (TradingView/Excel)**:
   - Upload Pine Script (.pine/.txt)
   - Upload Excel output file (.xlsx)
   - View extracted KPIs and parameters

2. **Right Column (Python/Backtest)**:
   - Upload Python strategy (.py)
   - Upload Excel file to extract parameters
   - Upload OHLC CSV data
   - Click "Run Backtest" to execute
   - View calculated KPIs

3. **Comparison**:
   - Tables show side-by-side values
   - Green checkmark = matching KPIs
   - Yellow warning = slight difference

### Command Line Usage

```python
from base_strategy import BaseStrategy
from ohlc_loader import OHLCDataLoader

# Load OHLC data
df = OHLCDataLoader.load('data.csv')

# Define strategy (inherit from BaseStrategy)
class MyStrategy(BaseStrategy):
    def calculate_indicators(self):
        # Implement indicator calculations
        pass
    
    def generate_signals(self):
        # Implement signal generation
        pass
    
    def run_backtest(self):
        # Implement bar-by-bar backtest logic
        pass

# Run backtest
strategy = MyStrategy(df, parameters={'param1': value1})
results = strategy.run()
print(f"Total PnL: {results['net_profit']}")
print(f"Win Rate: {results['percent_profitable']:.1f}%")
```

## API Endpoints

### Upload & Analysis

**POST /api/upload-strategy**
- Upload Pine Script file
- Returns: Extracted parameters from `input()` calls

**POST /api/upload-excel**
- Upload Excel output file
- Parses Trades, Performance, Trades analysis, Risk-adjusted tabs

**POST /api/extract-excel-parameters**
- Extract configurable parameters from Excel Properties tab
- Returns: Parameter dictionary

**POST /api/reconcile-kpis**
- Calculate 9 KPIs from Excel Trades tab
- Returns: KPI values with formulas

**POST /api/backtest-kpis**
- Load Python strategy and OHLC data
- Execute backtest
- Calculate 9 KPIs
- Returns: KPI values and trade data

**POST /api/validate-strategy**
- Validate Python code against TradingView results
- Returns: Validation summary

## Technical Indicators Supported

- EMA (Exponential Moving Average)
- SMA (Simple Moving Average)
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- Bollinger Bands
- ATR (Average True Range)
- Drawdown calculations

## Strategy Framework

### BaseStrategy Interface

All strategies must inherit from `BaseStrategy` and implement:

```python
class MyStrategy(BaseStrategy):
    def __init__(self, df, parameters=None):
        super().__init__(df, parameters)
    
    def calculate_indicators(self):
        """Calculate all technical indicators"""
        pass
    
    def generate_signals(self):
        """Generate entry/exit signals"""
        pass
    
    def run_backtest(self):
        """Execute bar-by-bar backtest"""
        pass
    
    def get_results(self):
        """Return backtest results"""
        pass
```

### Return Format

Backtest `run()` should return dict with:
```python
{
    'trades': pd.DataFrame([
        {
            'side': 'Long'/'Short',
            'entry_time': datetime,
            'exit_time': datetime,
            'entry_price': float,
            'exit_price': float,
            'pnl': float,
            'exit_reason': str,
            'qty': int
        },
        ...
    ]),
    'open_trades': pd.DataFrame(...),
    'net_profit': float,
    'max_drawdown': float,
    'total_closed_trades': int,
    'percent_profitable': float,
    # ... other metrics
}
```

## Desktop Launcher (macOS)

Double-click `LAUNCH_STRATEGY_UI.command` to start the web server and open the browser automatically.

(The launcher creates a virtual environment at `/tmp/strategy_venv` to bypass System Integrity Protection)

## Configuration

### Parameters

Modify default parameters in individual strategy files or via the UI by uploading an Excel file with a Properties tab.

Supported parameter types:
- Integer ranges (minval, maxval)
- Float ranges
- Dropdown/select options
- Boolean flags

### OHLC Column Detection

The system supports flexible CSV headers:
- Time column: `time`, `date`, `datetime`, `timestamp`
- Other columns: `open`, `high`, `low`, `close`, `volume`

All column names are case-insensitive.

## Known Limitations

1. **Freedom Filter Lower TF** - Requires lower-TF OHLC data; otherwise bias stays 0
2. **Parameter Ranges** - Currently supports exact values; optimization loops run sequentially
3. **Commission/Slippage** - Not included (matches TradingView default behavior)

## Performance

- Tested with 20,000+ OHLC bars
- Bar-by-bar simulation is CPU-bound
- Typical backtest: <5 seconds for 1000+ trades

## Troubleshooting

### "File not found" error
- Ensure CSV has first 5 columns: Time, Open, High, Low, Close
- Check file encoding (UTF-8 recommended)

### Strategy execution fails
- Verify strategy inherits from `BaseStrategy`
- Check method implementations: `calculate_indicators()`, `generate_signals()`, `run_backtest()`
- Review console output for specific error messages

### KPIs showing 0
- Ensure OHLC data loads correctly (check data preview)
- Verify strategy generates trades (check trade count)
- Check parameter values are valid for the strategy

## Contributing

Contributions welcome! Areas for improvement:
- Parameter optimization algorithms (genetic algorithm, Bayesian)
- More technical indicators
- Performance optimizations
- Additional Pine Script language features

## License

MIT

## Author

Created as a strategy backtesting and reconciliation tool.
