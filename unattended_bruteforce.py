"""
Unattended Brute Force Engine
Processes batch test specifications from CSV and runs tests automatically
"""

import csv
import os
import json
import pandas as pd
import time
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from parallel_backtest import ParallelBacktestEngine
from io import StringIO


class UnattendedBruteForceEngine:
    """Processes CSV test specifications and runs brute force tests unattended"""

    def __init__(self, output_dir=None, progress_callback=None):
        if output_dir is None:
            output_dir = os.path.join(os.path.dirname(__file__), "outputs", "unattended_results")
        self.output_dir = output_dir
        self.engine = ParallelBacktestEngine(num_workers=9)
        self.progress_callback = progress_callback
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    def parse_csv(self, csv_content):
        """Parse CSV test specifications

        Returns: {
            'valid': bool,
            'error': str or None,
            'tests': {test_sequence_id: [{spec dict}]}
        }
        """
        try:
            reader = csv.DictReader(StringIO(csv_content))
            rows = list(reader)

            if not rows:
                return {'valid': False, 'error': 'CSV is empty'}

            # Group by test_sequence_id
            tests = defaultdict(list)
            errors = []

            for idx, row in enumerate(rows, 1):
                # Validate required fields
                required = ['test_sequence_id', 'python_file_path', 'main_ohlc_path',
                           'parameter_name', 'param_from', 'param_to', 'param_step']

                missing = [f for f in required if f not in row or not row[f]]
                if missing:
                    errors.append(f"Row {idx}: Missing {', '.join(missing)}")
                    continue

                # Validate numeric fields
                try:
                    param_from = float(row['param_from'])
                    param_to = float(row['param_to'])
                    param_step = float(row['param_step'])

                    if param_step <= 0:
                        errors.append(f"Row {idx}: param_step must be positive")
                        continue

                    if param_from >= param_to:
                        errors.append(f"Row {idx}: param_from must be less than param_to")
                        continue

                except ValueError as e:
                    errors.append(f"Row {idx}: Invalid numeric value - {str(e)}")
                    continue

                # Validate file paths
                python_path = row['python_file_path'].strip()
                ohlc_path = row['main_ohlc_path'].strip()
                additional_path = row.get('additional_ohlc_path', '').strip()

                if not os.path.exists(python_path):
                    errors.append(f"Row {idx}: Python file not found: {python_path}")
                    continue

                if not os.path.exists(ohlc_path):
                    errors.append(f"Row {idx}: OHLC file not found: {ohlc_path}")
                    continue

                if additional_path and not os.path.exists(additional_path):
                    errors.append(f"Row {idx}: Additional OHLC file not found: {additional_path}")
                    continue

                # Add valid spec
                spec = {
                    'test_sequence_id': row['test_sequence_id'].strip(),
                    'python_file_path': python_path,
                    'main_ohlc_path': ohlc_path,
                    'additional_ohlc_path': additional_path if additional_path else None,
                    'parameter_name': row['parameter_name'].strip(),
                    'param_from': param_from,
                    'param_to': param_to,
                    'param_step': param_step
                }

                tests[spec['test_sequence_id']].append(spec)

            if errors:
                return {'valid': False, 'error': 'CSV validation errors:\n' + '\n'.join(errors)}

            if not tests:
                return {'valid': False, 'error': 'No valid test specifications found'}

            return {'valid': True, 'tests': dict(tests)}

        except Exception as e:
            return {'valid': False, 'error': f'CSV parsing error: {str(e)}'}

    def generate_combinations(self, specs):
        """Generate parameter combinations from specs (matches brute force page logic)"""
        import itertools

        param_lists = {}

        for spec in specs:
            param_name = spec['parameter_name']
            from_val = spec['param_from']
            to_val = spec['param_to']
            step = spec['param_step']

            values = []
            # Use epsilon for floating point tolerance (same as brute force page)
            current = float(from_val)
            while current <= float(to_val) + 1e-9:
                # Round to 10 decimals to avoid precision issues
                values.append(round(current, 10))
                current += float(step)

            param_lists[param_name] = values

        # Generate cartesian product using itertools (same as brute force page)
        param_names = list(param_lists.keys())
        param_values = list(param_lists.values())

        combinations = []
        for combo_values in itertools.product(*param_values):
            combo_dict = dict(zip(param_names, combo_values))
            combinations.append(combo_dict)

        return combinations

    def execute_test(self, test_sequence_id, specs, total_combinations_all=0, completed_before=0, engine_progress_callback=None):
        """Execute a single test sequence

        Returns: {
            'success': bool,
            'results': list,
            'stats': dict,
            'error': str or None
        }
        """
        try:
            # Load strategy
            python_path = specs[0]['python_file_path']
            with open(python_path, 'r') as f:
                python_code = f.read()

            # Load main OHLC
            main_ohlc_path = specs[0]['main_ohlc_path']
            main_ohlc_df = pd.read_csv(main_ohlc_path)
            main_ohlc_df.columns = main_ohlc_df.columns.str.lower().str.strip()

            # Normalize columns
            col_mapping = {}
            for idx, col in enumerate(main_ohlc_df.columns):
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
            main_ohlc_df.rename(columns=col_mapping, inplace=True)

            if 'time' in main_ohlc_df.columns:
                main_ohlc_df['time'] = pd.to_datetime(main_ohlc_df['time'])
                if main_ohlc_df['time'].dt.tz is not None:
                    main_ohlc_df['time'] = main_ohlc_df['time'].dt.tz_localize(None)

            if 'volume' not in main_ohlc_df.columns:
                main_ohlc_df['volume'] = 0

            # Load additional OHLC if provided
            freedom_df = None
            if specs[0]['additional_ohlc_path']:
                freedom_path = specs[0]['additional_ohlc_path']
                freedom_df = pd.read_csv(freedom_path)
                freedom_df.columns = freedom_df.columns.str.lower().str.strip()

                col_mapping = {}
                for idx, col in enumerate(freedom_df.columns):
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
                freedom_df.rename(columns=col_mapping, inplace=True)

                if 'time' in freedom_df.columns:
                    freedom_df['time'] = pd.to_datetime(freedom_df['time'])
                    if freedom_df['time'].dt.tz is not None:
                        freedom_df['time'] = freedom_df['time'].dt.tz_localize(None)

                if 'volume' not in freedom_df.columns:
                    freedom_df['volume'] = 0

            # Generate combinations
            combinations = self.generate_combinations(specs)

            # Update progress: test starting
            if self.progress_callback:
                self.progress_callback({
                    'current_test': test_sequence_id,
                    'combinations_in_test': len(combinations)
                })

            # Execute brute force with progress callback
            start_time = time.time()
            results, elapsed_time = self.engine.run_backtests(
                python_code,
                main_ohlc_df,
                combinations,
                progress_callback=engine_progress_callback,
                freedom_df=freedom_df
            )

            # Update progress: test completed
            if self.progress_callback:
                self.progress_callback({
                    'test_completed': test_sequence_id,
                    'combinations_completed': len(combinations),
                    'total_combinations': total_combinations_all
                })

            # Sort by PnL descending
            results_sorted = sorted(results, key=lambda x: x.get('total_pnl', 0), reverse=True)

            # Generate statistics
            stats = {
                'test_sequence_id': test_sequence_id,
                'start_time': datetime.now().isoformat(),
                'end_time': datetime.now().isoformat(),
                'duration_seconds': elapsed_time,
                'total_combinations': len(combinations),
                'results_found': len(results_sorted),
                'throughput_per_sec': len(combinations) / elapsed_time if elapsed_time > 0 else 0
            }

            return {
                'success': True,
                'results': results_sorted,
                'stats': stats,
                'error': None
            }

        except Exception as e:
            return {
                'success': False,
                'results': [],
                'stats': None,
                'error': f'Test execution error: {str(e)}'
            }

    def save_results(self, test_sequence_id, results):
        """Save results to CSV file"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"results_{test_sequence_id}_{timestamp}.csv"
        filepath = os.path.join(self.output_dir, filename)

        # Create DataFrame
        rows = []
        for idx, result in enumerate(results, 1):
            param_str = ' | '.join([f"{k}={v}" for k, v in result.get('parameters', {}).items()])
            rows.append({
                'Rank': idx,
                'Parameters': param_str,
                'Total Trades': result.get('total_trades', 0),
                'Winning Trades': result.get('winning_trades', 0),
                'Losing Trades': result.get('losing_trades', 0),
                'Win Rate (%)': f"{result.get('win_rate', 0):.2f}",
                'Max Profit': f"{result.get('max_profit', 0):.2f}",
                'Max Loss': f"{result.get('max_loss', 0):.2f}",
                'Total PnL': f"{result.get('total_pnl', 0):.2f}",
                'Max Drawdown': f"{result.get('max_drawdown', 0):.2f}",
                'Profit Factor': f"{result.get('profit_factor', 0):.4f}"
            })

        df = pd.DataFrame(rows)
        df.to_csv(filepath, index=False)

        return filepath

    def save_statistics(self, test_sequence_id, stats, results):
        """Save execution statistics to TXT file"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"stats_{test_sequence_id}_{timestamp}.txt"
        filepath = os.path.join(self.output_dir, filename)

        content = f"""================================================================================
UNATTENDED BRUTE FORCE EXECUTION STATISTICS
================================================================================

Test Sequence ID: {test_sequence_id}
Execution Time: {stats['start_time']}
Completion Time: {stats['end_time']}

EXECUTION SUMMARY
================================================================================
Total Combinations Tested: {stats['total_combinations']}
Results Found: {stats['results_found']}
Duration: {stats['duration_seconds']:.2f} seconds
Throughput: {stats['throughput_per_sec']:.2f} combinations/second

TOP 5 RESULTS (Sorted by Total PnL)
================================================================================
"""

        for idx, result in enumerate(results[:5], 1):
            param_str = ', '.join([f"{k}={v}" for k, v in result.get('parameters', {}).items()])
            content += f"""
Rank {idx}:
  Parameters: {param_str}
  Total PnL: {result.get('total_pnl', 0):.2f}
  Total Trades: {result.get('total_trades', 0)}
  Win Rate: {result.get('win_rate', 0):.2f}%
  Profit Factor: {result.get('profit_factor', 0):.4f}
"""

        content += "\n" + "="*80 + "\n"

        with open(filepath, 'w') as f:
            f.write(content)

        return filepath
