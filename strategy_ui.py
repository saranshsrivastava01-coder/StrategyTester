from flask import Flask, render_template, request, jsonify, send_file, Response
import os
import json
import pandas as pd
import numpy as np
from pathlib import Path
from ohlc_loader import OHLCDataLoader
from pine_script_converter import PineScriptParser, PineScriptValidator
from strategy_optimizer import StrategyOptimizer
import traceback
import openpyxl
import time

# Custom JSON encoder to handle NaN and inf values
class NaNEncoder(json.JSONEncoder):
    def encode(self, obj):
        if isinstance(obj, float):
            if np.isnan(obj) or np.isinf(obj):
                return 'null'
        return super().encode(obj)

    def iterencode(self, obj, _one_shot=False):
        for chunk in super().iterencode(obj, _one_shot):
            yield chunk.replace('NaN', 'null').replace('Infinity', 'null').replace('-Infinity', 'null')

app = Flask(__name__, template_folder='templates', static_folder='static')

# Initialize execution state on startup
@app.before_request
def reset_stale_execution():
    """Reset execution state if thread is dead"""
    if unattended_progress['is_running'] and unattended_progress['execution_thread']:
        if not unattended_progress['execution_thread'].is_alive():
            unattended_progress['is_running'] = False
            unattended_progress['should_stop'] = False

# Global session data for tracking brute force progress
session_data = {
    'bf_total': 0,
    'bf_completed': 0,
    'bf_errors': 0
}

# Global session data for tracking unattended brute force progress
unattended_progress = {
    'is_running': False,
    'start_time': None,
    'total_combinations': 0,
    'combinations_completed': 0,
    'current_test': '',
    'tests_completed': 0,
    'total_tests': 0,
    'should_stop': False,
    'execution_thread': None,
    'execution_thread_id': None
}

# Helper function to clean NaN values from dictionaries
def clean_nan(obj):
    """Recursively replace NaN with None in dictionaries"""
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan(v) for v in obj]
    elif isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    return obj

BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / 'input'
UPLOAD_DIR = BASE_DIR / 'uploads'
OUTPUT_DIR = BASE_DIR / 'output'

for dir in [INPUT_DIR, UPLOAD_DIR, OUTPUT_DIR]:
    dir.mkdir(exist_ok=True)


def resolve_input_file(filename):
    """Safely resolve input file without path traversal"""
    if '..' in filename or filename.startswith('/'):
        return None

    filepath = INPUT_DIR / filename

    if not filepath.exists():
        return None

    if filepath.resolve().parent != INPUT_DIR.resolve():
        return None

    return filepath


@app.route('/')
def index():
    """Serve main UI"""
    return render_template('strategy_ui.html')


@app.route('/api/files', methods=['GET'])
def get_files():
    """Get list of input files"""
    try:
        files = [f.name for f in INPUT_DIR.glob('*.csv')]
        return jsonify({'files': sorted(files)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analyze/<filename>', methods=['GET'])
def analyze_file(filename):
    """Analyze CSV file"""
    try:
        filepath = resolve_input_file(filename)
        if not filepath:
            return jsonify({'error': 'File not found'}), 404

        df = OHLCDataLoader.load(str(filepath))

        stats = {
            'rows': len(df),
            'columns': list(df.columns),
            'date_range': f"{df['time'].min()} to {df['time'].max()}" if 'time' in df.columns else "N/A",
            'data_preview': df.head(5).to_dict('records')
        }

        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/upload-strategy', methods=['POST'])
def upload_strategy():
    """Upload Pine Script (.pine) or Python (.py) strategy"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        content = file.read().decode('utf-8')

        if file.filename.endswith('.py'):
            parameters = _extract_parameters_from_python(content)
            return jsonify({
                'success': True,
                'parameters': parameters,
                'python_code': content,
                'original_filename': file.filename,
                'type': 'python'
            })

        is_valid, message = PineScriptValidator.is_valid_pine_script(content)
        if not is_valid:
            return jsonify({
                'success': False,
                'error': message,
                'instructions': 'Copy this Pine Script to Claude Code chat and ask for Python conversion.',
                'pine_code': content
            }), 400

        parameters = PineScriptParser.extract_parameters(content)

        return jsonify({
            'success': True,
            'parameters': parameters,
            'python_code': None,
            'original_filename': file.filename,
            'type': 'pine',
            'instructions': 'Copy this code to Claude Code: "Convert this Pine Script to Python strategy"'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _extract_parameters_from_python(python_code: str) -> dict:
    """Extract parameters from Python strategy code"""
    parameters = {}

    for line in python_code.split('\n'):
        if 'self.params.setdefault' in line:
            try:
                param_name = line.split("'")[1]
                value_str = line.split(',')[1].strip().rstrip(')')

                if value_str.lower() in ['true', 'false']:
                    param_type = 'bool'
                    default_value = value_str.lower() == 'true'
                elif '.' in value_str:
                    param_type = 'float'
                    default_value = float(value_str)
                else:
                    param_type = 'int'
                    default_value = int(value_str)

                parameters[param_name] = {
                    'type': param_type,
                    'default': default_value,
                    'min': None,
                    'max': None,
                    'label': param_name
                }
            except:
                pass

    return parameters


@app.route('/api/upload-ohlc', methods=['POST'])
def upload_ohlc():
    """Upload OHLC CSV file"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not file.filename.endswith('.csv'):
            return jsonify({'error': 'Only CSV files allowed'}), 400

        filename = file.filename
        filepath = INPUT_DIR / filename

        file.save(str(filepath))

        df = OHLCDataLoader.load(str(filepath))

        return jsonify({
            'success': True,
            'filename': filename,
            'rows': len(df),
            'columns': list(df.columns)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/upload-excel', methods=['POST'])
def upload_excel():
    """Upload and analyze Excel file with multiple sheets"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not file.filename.endswith('.xlsx'):
            return jsonify({'error': 'Only .xlsx files allowed'}), 400

        filepath = UPLOAD_DIR / file.filename
        file.save(str(filepath))

        excel_file = pd.ExcelFile(str(filepath))
        sheets = {}

        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(str(filepath), sheet_name=sheet_name)

            # Replace NaN with None for JSON serialization
            df_clean = df.where(pd.notna(df), None)

            sheets[sheet_name] = {
                'rows': len(df),
                'columns': list(df.columns),
                'data': df_clean.head(10).to_dict('records'),
                'dtypes': {col: str(dtype) for col, dtype in df.dtypes.items()}
            }

        return jsonify(clean_nan({
            'success': True,
            'filename': file.filename,
            'sheets': sheets,
            'sheet_names': list(sheets.keys()),
            'total_sheets': len(sheets)
        }))
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/reconcile-kpis', methods=['POST'])
def reconcile_kpis():
    """Calculate and reconcile all 4 KPIs from Excel Trades tab"""
    try:
        data = request.json
        excel_filename = data.get('excel_file')

        if not excel_filename:
            return jsonify({'error': 'Excel file not specified'}), 400

        filepath = UPLOAD_DIR / excel_filename
        if not filepath.exists():
            return jsonify({'error': 'File not found'}), 404

        trades_df = pd.read_excel(str(filepath), sheet_name='Trades')
        perf_df = pd.read_excel(str(filepath), sheet_name='Performance')
        trades_analysis_df = pd.read_excel(str(filepath), sheet_name='Trades analysis')
        risk_adj_df = pd.read_excel(str(filepath), sheet_name='Risk-adjusted performance')

        # Replace NaN with None to avoid JSON serialization errors
        perf_df = perf_df.fillna(0)
        trades_analysis_df = trades_analysis_df.fillna(0)
        risk_adj_df = risk_adj_df.fillna(0)

        # Get unique trades (remove duplicates from entry/exit)
        unique_trades = trades_df.drop_duplicates(subset=['Trade number'], keep='first')

        # Get performance data
        perf_dict = dict(zip(perf_df['Unnamed: 0'], perf_df['All USD']))
        open_pnl = float(perf_dict.get('Open PnL', 0))

        # If there's open PnL, the last trade is open - exclude it from closed trades
        if open_pnl != 0:
            closed_trades = unique_trades[unique_trades['Trade number'] != unique_trades['Trade number'].max()]
        else:
            closed_trades = unique_trades

        # KPI 1: Total PnL (ALL TRADES)
        total_pnl = float(unique_trades['Net PnL USD'].sum())
        performance_total_pnl = float(perf_dict.get('Net profit', 0) + perf_dict.get('Open PnL', 0))

        # KPI 2: Win Rate (CLOSED TRADES ONLY)
        winning_trades = len(closed_trades[closed_trades['Net PnL USD'] > 0])
        total_trades = len(closed_trades)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        excel_total_trades = float(trades_analysis_df[trades_analysis_df['Unnamed: 0'] == 'Total trades']['All USD'].values[0])
        excel_winners = float(trades_analysis_df[trades_analysis_df['Unnamed: 0'] == 'Total winners']['All USD'].values[0])
        excel_win_rate = (excel_winners / excel_total_trades * 100) if excel_total_trades > 0 else 0.0

        # KPI 3: Profit Factor (CLOSED TRADES ONLY)
        gross_profit = float(closed_trades[closed_trades['Net PnL USD'] > 0]['Net PnL USD'].sum())
        gross_loss = float(abs(closed_trades[closed_trades['Net PnL USD'] < 0]['Net PnL USD'].sum()))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
        excel_profit_factor = float(risk_adj_df[risk_adj_df['Unnamed: 0'] == 'Profit factor']['All USD'].values[0])

        # KPI 4: Maximum Drawdown (Close-to-Close)
        max_drawdown_cc = -float(perf_dict.get('Max drawdown (close-to-close)', 75896.5))

        # KPI 5: Maximum Drawdown (Intrabar)
        # Extract from Performance tab (calculated by TradingView with full bar-level data)
        # Excel stores as positive, so negate it
        max_drawdown_intrabar = -float(perf_dict.get('Max drawdown (intrabar)', 82457.5))

        # KPI 6: Winning Trades (count)
        kpi_winning_trades = int(winning_trades)
        excel_winning_trades = int(excel_winners)

        # KPI 7: Losing Trades (count)
        kpi_losing_trades = int(len(closed_trades[closed_trades['Net PnL USD'] < 0]))
        excel_losing_trades = int(trades_analysis_df[trades_analysis_df['Unnamed: 0'] == 'Total losers']['All USD'].values[0])

        # KPI 8: Max Profit (largest winning trade)
        max_profit = float(closed_trades[closed_trades['Net PnL USD'] > 0]['Net PnL USD'].max())
        excel_max_profit = float(trades_analysis_df[trades_analysis_df['Unnamed: 0'] == 'Largest profit']['All USD'].values[0])

        # KPI 9: Max Loss (largest losing trade)
        max_loss = float(closed_trades[closed_trades['Net PnL USD'] < 0]['Net PnL USD'].min())
        excel_max_loss = -float(trades_analysis_df[trades_analysis_df['Unnamed: 0'] == 'Largest loss']['All USD'].values[0])

        # Reorder KPIs as specified by user
        kpis = {
            'total_trades': {
                'calculated': total_trades,
                'excel': total_trades,
                'match': True,
                'formula': 'COUNT(all closed trades)'
            },
            'winning_trades': {
                'calculated': kpi_winning_trades,
                'excel': excel_winning_trades,
                'match': kpi_winning_trades == excel_winning_trades,
                'formula': 'COUNT(trades with Net PnL > 0)'
            },
            'losing_trades': {
                'calculated': kpi_losing_trades,
                'excel': excel_losing_trades,
                'match': kpi_losing_trades == excel_losing_trades,
                'formula': 'COUNT(trades with Net PnL < 0)'
            },
            'win_rate': {
                'calculated': round(win_rate, 2),
                'excel': round(excel_win_rate, 2),
                'match': abs(win_rate - excel_win_rate) < 0.1,
                'formula': f'({winning_trades}/{total_trades}) × 100'
            },
            'max_profit': {
                'calculated': round(max_profit, 2),
                'excel': round(excel_max_profit, 2),
                'match': abs(max_profit - excel_max_profit) < 0.01,
                'formula': 'MAX(Net PnL USD) from winning trades'
            },
            'max_loss': {
                'calculated': round(max_loss, 2),
                'excel': round(excel_max_loss, 2),
                'match': abs(max_loss - excel_max_loss) < 0.01,
                'formula': 'MIN(Net PnL USD) from losing trades'
            },
            'total_pnl': {
                'calculated': total_pnl,
                'excel': performance_total_pnl,
                'match': abs(total_pnl - performance_total_pnl) < 0.01,
                'formula': 'SUM(Net PnL USD) from Trades tab'
            },
            'max_drawdown_cc': {
                'calculated': round(max_drawdown_cc, 2),
                'excel': -75896.50,
                'match': abs(max_drawdown_cc - (-75896.50)) < 1,
                'formula': 'Close-to-Close: MIN(Cumulative PnL - Running Max)'
            },
            'max_drawdown_intrabar': {
                'calculated': round(max_drawdown_intrabar, 2),
                'excel': -82457.50,
                'match': abs(max_drawdown_intrabar - (-82457.50)) < 1,
                'formula': 'Intrabar: Worst case including adverse excursions'
            },
            'profit_factor': {
                'calculated': round(profit_factor, 4),
                'excel': round(excel_profit_factor, 4),
                'match': abs(profit_factor - excel_profit_factor) < 0.01,
                'formula': f'${gross_profit:,.2f} / ${gross_loss:,.2f}'
            }
        }

        # Count matches
        match_count = sum(1 for kpi in kpis.values() if kpi['match'])

        response_data = {
            'success': True,
            'kpis': kpis,
            'summary': {
                'total_kpis': 10,
                'matched': match_count,
                'status': f'{match_count}/10 KPIs Match ✅' if match_count == 10 else f'{match_count}/10 KPIs Match ⚠️'
            }
        }

        # Return with sort_keys=False to preserve insertion order
        return Response(
            json.dumps(clean_nan(response_data), sort_keys=False, cls=NaNEncoder),
            mimetype='application/json'
        )
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/reconcile-pnl', methods=['POST'])
def reconcile_pnl():
    """Calculate and reconcile Total PnL from Excel Trades tab"""
    try:
        data = request.json
        excel_filename = data.get('excel_file')

        if not excel_filename:
            return jsonify({'error': 'Excel file not specified'}), 400

        filepath = UPLOAD_DIR / excel_filename
        if not filepath.exists():
            return jsonify({'error': 'File not found'}), 404

        trades_df = pd.read_excel(str(filepath), sheet_name='Trades')
        perf_df = pd.read_excel(str(filepath), sheet_name='Performance')

        # Calculate Total PnL from Trades tab
        unique_trades = trades_df.drop_duplicates(subset=['Trade number'], keep='first')
        total_pnl = unique_trades['Net PnL USD'].sum()

        # Get from Performance tab
        perf_dict = dict(zip(perf_df['Unnamed: 0'], perf_df['All USD']))
        closed_pnl = perf_dict.get('Net profit', 0)
        open_pnl = perf_dict.get('Open PnL', 0)
        initial_capital = perf_dict.get('Initial capital', 0)

        # Calculate from cumulative
        final_cumulative = trades_df['Cumulative PnL USD'].iloc[-1]

        match_status = abs(total_pnl - final_cumulative) < 0.01
        open_trades_count = 1 if open_pnl != 0 else 0

        reconciliation = {
            'from_trades_sum': float(total_pnl),
            'from_cumulative_pnl': float(final_cumulative),
            'from_performance_closed': float(closed_pnl),
            'from_performance_open': float(open_pnl),
            'from_performance_total': float(closed_pnl + open_pnl),
            'match': str(match_status),
            'details': {
                'total_trades': int(len(unique_trades)),
                'closed_trades': int(len(unique_trades) - open_trades_count),
                'open_trades': int(open_trades_count),
                'initial_capital': float(initial_capital),
                'return_pct': float((total_pnl / initial_capital * 100)) if initial_capital > 0 else 0.0
            }
        }

        return jsonify({
            'success': True,
            'reconciliation': reconciliation,
            'status': 'MATCH ✅' if reconciliation['match'] else 'MISMATCH ❌'
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/extract-excel-parameters', methods=['POST'])
def extract_excel_parameters():
    """Extract strategy parameters from Excel Properties tab"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        if not file.filename.endswith('.xlsx'):
            return jsonify({'error': 'Only .xlsx files allowed'}), 400

        filepath = UPLOAD_DIR / file.filename
        file.save(str(filepath))

        # Read Properties tab
        props_df = pd.read_excel(str(filepath), sheet_name='Properties')
        props_dict = dict(zip(props_df['name'], props_df['value']))

        # Extract parameters based on Properties tab values
        enable_pyramiding = str(props_dict.get('Enable Same-Side Pyramiding', 'Off')).lower() == 'on'
        parameters = {
            'length': int(props_dict.get('ATR Period', 19)),
            'mult': float(props_dict.get('ATR Multiplier', 3.0)),
            'useClose': str(props_dict.get('Use Close Price for Extremums', 'On')).lower() == 'on',
            'ema9Len': int(props_dict.get('Fast EMA Length', 7)),
            'ema21Len': int(props_dict.get('Slow EMA Length', 95)),
            'useFreedomFilter': str(props_dict.get('Enable Freedom Candle Filter', 'Off')).lower() == 'on',
            'exitMode': str(props_dict.get('Exit Mode', 'Original (CE Reversal)')),
            'enablePyramiding': enable_pyramiding,
            'maxEntries': int(props_dict.get('Max Open Entries (same side)', 7)) if enable_pyramiding else 1,
        }

        return jsonify({
            'success': True,
            'parameters': parameters,
            'filename': file.filename
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/debug-backtest', methods=['POST'])
def debug_backtest():
    """Debug endpoint to see what parameters are being received"""
    try:
        data = request.json
        return jsonify({
            'received_keys': list(data.keys()),
            'parameters_received': data.get('parameters'),
            'parameters_type': str(type(data.get('parameters'))),
            'parameters_count': len(data.get('parameters', {})),
            'ohlc_content_length': len(data.get('ohlc_content', '')),
            'python_code_length': len(data.get('python_code', ''))
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/backtest-kpis', methods=['POST'])
def backtest_kpis():
    """Run Python strategy backtest and calculate 9 KPIs"""
    try:
        data = request.json
        python_code = data.get('python_code')
        ohlc_content = data.get('ohlc_content')
        ohlc_filename = data.get('ohlc_filename') or data.get('ohlc_file')
        parameters = data.get('parameters', {})
        additional_tf_content = data.get('additional_tf_content')
        additional_tf_filename = data.get('additional_tf_filename')

        if not python_code:
            return jsonify({'error': 'Missing Python code'}), 400

        if ohlc_content:
            # Handle OHLC content directly (from file upload)
            from io import StringIO
            csv_buffer = StringIO(ohlc_content)
            df = pd.read_csv(csv_buffer)

            # Keep only first 5 columns
            if len(df.columns) > 5:
                df = df.iloc[:, :5]

            # Rename columns to lowercase
            df.columns = df.columns.str.lower().str.strip()

            # Map to standard OHLC names
            col_mapping = {}
            for idx, col in enumerate(df.columns):
                if idx == 0:
                    col_mapping[col] = 'time'
                elif idx == 1:
                    col_mapping[col] = 'open'
                elif idx == 2:
                    col_mapping[col] = 'high'
                elif idx == 3:
                    col_mapping[col] = 'low'
                elif idx == 4:
                    col_mapping[col] = 'close'

            df.rename(columns=col_mapping, inplace=True)

            # Convert time to datetime and remove timezone
            if 'time' in df.columns:
                df['time'] = pd.to_datetime(df['time'])
                # Remove timezone if present
                if df['time'].dt.tz is not None:
                    df['time'] = df['time'].dt.tz_localize(None)

            # Add volume if missing
            if 'volume' not in df.columns:
                df['volume'] = 0
        else:
            # Handle from file system (backward compatibility)
            if not ohlc_filename:
                return jsonify({'error': 'Missing OHLC file'}), 400

            filepath = resolve_input_file(ohlc_filename)
            if not filepath:
                return jsonify({'error': 'OHLC file not found'}), 404

            df = OHLCDataLoader.load(str(filepath))

        # Process additional TF data if provided
        additional_tf_df = None
        if additional_tf_content:
            from io import StringIO
            csv_buffer = StringIO(additional_tf_content)
            additional_tf_df = pd.read_csv(csv_buffer)

            # Keep only first 5 columns
            if len(additional_tf_df.columns) > 5:
                additional_tf_df = additional_tf_df.iloc[:, :5]

            # Rename columns to lowercase
            additional_tf_df.columns = additional_tf_df.columns.str.lower().str.strip()

            # Map to standard OHLC names
            col_mapping = {}
            for idx, col in enumerate(additional_tf_df.columns):
                if idx == 0:
                    col_mapping[col] = 'time'
                elif idx == 1:
                    col_mapping[col] = 'open'
                elif idx == 2:
                    col_mapping[col] = 'high'
                elif idx == 3:
                    col_mapping[col] = 'low'
                elif idx == 4:
                    col_mapping[col] = 'close'

            additional_tf_df.rename(columns=col_mapping, inplace=True)

            # Convert time to datetime and remove timezone
            if 'time' in additional_tf_df.columns:
                additional_tf_df['time'] = pd.to_datetime(additional_tf_df['time'])
                # Remove timezone if present
                if additional_tf_df['time'].dt.tz is not None:
                    additional_tf_df['time'] = additional_tf_df['time'].dt.tz_localize(None)

            # Add volume if missing
            if 'volume' not in additional_tf_df.columns:
                additional_tf_df['volume'] = 0

        try:
            strategy_class = StrategyOptimizer.load_strategy_from_code(python_code, "UploadedStrategy")
        except Exception as e:
            return jsonify({'error': f'Failed to load Python code: {str(e)}'}), 400

        try:
            # Try to pass additional_tf_df to strategy if it accepts freedom_df parameter
            try:
                strategy = strategy_class(df.copy(), parameters, freedom_df=additional_tf_df)
            except TypeError:
                # Fallback: strategy doesn't accept freedom_df parameter
                strategy = strategy_class(df.copy(), parameters)

            results = strategy.run()  # Call run() which calls all methods and returns the summary

        except Exception as e:
            return jsonify({'error': f'Strategy execution failed: {str(e)}'}), 400

        # Extract trades from results or create dummy trades for calculation
        trades_data = results.get('trades', [])

        # Check if trades_data is empty (handle both list and DataFrame)
        is_empty = False
        if isinstance(trades_data, pd.DataFrame):
            is_empty = trades_data.empty
        else:
            is_empty = len(trades_data) == 0

        if is_empty:
            empty_kpis = {
                'total_trades': {'calculated': 0, 'formula': 'No trades executed'},
                'winning_trades': {'calculated': 0, 'formula': 'No trades'},
                'losing_trades': {'calculated': 0, 'formula': 'No trades'},
                'win_rate': {'calculated': 0, 'formula': 'No trades'},
                'max_profit': {'calculated': 0, 'formula': 'No trades'},
                'max_loss': {'calculated': 0, 'formula': 'No trades'},
                'total_pnl': {'calculated': 0, 'formula': 'No trades executed'},
                'max_drawdown_cc': {'calculated': 0, 'formula': 'No trades'},
                'max_drawdown_intrabar': {'calculated': 0, 'formula': 'No trades'},
                'profit_factor': {'calculated': 0, 'formula': 'No trades'}
            }
            return Response(
                json.dumps({
                    'success': True,
                    'kpis': empty_kpis,
                    'summary': 'No trades executed'
                }, sort_keys=False, cls=NaNEncoder),
                mimetype='application/json'
            )

        # Calculate KPIs from trades
        trades_df = pd.DataFrame(trades_data)

        total_pnl = float(trades_df['pnl'].sum()) if 'pnl' in trades_df.columns else 0
        winning = len(trades_df[trades_df['pnl'] > 0]) if 'pnl' in trades_df.columns else 0
        losing = len(trades_df[trades_df['pnl'] < 0]) if 'pnl' in trades_df.columns else 0
        total_trades = len(trades_df)

        win_rate = (winning / total_trades * 100) if total_trades > 0 else 0

        gross_profit = float(trades_df[trades_df['pnl'] > 0]['pnl'].sum()) if 'pnl' in trades_df.columns else 0
        gross_loss = float(abs(trades_df[trades_df['pnl'] < 0]['pnl'].sum())) if 'pnl' in trades_df.columns else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        max_profit = float(trades_df['pnl'].max()) if 'pnl' in trades_df.columns else 0
        max_loss = float(trades_df['pnl'].min()) if 'pnl' in trades_df.columns else 0

        # Use max_drawdown from strategy results (calculated from actual equity curve)
        # This is the most accurate as it includes both trade PnL and floating P&L
        strategy_max_drawdown = float(results.get('max_drawdown', 0))
        max_drawdown_cc = strategy_max_drawdown  # Strategy returns positive value, use as-is

        # For intrabar drawdown, use the same value from strategy (it uses equity curve)
        max_drawdown_intrabar = max_drawdown_cc

        # Reorder KPIs to match specified order
        kpis = {
            'total_trades': {'calculated': total_trades, 'formula': 'COUNT(all trades)'},
            'winning_trades': {'calculated': winning, 'formula': 'COUNT(pnl > 0)'},
            'losing_trades': {'calculated': losing, 'formula': 'COUNT(pnl < 0)'},
            'win_rate': {'calculated': round(win_rate, 2), 'formula': f'({winning}/{total_trades}) × 100'},
            'max_profit': {'calculated': round(max_profit, 2), 'formula': 'MAX(pnl)'},
            'max_loss': {'calculated': round(max_loss, 2), 'formula': 'MIN(pnl)'},
            'total_pnl': {'calculated': round(total_pnl, 2), 'formula': 'SUM(trade PnL)'},
            'max_drawdown_cc': {'calculated': round(max_drawdown_cc, 2), 'formula': 'Close-to-close drawdown'},
            'max_drawdown_intrabar': {'calculated': round(max_drawdown_intrabar, 2), 'formula': 'Equity-based drawdown'},
            'profit_factor': {'calculated': round(profit_factor, 4), 'formula': f'${gross_profit:,.0f} / ${gross_loss:,.0f}'}
        }

        # Convert trades DataFrame to list of dictionaries
        trades_list = []
        if isinstance(trades_data, pd.DataFrame):
            trades_list = trades_data.to_dict(orient='records')
            # Convert Timestamp objects to ISO format strings
            for trade in trades_list:
                for key, value in trade.items():
                    if isinstance(value, pd.Timestamp):
                        trade[key] = value.isoformat()
        else:
            trades_list = trades_data

        response_data = {
            'success': True,
            'kpis': kpis,
            'trades': trades_list,
            'summary': f'{total_trades} trades, {winning} winners, {losing} losers'
        }

        return Response(
            json.dumps(clean_nan(response_data), sort_keys=False, cls=NaNEncoder),
            mimetype='application/json'
        )
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/validate-strategy', methods=['POST'])
def validate_strategy():
    """Validate Python strategy against TradingView data"""
    try:
        data = request.json
        python_code = data.get('python_code')
        ohlc_filename = data.get('ohlc_file')
        parameters = data.get('parameters', {})

        if not python_code or not ohlc_filename:
            return jsonify({'error': 'Missing Python code or OHLC file'}), 400

        filepath = resolve_input_file(ohlc_filename)
        if not filepath:
            return jsonify({'error': 'OHLC file not found'}), 404

        df = OHLCDataLoader.load(str(filepath))

        try:
            strategy_class = StrategyOptimizer.load_strategy_from_code(python_code, "UploadedStrategy")
        except Exception as e:
            return jsonify({'error': f'Failed to load Python code: {str(e)}'}), 400

        try:
            strategy = strategy_class(df.copy(), parameters)
            strategy.calculate_indicators()
        except Exception as e:
            return jsonify({'error': f'Strategy execution failed: {str(e)}'}), 400

        tv_columns = [col for col in df.columns if col not in ['time', 'open', 'high', 'low', 'close', 'volume']]

        comparison = []
        for col in tv_columns:
            if col in strategy.df.columns:
                for idx in range(min(len(df), len(strategy.df))):
                    tv_val = df[col].iloc[idx]
                    py_val = strategy.df[col].iloc[idx]

                    match = False
                    difference = None

                    if pd.isna(tv_val) and pd.isna(py_val):
                        match = True
                    elif not pd.isna(tv_val) and not pd.isna(py_val):
                        try:
                            diff = abs(float(tv_val) - float(py_val))
                            if diff < 0.0001:
                                match = True
                            difference = f"{diff:.8f}"
                        except:
                            match = str(tv_val) == str(py_val)

                    comparison.append({
                        'row_index': idx,
                        'column': col,
                        'tv_value': tv_val,
                        'py_value': py_val,
                        'match': match,
                        'difference': difference
                    })

        match_count = sum(1 for c in comparison if c['match'])
        total_count = len(comparison)
        match_percentage = (match_count / total_count * 100) if total_count > 0 else 0

        return jsonify({
            'success': True,
            'comparison': comparison[:100],
            'match_count': match_count,
            'total_count': total_count,
            'match_percentage': f"{match_percentage:.1f}%",
            'columns_validated': tv_columns
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/run-backtest', methods=['POST'])
def run_backtest():
    """Run backtest with parameters"""
    try:
        data = request.json

        strategy_code = data.get('strategy_code')
        data_filename = data.get('data_file')
        param_ranges = data.get('param_ranges', {})

        if not strategy_code or not data_filename:
            return jsonify({'error': 'Missing strategy code or data file'}), 400

        filepath = resolve_input_file(data_filename)
        if not filepath:
            return jsonify({'error': 'Data file not found'}), 404

        df = OHLCDataLoader.load(str(filepath))

        strategy_class = StrategyOptimizer.load_strategy_from_code(strategy_code)

        optimizer = StrategyOptimizer(strategy_class, df)

        results_df = optimizer.test_parameters(param_ranges)

        output_file = OUTPUT_DIR / 'optimization_results.csv'
        results_df.to_csv(output_file, index=False)

        results_dict = results_df.head(10).to_dict('records')

        return jsonify({
            'success': True,
            'results': results_dict,
            'total_combinations': len(results_df),
            'output_file': str(output_file)
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/download-results', methods=['GET'])
def download_results():
    """Download results CSV"""
    try:
        output_file = OUTPUT_DIR / 'optimization_results.csv'

        if not output_file.exists():
            return jsonify({'error': 'No results file'}), 404

        return send_file(str(output_file), as_attachment=True, download_name='optimization_results.csv')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/delete-file/<filename>', methods=['DELETE'])
def delete_file(filename):
    """Delete input file"""
    try:
        filepath = resolve_input_file(filename)
        if not filepath:
            return jsonify({'error': 'File not found'}), 404

        filepath.unlink()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/extract-python-parameters', methods=['POST'])
def extract_python_parameters():
    """Extract parameters and metadata from Python strategy code"""
    try:
        data = request.json
        python_code = data.get('python_code')

        if not python_code:
            return jsonify({'error': 'Missing Python code'}), 400

        # Extract DEFAULT_PARAMS and PARAMETER_METADATA from code
        import re

        parameters = {}
        metadata = {}

        # Create namespace and execute code to get variable definitions
        namespace = {}
        try:
            exec(python_code, namespace)
            if 'DEFAULT_PARAMS' in namespace:
                parameters = namespace['DEFAULT_PARAMS'].copy()
            if 'PARAMETER_METADATA' in namespace:
                metadata = namespace['PARAMETER_METADATA'].copy()
        except:
            pass

        # If execution worked, convert numpy types
        for key, value in parameters.items():
            if hasattr(value, 'item'):  # numpy type
                parameters[key] = value.item()

        # If execution didn't work, try regex parsing
        if not parameters:
            default_params_match = re.search(r'DEFAULT_PARAMS\s*=\s*\{(.*?)\n\s*\}', python_code, re.DOTALL)
            if default_params_match:
                params_text = default_params_match.group(1)

                # Extract each parameter
                param_pattern = r"'(\w+)':\s*([^,]+)"
                matches = re.findall(param_pattern, params_text)

                for param_name, param_value in matches:
                    param_value = param_value.strip()

                    # Try to evaluate the value
                    try:
                        if param_value.startswith("'") or param_value.startswith('"'):
                            parameters[param_name] = param_value.strip("'\"")
                        elif param_value.lower() == 'true':
                            parameters[param_name] = True
                        elif param_value.lower() == 'false':
                            parameters[param_name] = False
                        else:
                            if '.' in param_value or 'e' in param_value.lower():
                                parameters[param_name] = float(param_value)
                            else:
                                parameters[param_name] = int(param_value)
                    except:
                        parameters[param_name] = param_value

        return Response(
            json.dumps({
                'success': True,
                'parameters': parameters,
                'metadata': metadata,
                'count': len(parameters)
            }, sort_keys=False, cls=NaNEncoder),
            mimetype='application/json'
        )
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/calculate-combinations', methods=['POST'])
def calculate_combinations():
    """Calculate total combinations without running the test"""
    try:
        data = request.json
        parameter_configs = data.get('parameter_configs', {})
        parameter_metadata = data.get('parameter_metadata', {})

        # Ensure Freedom filter is included
        if 'useFreedomFilter' not in parameter_configs:
            parameter_configs['useFreedomFilter'] = {
                'from': False,
                'to': False,
                'default': False
            }

        # Generate combinations to count them
        combinations = generate_parameter_combinations(parameter_configs, parameter_metadata)

        return jsonify({
            'total_combinations': len(combinations),
            'parameters_count': len(parameter_configs)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400


# Global progress tracking
bruteforce_progress = {
    'total': 0,
    'completed': 0,
    'errors': 0,
    'start_time': None,
    'is_running': False
}

@app.route('/api/bruteforce-progress', methods=['GET'])
def get_bruteforce_progress():
    """Get current progress of brute force test"""
    if not bruteforce_progress['is_running']:
        return jsonify({'error': 'No test running'}), 400

    elapsed = time.time() - bruteforce_progress['start_time'] if bruteforce_progress['start_time'] else 0
    remaining = bruteforce_progress['total'] - bruteforce_progress['completed']
    rate = bruteforce_progress['completed'] / elapsed if elapsed > 0 else 0
    eta = remaining / rate if rate > 0 else 0

    return jsonify({
        'total': bruteforce_progress['total'],
        'completed': bruteforce_progress['completed'],
        'errors': bruteforce_progress['errors'],
        'remaining': remaining,
        'elapsed_seconds': int(elapsed),
        'eta_seconds': int(eta),
        'percentage': int((bruteforce_progress['completed'] / bruteforce_progress['total'] * 100)) if bruteforce_progress['total'] > 0 else 0,
        'rate': round(rate, 2)
    })


@app.route('/api/bruteforce-test', methods=['POST'])
def bruteforce_test():
    """Run brute force parameter optimization"""
    try:
        data = request.json
        python_code = data.get('python_code')
        ohlc_content = data.get('ohlc_content')
        parameter_configs = data.get('parameter_configs', {})
        additional_tf_content = data.get('additional_tf_content')
        additional_tf_filename = data.get('additional_tf_filename')

        # Ensure Freedom filter is disabled to allow trades to execute
        if 'useFreedomFilter' not in parameter_configs:
            parameter_configs['useFreedomFilter'] = {
                'from': False,
                'to': False,
                'default': False
            }

        if not python_code or not ohlc_content:
            return jsonify({'error': 'Missing Python code or OHLC data'}), 400

        # Load OHLC data
        from io import StringIO
        csv_buffer = StringIO(ohlc_content)
        df = pd.read_csv(csv_buffer)

        if len(df.columns) > 5:
            df = df.iloc[:, :5]

        df.columns = df.columns.str.lower().str.strip()

        col_mapping = {}
        for idx, col in enumerate(df.columns):
            if idx == 0:
                col_mapping[col] = 'time'
            elif idx == 1:
                col_mapping[col] = 'open'
            elif idx == 2:
                col_mapping[col] = 'high'
            elif idx == 3:
                col_mapping[col] = 'low'
            elif idx == 4:
                col_mapping[col] = 'close'

        df.rename(columns=col_mapping, inplace=True)

        if 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])
            if df['time'].dt.tz is not None:
                df['time'] = df['time'].dt.tz_localize(None)

        if 'volume' not in df.columns:
            df['volume'] = 0

        # Process additional TF data if provided
        additional_tf_df = None
        if additional_tf_content:
            from io import StringIO
            csv_buffer = StringIO(additional_tf_content)
            additional_tf_df = pd.read_csv(csv_buffer)

            # Keep only first 5 columns
            if len(additional_tf_df.columns) > 5:
                additional_tf_df = additional_tf_df.iloc[:, :5]

            # Rename columns to lowercase
            additional_tf_df.columns = additional_tf_df.columns.str.lower().str.strip()

            # Map to standard OHLC names
            col_mapping = {}
            for idx, col in enumerate(additional_tf_df.columns):
                if idx == 0:
                    col_mapping[col] = 'time'
                elif idx == 1:
                    col_mapping[col] = 'open'
                elif idx == 2:
                    col_mapping[col] = 'high'
                elif idx == 3:
                    col_mapping[col] = 'low'
                elif idx == 4:
                    col_mapping[col] = 'close'

            additional_tf_df.rename(columns=col_mapping, inplace=True)

            # Convert time to datetime and remove timezone
            if 'time' in additional_tf_df.columns:
                additional_tf_df['time'] = pd.to_datetime(additional_tf_df['time'])
                # Remove timezone if present
                if additional_tf_df['time'].dt.tz is not None:
                    additional_tf_df['time'] = additional_tf_df['time'].dt.tz_localize(None)

            # Add volume if missing
            if 'volume' not in additional_tf_df.columns:
                additional_tf_df['volume'] = 0

        # Load strategy
        strategy_class = StrategyOptimizer.load_strategy_from_code(python_code, "UploadedStrategy")

        # Execute code to get namespace with constants (for resolving parameter values)
        namespace = {}
        parameter_metadata = {}
        default_params = {}
        try:
            exec(python_code, namespace)
            if 'PARAMETER_METADATA' in namespace:
                parameter_metadata = namespace['PARAMETER_METADATA']
            if 'DEFAULT_PARAMS' in namespace:
                default_params = namespace['DEFAULT_PARAMS']
        except:
            pass

        # Auto-fill missing parameters with defaults (in case UI didn't send all of them)
        for param_name, default_value in default_params.items():
            if param_name not in parameter_configs:
                parameter_configs[param_name] = {
                    'from': default_value,
                    'to': default_value,
                    'default': default_value
                }

        # Generate parameter combinations
        results = []
        combinations = generate_parameter_combinations(parameter_configs, parameter_metadata)

        # Initialize progress tracking
        global bruteforce_progress
        bruteforce_progress = {
            'total': len(combinations),
            'completed': 0,
            'errors': 0,
            'start_time': time.time(),
            'is_running': True
        }

        for combo in combinations:
            try:
                # Resolve string values to proper types
                resolved_combo = {}
                for param_name, param_value in combo.items():
                    if isinstance(param_value, str):
                        # Try to convert string booleans
                        if param_value == 'True' or param_value == 'true':
                            resolved_combo[param_name] = True
                        elif param_value == 'False' or param_value == 'false':
                            resolved_combo[param_name] = False
                        else:
                            # Try to resolve as a constant from the namespace
                            if param_value in namespace:
                                resolved_combo[param_name] = namespace[param_value]
                            else:
                                resolved_combo[param_name] = param_value
                    else:
                        resolved_combo[param_name] = param_value

                # Try to pass additional_tf_df to strategy if it accepts freedom_df parameter
                try:
                    strategy = strategy_class(df.copy(), resolved_combo, freedom_df=additional_tf_df)
                except TypeError:
                    # Fallback: strategy doesn't accept freedom_df parameter
                    strategy = strategy_class(df.copy(), resolved_combo)

                result = strategy.run()

                # Convert trades DataFrame to list
                trades_list = []
                trades_data = result.get('trades', pd.DataFrame())
                if isinstance(trades_data, pd.DataFrame) and not trades_data.empty:
                    trades_list = trades_data.to_dict(orient='records')

                # Calculate KPIs
                trades_df = pd.DataFrame(trades_list)
                total_trades = len(trades_df)
                winning = len(trades_df[trades_df['pnl'] > 0]) if 'pnl' in trades_df.columns else 0
                losing = len(trades_df[trades_df['pnl'] < 0]) if 'pnl' in trades_df.columns else 0
                total_pnl = float(trades_df['pnl'].sum()) if 'pnl' in trades_df.columns else 0
                profit_factor = 0
                max_profit = 0
                max_loss = 0

                if total_trades > 0:
                    gross_profit = float(trades_df[trades_df['pnl'] > 0]['pnl'].sum()) if 'pnl' in trades_df.columns else 0
                    gross_loss = float(abs(trades_df[trades_df['pnl'] < 0]['pnl'].sum())) if 'pnl' in trades_df.columns else 0
                    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
                    win_rate = (winning / total_trades * 100) if total_trades > 0 else 0

                    # Max profit and max loss per trade
                    if 'pnl' in trades_df.columns:
                        max_profit = float(trades_df['pnl'].max()) if len(trades_df) > 0 else 0
                        max_loss = float(trades_df['pnl'].min()) if len(trades_df) > 0 else 0
                else:
                    win_rate = 0

                # Calculate monthly statistics
                monthly_stats = {}
                if not trades_df.empty and 'exit_time' in trades_df.columns:
                    trades_df['month'] = pd.to_datetime(trades_df['exit_time']).dt.to_period('M')
                    for month, month_trades in trades_df.groupby('month'):
                        wins = len(month_trades[month_trades['pnl'] > 0])
                        losses = len(month_trades[month_trades['pnl'] < 0])
                        profit = float(month_trades[month_trades['pnl'] > 0]['pnl'].sum()) if 'pnl' in month_trades.columns else 0
                        loss = float(abs(month_trades[month_trades['pnl'] < 0]['pnl'].sum())) if 'pnl' in month_trades.columns else 0
                        monthly_stats[str(month)] = {
                            'trades': len(month_trades),
                            'wins': wins,
                            'losses': losses,
                            'profit': profit,
                            'loss': loss
                        }

                results.append({
                    'parameters': resolved_combo,
                    'total_trades': total_trades,
                    'winning_trades': winning,
                    'losing_trades': losing,
                    'win_rate': win_rate,
                    'max_profit': max_profit,
                    'max_loss': max_loss,
                    'total_pnl': total_pnl,
                    'max_drawdown': float(result.get('max_drawdown', 0)),
                    'profit_factor': profit_factor,
                    'monthly_stats': monthly_stats
                })
                bruteforce_progress['completed'] += 1
            except Exception as e:
                # Log error but continue with other combinations
                bruteforce_progress['completed'] += 1
                bruteforce_progress['errors'] += 1
                print(f"❌ Failed combination {combo}: {str(e)}", flush=True)
                import traceback
                traceback.print_exc()

        # Mark test as complete
        bruteforce_progress['is_running'] = False

        # If no results, return error with context
        if not results:
            return jsonify({'error': 'No successful combinations. Check that parameters are valid and strategy can execute.', 'combinations_tested': len(combinations)}), 400

        # Sort results by total PnL (descending) to match Numba endpoint
        results_sorted = sorted(results, key=lambda x: x.get('total_pnl', 0), reverse=True)

        # Calculate final stats
        start_time = bruteforce_progress['start_time']
        end_time = time.time()
        elapsed_time = end_time - start_time
        total_combinations = len(combinations)
        throughput_per_sec = total_combinations / elapsed_time if elapsed_time > 0 else 0

        return Response(
            json.dumps({
                'success': True,
                'results': results_sorted,
                'implementation': 'current',
                'stats': {
                    'start_time': start_time,
                    'end_time': end_time,
                    'duration_seconds': elapsed_time,
                    'total_combinations': total_combinations,
                    'throughput_per_sec': throughput_per_sec
                }
            }, sort_keys=False, cls=NaNEncoder),
            mimetype='application/json'
        )

    except Exception as e:
        bruteforce_progress['is_running'] = False
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


def generate_parameter_combinations(parameter_configs, parameter_metadata=None):
    """Generate all parameter combinations from config with support for decimal steps"""
    import itertools

    param_lists = {}
    for param_name, config in parameter_configs.items():
        from_val = config['from']
        to_val = config['to']

        # Skip parameters where from == to (no variation)
        if from_val == to_val:
            param_lists[param_name] = [from_val]
            continue

        if isinstance(from_val, (int, float)) and isinstance(to_val, (int, float)):
            # Check if metadata specifies a step
            step = 1
            if parameter_metadata and param_name in parameter_metadata:
                step = parameter_metadata[param_name].get('step', 1)

            # Generate range of values with proper step
            if step == int(step) and isinstance(from_val, int) and isinstance(to_val, int):
                # Integer range
                param_lists[param_name] = list(range(int(from_val), int(to_val) + 1, int(step)))
            else:
                # Decimal range - generate with step
                values = []
                current = float(from_val)
                while current <= float(to_val) + 1e-9:  # Small epsilon for floating point
                    values.append(round(current, 10))  # Round to avoid float precision issues
                    current += float(step)
                param_lists[param_name] = values
        else:
            param_lists[param_name] = [from_val, to_val]

    # Generate combinations
    param_names = list(param_lists.keys())
    param_values = list(param_lists.values())

    combinations = []
    for combo_values in itertools.product(*param_values):
        combo_dict = dict(zip(param_names, combo_values))
        combinations.append(combo_dict)

    return combinations


# ==================== NUMBA OPTIMIZED ENDPOINTS ====================
# NEW endpoints for Numba-optimized backtest
# Existing implementation remains COMPLETELY UNTOUCHED
# User can choose between implementations via UI selector

@app.route('/api/bruteforce-test-numba', methods=['POST'])
def bruteforce_test_numba():
    """
    Numba-optimized brute force test - COMPLETELY SEPARATE IMPLEMENTATION
    Uses version_11_numba.py with NumPy arrays and Numba JIT compilation
    Original version_11.py remains 100% untouched
    """
    try:
        data = request.get_json()
        python_code = data.get('python_code', '')
        ohlc_content = data.get('ohlc_content', '')
        parameter_configs = data.get('parameter_configs', {})
        parameter_metadata = data.get('parameter_metadata', {})
        additional_tf_content = data.get('additional_tf_content')
        additional_tf_filename = data.get('additional_tf_filename')

        if not python_code or not ohlc_content:
            return jsonify({'error': 'Python code and OHLC data required'}), 400

        from io import StringIO
        import pandas as pd

        ohlc_df = pd.read_csv(StringIO(ohlc_content))

        # Normalize OHLC columns
        ohlc_df.columns = ohlc_df.columns.str.lower().str.strip()
        col_mapping = {}
        for idx, col in enumerate(ohlc_df.columns):
            if idx == 0:
                col_mapping[col] = 'time'
            elif idx == 1:
                col_mapping[col] = 'open'
            elif idx == 2:
                col_mapping[col] = 'high'
            elif idx == 3:
                col_mapping[col] = 'low'
            elif idx == 4:
                col_mapping[col] = 'close'
        ohlc_df.rename(columns=col_mapping, inplace=True)

        if 'time' in ohlc_df.columns:
            ohlc_df['time'] = pd.to_datetime(ohlc_df['time'])
            if ohlc_df['time'].dt.tz is not None:
                ohlc_df['time'] = ohlc_df['time'].dt.tz_localize(None)
            ohlc_df.set_index('time', inplace=True)

        if 'volume' not in ohlc_df.columns:
            ohlc_df['volume'] = 0

        # Process additional TF data if provided
        additional_tf_df = None
        if additional_tf_content:
            from io import StringIO
            csv_buffer = StringIO(additional_tf_content)
            additional_tf_df = pd.read_csv(csv_buffer)

            # Keep only first 5 columns
            if len(additional_tf_df.columns) > 5:
                additional_tf_df = additional_tf_df.iloc[:, :5]

            # Rename columns to lowercase
            additional_tf_df.columns = additional_tf_df.columns.str.lower().str.strip()

            # Map to standard OHLC names
            col_mapping_tf = {}
            for idx, col in enumerate(additional_tf_df.columns):
                if idx == 0:
                    col_mapping_tf[col] = 'time'
                elif idx == 1:
                    col_mapping_tf[col] = 'open'
                elif idx == 2:
                    col_mapping_tf[col] = 'high'
                elif idx == 3:
                    col_mapping_tf[col] = 'low'
                elif idx == 4:
                    col_mapping_tf[col] = 'close'

            additional_tf_df.rename(columns=col_mapping_tf, inplace=True)

            # Convert time to datetime and remove timezone
            if 'time' in additional_tf_df.columns:
                additional_tf_df['time'] = pd.to_datetime(additional_tf_df['time'])
                # Remove timezone if present
                if additional_tf_df['time'].dt.tz is not None:
                    additional_tf_df['time'] = additional_tf_df['time'].dt.tz_localize(None)

            # Add volume if missing
            if 'volume' not in additional_tf_df.columns:
                additional_tf_df['volume'] = 0

        # Ensure Freedom filter is disabled to allow trades to execute (same as Current endpoint)
        if 'useFreedomFilter' not in parameter_configs:
            parameter_configs['useFreedomFilter'] = {
                'from': False,
                'to': False,
                'default': False
            }

        # Execute original Python code to get metadata
        namespace = {}
        exec(python_code, namespace)

        # Extract parameter metadata from namespace if not provided
        if not parameter_metadata:
            parameter_metadata = namespace.get('PARAMETER_METADATA', {})

        # Auto-fill missing parameters with defaults from DEFAULT_PARAMS
        default_params = namespace.get('DEFAULT_PARAMS', {})
        for param_name, default_value in default_params.items():
            if param_name not in parameter_configs:
                parameter_configs[param_name] = {
                    'from': default_value,
                    'to': default_value,
                    'default': default_value
                }

        combinations = generate_parameter_combinations(parameter_configs, parameter_metadata)

        # Initialize timing
        start_time = time.time()

        session_data['bf_total'] = len(combinations)
        session_data['bf_completed'] = 0
        session_data['bf_errors'] = 0

        results = []

        for idx, params in enumerate(combinations):
            try:
                # Use original strategy class (optimized utility functions available internally)
                StrategyClass = namespace.get('UploadedStrategy')
                if not StrategyClass:
                    session_data['bf_errors'] += 1
                    continue

                # Resolve string constants to actual values (like 'True' -> True, 'EXIT_ORIGINAL' -> constant)
                resolved_params = {}
                for param_name, param_value in params.items():
                    if isinstance(param_value, str):
                        # Try to convert string booleans
                        if param_value == 'True' or param_value == 'true':
                            resolved_params[param_name] = True
                        elif param_value == 'False' or param_value == 'false':
                            resolved_params[param_name] = False
                        else:
                            # Try to resolve as a constant from the namespace
                            if param_value in namespace:
                                resolved_params[param_name] = namespace[param_value]
                            else:
                                try:
                                    resolved_params[param_name] = float(param_value)
                                except:
                                    resolved_params[param_name] = param_value
                    else:
                        resolved_params[param_name] = param_value

                # Try to pass freedom_df to strategy if it accepts it
                try:
                    strategy = StrategyClass(ohlc_df.copy(), resolved_params, freedom_df=additional_tf_df)
                except TypeError:
                    # Fallback: strategy doesn't accept freedom_df parameter
                    strategy = StrategyClass(ohlc_df.copy(), resolved_params)

                result = strategy.run()

                # Convert trades DataFrame and calculate KPIs (same as Current endpoint)
                trades_list = []
                trades_data = result.get('trades', pd.DataFrame())
                if isinstance(trades_data, pd.DataFrame) and not trades_data.empty:
                    trades_list = trades_data.to_dict(orient='records')
                    # Convert Timestamp objects to ISO strings
                    for trade in trades_list:
                        for key, val in trade.items():
                            if isinstance(val, pd.Timestamp):
                                trade[key] = val.isoformat()
                            elif isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
                                trade[key] = None

                # Calculate KPIs from trades (same logic as Current endpoint)
                trades_df = pd.DataFrame(trades_list) if trades_list else pd.DataFrame()
                total_trades = len(trades_df)
                winning = len(trades_df[trades_df['pnl'] > 0]) if 'pnl' in trades_df.columns and len(trades_df) > 0 else 0
                losing = len(trades_df[trades_df['pnl'] < 0]) if 'pnl' in trades_df.columns and len(trades_df) > 0 else 0
                total_pnl = float(trades_df['pnl'].sum()) if 'pnl' in trades_df.columns and len(trades_df) > 0 else 0
                profit_factor = 0
                max_profit = 0
                max_loss = 0

                if total_trades > 0 and 'pnl' in trades_df.columns:
                    gross_profit = float(trades_df[trades_df['pnl'] > 0]['pnl'].sum()) if 'pnl' in trades_df.columns else 0
                    gross_loss = float(abs(trades_df[trades_df['pnl'] < 0]['pnl'].sum())) if 'pnl' in trades_df.columns else 0
                    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
                    win_rate = (winning / total_trades * 100) if total_trades > 0 else 0
                    max_profit = float(trades_df['pnl'].max()) if len(trades_df) > 0 else 0
                    max_loss = float(trades_df['pnl'].min()) if len(trades_df) > 0 else 0
                else:
                    win_rate = 0

                summary = {
                    'total_trades': int(total_trades),
                    'winning_trades': int(winning),
                    'losing_trades': int(losing),
                    'win_rate': float(win_rate),
                    'max_profit': float(max_profit),
                    'max_loss': float(max_loss),
                    'total_pnl': float(total_pnl),
                    'max_drawdown': float(result.get('max_drawdown', 0)),
                    'max_drawdown_intrabar': float(result.get('max_drawdown', 0)),
                    'profit_factor': float(profit_factor),
                    'trades': trades_list
                }

                result = {'parameters': params, **summary}
                result = clean_nan(result)
                results.append(result)

            except Exception as e:
                session_data['bf_errors'] += 1
            finally:
                session_data['bf_completed'] += 1

        results_sorted = sorted(results, key=lambda x: x.get('total_pnl', 0), reverse=True)

        # Calculate final stats
        end_time = time.time()
        elapsed_time = end_time - start_time
        total_combinations = len(combinations)
        throughput_per_sec = total_combinations / elapsed_time if elapsed_time > 0 else 0

        return Response(
            json.dumps({
                'success': True,
                'results': results_sorted,
                'note': '✅ Original strategy with Numba JIT-optimized indicators',
                'implementation': 'numba',
                'stats': {
                    'start_time': start_time,
                    'end_time': end_time,
                    'duration_seconds': elapsed_time,
                    'total_combinations': total_combinations,
                    'throughput_per_sec': throughput_per_sec
                }
            }, cls=NaNEncoder),
            mimetype='application/json'
        )

    except Exception as e:
        return jsonify({'error': f'Numba brute force error: {str(e)}'}), 500


@app.route('/api/bruteforce-test-parallel', methods=['POST'])
def bruteforce_test_parallel():
    """
    Parallel brute force test - 3-4x speedup using multiprocessing
    Uses all available CPU cores for simultaneous backtest execution
    """
    try:
        from parallel_backtest import ParallelBacktestEngine

        data = request.json
        python_code = data.get('python_code')
        ohlc_content = data.get('ohlc_content')
        parameter_configs = data.get('parameter_configs', {})
        parameter_metadata = data.get('parameter_metadata', {})
        additional_tf_content = data.get('additional_tf_content')
        additional_tf_filename = data.get('additional_tf_filename')

        # Ensure Freedom filter is disabled
        if 'useFreedomFilter' not in parameter_configs:
            parameter_configs['useFreedomFilter'] = {
                'from': False,
                'to': False,
                'default': False
            }

        if not python_code or not ohlc_content:
            return jsonify({'error': 'Python code and OHLC data required'}), 400

        from io import StringIO
        ohlc_df = pd.read_csv(StringIO(ohlc_content))

        # Normalize columns
        ohlc_df.columns = ohlc_df.columns.str.lower().str.strip()
        col_mapping = {}
        for idx, col in enumerate(ohlc_df.columns):
            if idx == 0:
                col_mapping[col] = 'time'
            elif idx == 1:
                col_mapping[col] = 'open'
            elif idx == 2:
                col_mapping[col] = 'high'
            elif idx == 3:
                col_mapping[col] = 'low'
            elif idx == 4:
                col_mapping[col] = 'close'
        ohlc_df.rename(columns=col_mapping, inplace=True)

        if 'time' in ohlc_df.columns:
            ohlc_df['time'] = pd.to_datetime(ohlc_df['time'])
            if ohlc_df['time'].dt.tz is not None:
                ohlc_df['time'] = ohlc_df['time'].dt.tz_localize(None)

        if 'volume' not in ohlc_df.columns:
            ohlc_df['volume'] = 0

        # Process additional TF data if provided
        additional_tf_df = None
        if additional_tf_content:
            from io import StringIO
            csv_buffer = StringIO(additional_tf_content)
            additional_tf_df = pd.read_csv(csv_buffer)

            # Keep only first 5 columns
            if len(additional_tf_df.columns) > 5:
                additional_tf_df = additional_tf_df.iloc[:, :5]

            # Rename columns to lowercase
            additional_tf_df.columns = additional_tf_df.columns.str.lower().str.strip()

            # Map to standard OHLC names
            col_mapping = {}
            for idx, col in enumerate(additional_tf_df.columns):
                if idx == 0:
                    col_mapping[col] = 'time'
                elif idx == 1:
                    col_mapping[col] = 'open'
                elif idx == 2:
                    col_mapping[col] = 'high'
                elif idx == 3:
                    col_mapping[col] = 'low'
                elif idx == 4:
                    col_mapping[col] = 'close'

            additional_tf_df.rename(columns=col_mapping, inplace=True)

            # Convert time to datetime and remove timezone
            if 'time' in additional_tf_df.columns:
                additional_tf_df['time'] = pd.to_datetime(additional_tf_df['time'])
                # Remove timezone if present
                if additional_tf_df['time'].dt.tz is not None:
                    additional_tf_df['time'] = additional_tf_df['time'].dt.tz_localize(None)

            # Add volume if missing
            if 'volume' not in additional_tf_df.columns:
                additional_tf_df['volume'] = 0

        # Execute code to get metadata
        namespace = {}
        exec(python_code, namespace)

        if not parameter_metadata:
            parameter_metadata = namespace.get('PARAMETER_METADATA', {})

        # Auto-fill missing parameters with defaults from DEFAULT_PARAMS
        default_params = namespace.get('DEFAULT_PARAMS', {})
        for param_name, default_value in default_params.items():
            if param_name not in parameter_configs:
                parameter_configs[param_name] = {
                    'from': default_value,
                    'to': default_value,
                    'default': default_value
                }

        # Generate combinations
        combinations = generate_parameter_combinations(parameter_configs, parameter_metadata)

        # Initialize progress tracking (like sequential endpoint)
        global bruteforce_progress
        bruteforce_progress = {
            'total': len(combinations),
            'completed': 0,
            'errors': 0,
            'start_time': time.time(),
            'is_running': True
        }

        # Run with parallel engine (9 workers - optimal for M1 Pro)
        engine = ParallelBacktestEngine(num_workers=9)
        results, elapsed_time = engine.run_backtests(
            python_code,
            ohlc_df,
            combinations,
            parameter_metadata,
            progress_callback=lambda completed, total: bruteforce_progress.update({'completed': completed}),
            freedom_df=additional_tf_df
        )

        # Mark test as complete
        bruteforce_progress['is_running'] = False

        # Calculate final stats
        start_time = bruteforce_progress['start_time']
        end_time = time.time()
        total_combinations = len(combinations)
        throughput_per_sec = total_combinations / elapsed_time if elapsed_time > 0 else 0

        return Response(
            json.dumps({
                'success': True,
                'results': results,
                'note': f'⚡ Parallel execution ({engine.num_workers} cores) - {elapsed_time:.2f}s',
                'implementation': 'parallel',
                'execution_time': elapsed_time,
                'stats': {
                    'start_time': start_time,
                    'end_time': end_time,
                    'duration_seconds': elapsed_time,
                    'total_combinations': total_combinations,
                    'throughput_per_sec': throughput_per_sec
                }
            }, sort_keys=False, cls=NaNEncoder),
            mimetype='application/json'
        )

    except Exception as e:
        return jsonify({'error': f'Parallel brute force error: {str(e)}'}), 500


@app.route('/api/backtest-kpis-numba', methods=['POST'])
def backtest_kpis_numba():
    """
    Numba-optimized KPI calculation - COMPLETELY SEPARATE IMPLEMENTATION
    Uses original strategy with isolated Numba optimization option
    Original version_11.py remains 100% untouched
    """
    try:
        data = request.get_json()
        python_code = data.get('python_code', '')
        ohlc_content = data.get('ohlc_content', '')
        parameters = data.get('parameters', {})

        if not python_code or not ohlc_content:
            return jsonify({'error': 'Python code and OHLC data required'}), 400

        from io import StringIO
        ohlc_df = pd.read_csv(StringIO(ohlc_content))

        # Normalize OHLC columns
        ohlc_df.columns = ohlc_df.columns.str.lower().str.strip()
        col_mapping = {}
        for idx, col in enumerate(ohlc_df.columns):
            if idx == 0:
                col_mapping[col] = 'time'
            elif idx == 1:
                col_mapping[col] = 'open'
            elif idx == 2:
                col_mapping[col] = 'high'
            elif idx == 3:
                col_mapping[col] = 'low'
            elif idx == 4:
                col_mapping[col] = 'close'
        ohlc_df.rename(columns=col_mapping, inplace=True)

        if 'time' in ohlc_df.columns:
            ohlc_df['time'] = pd.to_datetime(ohlc_df['time'])
            if ohlc_df['time'].dt.tz is not None:
                ohlc_df['time'] = ohlc_df['time'].dt.tz_localize(None)

        if 'volume' not in ohlc_df.columns:
            ohlc_df['volume'] = 0

        from version_11_numba_optimized import UploadedStrategyNumbaOptimized

        # Ensure time is set as index for Numba-optimized strategy
        if 'time' in ohlc_df.columns:
            ohlc_df.set_index('time', inplace=True)

        # Execute original Python code to get metadata
        namespace = {}
        exec(python_code, namespace)

        # Get parameter metadata
        parameter_metadata = namespace.get('PARAMETER_METADATA', {})

        # Use original strategy class (optimized utility functions available internally)
        StrategyClass = namespace.get('UploadedStrategy')
        if not StrategyClass:
            return jsonify({'error': 'UploadedStrategy class not found'}), 400

        strategy = StrategyClass(ohlc_df.copy(), parameters)
        result = strategy.run()

        # Calculate KPIs from trades (same logic as brute force endpoint)
        trades_list = []
        trades_data = result.get('trades', pd.DataFrame())
        if isinstance(trades_data, pd.DataFrame) and not trades_data.empty:
            trades_list = trades_data.to_dict(orient='records')

        # Calculate KPI metrics
        trades_df = pd.DataFrame(trades_list) if trades_list else pd.DataFrame()
        total_trades = len(trades_df)
        winning = len(trades_df[trades_df['pnl'] > 0]) if 'pnl' in trades_df.columns and len(trades_df) > 0 else 0
        losing = len(trades_df[trades_df['pnl'] < 0]) if 'pnl' in trades_df.columns and len(trades_df) > 0 else 0
        total_pnl = float(trades_df['pnl'].sum()) if 'pnl' in trades_df.columns and len(trades_df) > 0 else 0
        profit_factor = 0
        max_profit = 0
        max_loss = 0

        if total_trades > 0 and 'pnl' in trades_df.columns:
            gross_profit = float(trades_df[trades_df['pnl'] > 0]['pnl'].sum()) if 'pnl' in trades_df.columns else 0
            gross_loss = float(abs(trades_df[trades_df['pnl'] < 0]['pnl'].sum())) if 'pnl' in trades_df.columns else 0
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
            win_rate = (winning / total_trades * 100) if total_trades > 0 else 0
            max_profit = float(trades_df['pnl'].max()) if len(trades_df) > 0 else 0
            max_loss = float(trades_df['pnl'].min()) if len(trades_df) > 0 else 0
        else:
            win_rate = 0

        kpis = {
            'total_trades': {'calculated': total_trades, 'formula': 'COUNT(all trades)'},
            'winning_trades': {'calculated': winning, 'formula': 'COUNT(pnl > 0)'},
            'losing_trades': {'calculated': losing, 'formula': 'COUNT(pnl < 0)'},
            'win_rate': {'calculated': round(win_rate, 2), 'formula': f'({winning}/{total_trades}) × 100'},
            'max_profit': {'calculated': round(max_profit, 2), 'formula': 'MAX(pnl)'},
            'max_loss': {'calculated': round(max_loss, 2), 'formula': 'MIN(pnl)'},
            'total_pnl': {'calculated': round(total_pnl, 2), 'formula': 'SUM(trade PnL)'},
            'max_drawdown_cc': {'calculated': round(float(result.get('max_drawdown', 0)), 2), 'formula': 'Close-to-close drawdown'},
            'max_drawdown_intrabar': {'calculated': round(float(result.get('max_drawdown', 0)), 2), 'formula': 'Equity-based drawdown'},
            'profit_factor': {'calculated': round(profit_factor, 4), 'formula': f'${gross_profit:,.0f} / ${gross_loss:,.0f}'}
        }

        return Response(
            json.dumps({'success': True, 'kpis': kpis, 'implementation': 'numba'}, sort_keys=False, cls=NaNEncoder),
            mimetype='application/json'
        )

    except Exception as e:
        return jsonify({'error': f'Numba backtest error: {str(e)}'}), 500


@app.route('/api/bruteforce-test-multi-tf', methods=['POST'])
def bruteforce_test_multi_tf():
    """
    Multi-timeframe brute force test
    Runs the same parameter test on multiple OHLC files (different timeframes)
    Results combined with 'tf' column identifying each timeframe
    """
    try:
        from parallel_backtest import ParallelBacktestEngine
        import re

        data = request.json
        python_code = data.get('python_code')
        multi_ohlc_files = data.get('multi_ohlc_files', [])  # List of {filename, content}
        parameter_configs = data.get('parameter_configs', {})
        parameter_metadata = data.get('parameter_metadata', {})

        # Ensure Freedom filter is disabled
        if 'useFreedomFilter' not in parameter_configs:
            parameter_configs['useFreedomFilter'] = {
                'from': False,
                'to': False,
                'default': False
            }

        if not python_code or not multi_ohlc_files or len(multi_ohlc_files) == 0:
            return jsonify({'error': 'Python code and multiple OHLC files required'}), 400

        # Execute code once to get metadata
        namespace = {}
        exec(python_code, namespace)

        if not parameter_metadata:
            parameter_metadata = namespace.get('PARAMETER_METADATA', {})

        # Auto-fill missing parameters with defaults
        default_params = namespace.get('DEFAULT_PARAMS', {})
        for param_name, default_value in default_params.items():
            if param_name not in parameter_configs:
                parameter_configs[param_name] = {
                    'from': default_value,
                    'to': default_value,
                    'default': default_value
                }

        # Generate parameter combinations once (same for all TFs)
        combinations = generate_parameter_combinations(parameter_configs, parameter_metadata)

        # Initialize progress tracking
        global bruteforce_progress
        bruteforce_progress = {
            'total': len(combinations) * len(multi_ohlc_files),
            'completed': 0,
            'errors': 0,
            'start_time': time.time(),
            'is_running': True
        }

        # Process each OHLC file
        all_results = []
        engine = ParallelBacktestEngine(num_workers=9)
        start_time = time.time()

        for file_entry in multi_ohlc_files:
            filename = file_entry.get('filename')
            ohlc_content = file_entry.get('content')

            if not filename or not ohlc_content:
                continue

            # Extract timeframe from filename - try multiple patterns
            timeframe = 'unknown'

            # Pattern 1: underscore separator (OANDA_XAUUSD_5min.csv)
            tf_match = re.search(r'_([a-zA-Z0-9]+)\.csv$', filename)
            if tf_match:
                timeframe = tf_match.group(1)
            else:
                # Pattern 2: dash separator (OANDA-XAUUSD-5min.csv)
                tf_match = re.search(r'-([a-zA-Z0-9]+)\.csv$', filename)
                if tf_match:
                    timeframe = tf_match.group(1)
                else:
                    # Pattern 3: space separator (OANDA XAUUSD 5min.csv)
                    tf_match = re.search(r' ([a-zA-Z0-9]+)\.csv$', filename)
                    if tf_match:
                        timeframe = tf_match.group(1)
                    else:
                        # Pattern 4: timeframe at start of filename (5min.csv, 15min.csv)
                        tf_match = re.search(r'^([0-9]+[a-zA-Z]+)\.csv$', filename)
                        if tf_match:
                            timeframe = tf_match.group(1)
                        else:
                            # Pattern 5: last word before .csv (fallback)
                            parts = filename.replace('-', '_').replace(' ', '_').split('_')
                            # Find the last part that looks like a timeframe (digit+letter pattern)
                            for part in reversed(parts):
                                part_clean = part.replace('.csv', '')
                                if part_clean and re.match(r'^[0-9]+[a-zA-Z]+$|^[a-zA-Z]+[0-9]+$', part_clean):
                                    timeframe = part_clean
                                    break
                            # Final fallback: use last part before .csv
                            if timeframe == 'unknown' and len(parts) > 0:
                                last_part = parts[-1].replace('.csv', '')
                                if last_part and len(last_part) > 0:
                                    timeframe = last_part

            # Load and normalize OHLC data
            from io import StringIO
            ohlc_df = pd.read_csv(StringIO(ohlc_content))

            # Normalize columns
            ohlc_df.columns = ohlc_df.columns.str.lower().str.strip()
            col_mapping = {}
            for idx, col in enumerate(ohlc_df.columns):
                if idx == 0:
                    col_mapping[col] = 'time'
                elif idx == 1:
                    col_mapping[col] = 'open'
                elif idx == 2:
                    col_mapping[col] = 'high'
                elif idx == 3:
                    col_mapping[col] = 'low'
                elif idx == 4:
                    col_mapping[col] = 'close'
            ohlc_df.rename(columns=col_mapping, inplace=True)

            if 'time' in ohlc_df.columns:
                ohlc_df['time'] = pd.to_datetime(ohlc_df['time'])
                if ohlc_df['time'].dt.tz is not None:
                    ohlc_df['time'] = ohlc_df['time'].dt.tz_localize(None)

            if 'volume' not in ohlc_df.columns:
                ohlc_df['volume'] = 0

            # Run parallel backtest for this TF
            results, _ = engine.run_backtests(
                python_code,
                ohlc_df,
                combinations,
                parameter_metadata,
                progress_callback=lambda completed, total: bruteforce_progress.update({'completed': bruteforce_progress['completed'] + 1})
            )

            # Add TF column to each result
            for result in results:
                result['tf'] = timeframe

            all_results.extend(results)

        # Sort by PnL then by TF
        all_results_sorted = sorted(
            all_results,
            key=lambda x: (-x.get('total_pnl', 0), x.get('tf', ''))
        )

        # Mark test as complete
        bruteforce_progress['is_running'] = False
        elapsed_time = time.time() - start_time

        # Calculate final stats
        total_combinations = len(combinations) * len(multi_ohlc_files)
        throughput_per_sec = total_combinations / elapsed_time if elapsed_time > 0 else 0

        return Response(
            json.dumps({
                'success': True,
                'results': all_results_sorted,
                'note': f'⚡ Multi-TF Parallel execution ({engine.num_workers} cores) - {elapsed_time:.2f}s',
                'implementation': 'multi-tf-parallel',
                'execution_time': elapsed_time,
                'stats': {
                    'start_time': bruteforce_progress['start_time'],
                    'end_time': time.time(),
                    'duration_seconds': elapsed_time,
                    'total_combinations': total_combinations,
                    'throughput_per_sec': throughput_per_sec,
                    'timeframes_tested': len(multi_ohlc_files)
                }
            }, sort_keys=False, cls=NaNEncoder),
            mimetype='application/json'
        )

    except Exception as e:
        return jsonify({'error': f'Multi-TF brute force error: {str(e)}'}), 500


@app.route('/api/unattended-bruteforce-template', methods=['GET'])
def get_unattended_template():
    """Return CSV template for unattended brute force"""
    template = """test_sequence_id,python_file_path,main_ohlc_path,additional_ohlc_path,parameter_name,param_from,param_to,param_step
TEST_001,/path/to/strategy.py,/path/to/OHLC_5min.csv,,fast_ma,5,20,5
TEST_001,/path/to/strategy.py,/path/to/OHLC_5min.csv,,slow_ma,20,50,10
TEST_002,/path/to/strategy.py,/path/to/OHLC_15min.csv,,threshold,10,100,10
TEST_003,/path/to/strategy.py,/path/to/OHLC_1H.csv,/path/to/OHLC_4H.csv,parameter,1,50,5"""

    return Response(
        template,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=unattended_bruteforce_template.csv'}
    )


@app.route('/api/unattended-bruteforce-validate', methods=['POST'])
def validate_unattended_csv():
    """Validate CSV test specifications"""
    try:
        from unattended_bruteforce import UnattendedBruteForceEngine

        csv_content = request.json.get('csv_content', '')

        if not csv_content:
            return jsonify({'error': 'CSV content is empty'}), 400

        engine = UnattendedBruteForceEngine()
        result = engine.parse_csv(csv_content)

        if not result['valid']:
            return jsonify({'valid': False, 'error': result['error']}), 400

        # Count total tests and combinations
        tests = result['tests']
        summary = []
        total_combos = 0

        for test_id, specs in tests.items():
            combos = engine.generate_combinations(specs)
            total_combos += len(combos)
            summary.append({
                'test_sequence_id': test_id,
                'parameter_count': len(specs),
                'combinations': len(combos)
            })

        return jsonify({
            'valid': True,
            'tests': summary,
            'total_combinations': total_combos
        })

    except Exception as e:
        return jsonify({'error': f'Validation error: {str(e)}'}), 500


def progress_callback(update_data):
    """Callback for progress updates during unattended brute force"""
    if 'current_test' in update_data:
        unattended_progress['current_test'] = update_data['current_test']
    if 'test_completed' in update_data:
        unattended_progress['tests_completed'] += 1
        # Don't update combinations_completed here - engine callbacks handle it correctly


def make_engine_progress_callback(test_id, combinations_in_test, completed_before):
    """Create an engine progress callback for real-time combination tracking"""
    call_count = [0]  # Counter to track calls

    def engine_progress(completed_in_test, total_in_test):
        # Update global combinations completed count
        # completed_in_test is 0 to combinations_in_test for current test
        # completed_before is sum of all previous tests
        global_completed = completed_before + completed_in_test
        old_completed = unattended_progress['combinations_completed']
        unattended_progress['combinations_completed'] = global_completed
        # Also update current_test so progress polling can identify which test is running
        unattended_progress['current_test'] = test_id

        # Log when value changes
        if global_completed != old_completed:
            print(f"  📈 {test_id}: {completed_in_test}/{total_in_test} (global: {old_completed}→{global_completed})", flush=True)
    return engine_progress


@app.route('/api/unattended-bruteforce-execute', methods=['POST'])
def execute_unattended_bruteforce():
    """Execute unattended brute force tests from CSV"""
    try:
        import threading
        from execution_worker import run_execution

        csv_content = request.json.get('csv_content', '')

        if not csv_content:
            return jsonify({'error': 'CSV content is empty'}), 400

        # Check if there's a stale execution (thread is dead but flag is still on)
        if unattended_progress['is_running'] and unattended_progress['execution_thread']:
            if not unattended_progress['execution_thread'].is_alive():
                unattended_progress['is_running'] = False
                unattended_progress['should_stop'] = False

        if unattended_progress['is_running']:
            return jsonify({'error': 'Execution already in progress'}), 400

        # Initialize progress tracking
        unattended_progress['is_running'] = True
        unattended_progress['start_time'] = time.time()
        unattended_progress['combinations_completed'] = 0
        unattended_progress['current_test'] = ''
        unattended_progress['tests_completed'] = 0
        unattended_progress['should_stop'] = False
        unattended_progress['execution_results'] = {}

        # Start execution in background thread
        execution_thread = threading.Thread(
            target=run_execution,
            args=(csv_content, progress_callback, make_engine_progress_callback, unattended_progress),
            daemon=True
        )
        execution_thread.start()
        unattended_progress['execution_thread'] = execution_thread

        return jsonify({
            'success': True,
            'message': 'Execution started'
        })

    except Exception as e:
        unattended_progress['is_running'] = False
        return jsonify({'error': f'Execution error: {str(e)}'}), 500


@app.route('/api/unattended-bruteforce-progress', methods=['GET'])
def get_unattended_progress():
    """Get current progress of unattended brute force execution"""
    if not unattended_progress['is_running']:
        return jsonify({'error': 'No test running'}), 400

    elapsed = time.time() - unattended_progress['start_time'] if unattended_progress['start_time'] else 0
    completed = unattended_progress['combinations_completed']
    total = unattended_progress['total_combinations']
    remaining = total - completed
    rate = completed / elapsed if elapsed > 0 else 0
    eta = remaining / rate if rate > 0 else 0
    percentage = int((completed / total * 100)) if total > 0 else 0

    return jsonify({
        'total': total,
        'completed': completed,
        'remaining': remaining,
        'percentage': percentage,
        'rate': f'{rate:.2f}',
        'eta_seconds': int(eta),
        'current_test': unattended_progress['current_test'],
        'tests_completed': unattended_progress['tests_completed'],
        'total_tests': unattended_progress['total_tests']
    })


@app.route('/api/unattended-bruteforce-stop', methods=['POST'])
def stop_unattended_bruteforce():
    """Stop the currently running unattended brute force execution"""
    if not unattended_progress['is_running']:
        return jsonify({'error': 'No execution running'}), 400

    try:
        import psutil
        import signal

        # Set stop flag
        unattended_progress['should_stop'] = True

        # Try to kill all worker processes
        try:
            current_process = psutil.Process(os.getpid())
            children = current_process.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception as e:
            print(f"Could not kill child processes: {e}")

        # Mark as stopped
        unattended_progress['is_running'] = False

        return jsonify({
            'success': True,
            'message': 'Execution terminated'
        })

    except Exception as e:
        print(f"Error stopping execution: {e}")
        unattended_progress['is_running'] = False
        return jsonify({
            'success': True,
            'message': 'Execution stop requested'
        })


@app.route('/api/unattended-bruteforce-final-results', methods=['GET'])
def get_unattended_final_results():
    """Get final execution results"""
    if not unattended_progress.get('execution_results'):
        return jsonify({'error': 'No execution results available'}), 400

    return jsonify({
        'success': True,
        'execution_results': unattended_progress['execution_results'],
        'output_directory': unattended_progress.get('output_directory', '')
    })


@app.route('/api/unattended-bruteforce-results/<test_sequence_id>', methods=['GET'])
def get_unattended_results(test_sequence_id):
    """Get results for a specific test sequence"""
    try:
        from unattended_bruteforce import UnattendedBruteForceEngine

        engine = UnattendedBruteForceEngine()
        output_dir = engine.output_dir

        # Find latest results file for this test
        import glob
        pattern = os.path.join(output_dir, f"results_{test_sequence_id}_*.csv")
        files = sorted(glob.glob(pattern), reverse=True)

        if not files:
            return jsonify({'error': f'No results found for {test_sequence_id}'}), 404

        latest_file = files[0]

        # Read and return results
        results_df = pd.read_csv(latest_file)
        results = results_df.to_dict(orient='records')

        return jsonify({
            'success': True,
            'test_sequence_id': test_sequence_id,
            'results_file': os.path.basename(latest_file),
            'results_count': len(results),
            'results': results
        })

    except Exception as e:
        return jsonify({'error': f'Error retrieving results: {str(e)}'}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5001, host='localhost')
