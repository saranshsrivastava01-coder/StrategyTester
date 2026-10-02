"""
Parallel Backtest Engine
Uses multiprocessing to achieve 3-4x speedup on multi-core systems

Splits parameter combinations across CPU cores and runs backtests in parallel.
M1 Pro has 8 performance cores, so expect 3-4x speedup.
"""

import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
import pandas as pd
import numpy as np
import time
from functools import partial
import traceback


def _run_single_backtest(args):
    """
    Run a single backtest in a worker process
    Must be at module level for pickling
    """
    try:
        python_code, ohlc_df, params, parameter_metadata = args

        # Execute code in worker
        namespace = {}
        exec(python_code, namespace)

        StrategyClass = namespace.get('UploadedStrategy')
        if not StrategyClass:
            return None

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

        strategy = StrategyClass(ohlc_df.copy(), resolved_params)
        result = strategy.run()

        # Calculate KPIs
        trades_data = result.get('trades', pd.DataFrame())
        if isinstance(trades_data, pd.DataFrame) and not trades_data.empty:
            trades_list = trades_data.to_dict(orient='records')
        else:
            trades_list = []

        trades_df = pd.DataFrame(trades_list) if trades_list else pd.DataFrame()
        total_trades = len(trades_df)
        winning = len(trades_df[trades_df['pnl'] > 0]) if 'pnl' in trades_df.columns and len(trades_df) > 0 else 0
        losing = len(trades_df[trades_df['pnl'] < 0]) if 'pnl' in trades_df.columns and len(trades_df) > 0 else 0
        total_pnl = float(trades_df['pnl'].sum()) if 'pnl' in trades_df.columns and len(trades_df) > 0 else 0

        gross_profit = sum(t['pnl'] for t in trades_list if t['pnl'] > 0) if trades_list else 0
        gross_loss = abs(sum(t['pnl'] for t in trades_list if t['pnl'] < 0)) if trades_list else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        max_profit = float(trades_df['pnl'].max()) if 'pnl' in trades_df.columns and len(trades_df) > 0 else 0
        max_loss = float(trades_df['pnl'].min()) if 'pnl' in trades_df.columns and len(trades_df) > 0 else 0
        win_rate = (winning / total_trades * 100) if total_trades > 0 else 0

        return {
            'parameters': params,
            'total_trades': total_trades,
            'winning_trades': winning,
            'losing_trades': losing,
            'win_rate': win_rate,
            'max_profit': max_profit,
            'max_loss': max_loss,
            'total_pnl': total_pnl,
            'max_drawdown': float(result.get('max_drawdown', 0)),
            'profit_factor': profit_factor
        }

    except Exception as e:
        # Log error for debugging
        print(f"❌ Backtest failed for params {params}: {str(e)[:100]}", flush=True)
        return None


class ParallelBacktestEngine:
    """
    Parallel backtest engine using multiprocessing
    Automatically uses all available CPU cores
    """

    def __init__(self, num_workers=None):
        """
        Initialize the parallel engine

        Args:
            num_workers: Number of worker processes.
                        If None, uses number of CPU cores - 1
        """
        if num_workers is None:
            # Use all cores except 1 (keep system responsive)
            num_workers = max(1, mp.cpu_count() - 1)

        self.num_workers = num_workers
        print(f"⚡ Parallel Engine: Using {num_workers} worker processes")

    def run_backtests(self, python_code, ohlc_df, combinations, parameter_metadata=None, progress_callback=None):
        """
        Run multiple backtests in parallel

        Args:
            python_code: Strategy Python code
            ohlc_df: OHLC dataframe
            combinations: List of parameter dicts
            parameter_metadata: Parameter metadata (optional)
            progress_callback: Optional callback function(completed, total) for progress updates

        Returns:
            List of results (sorted by total_pnl descending)
        """

        # Prepare arguments for workers
        worker_args = [
            (python_code, ohlc_df, params, parameter_metadata)
            for params in combinations
        ]

        results = []
        completed = 0
        start_time = time.time()

        # Use ProcessPoolExecutor for parallel execution
        with ProcessPoolExecutor(max_workers=self.num_workers) as executor:
            # Submit all tasks
            futures = {
                executor.submit(_run_single_backtest, args): i
                for i, args in enumerate(worker_args)
            }

            # Collect results as they complete
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result is not None:
                        results.append(result)

                    completed += 1

                    # Call progress callback if provided
                    if progress_callback:
                        progress_callback(completed, len(combinations))

                    # Progress update every 10 results or at start/end
                    if completed % max(1, len(combinations) // 10) == 0 or completed == len(combinations):
                        elapsed = time.time() - start_time
                        rate = completed / elapsed if elapsed > 0 else 0
                        remaining = len(combinations) - completed
                        eta = remaining / rate if rate > 0 else 0

                        progress_pct = (completed / len(combinations)) * 100
                        print(f"  Progress: {completed}/{len(combinations)} ({progress_pct:.0f}%) "
                              f"| Rate: {rate:.1f}/sec | ETA: {eta:.0f}s")

                except Exception as e:
                    completed += 1
                    print(f"  Worker error: {str(e)[:100]}")

        # Sort by total_pnl descending
        results_sorted = sorted(results, key=lambda x: x.get('total_pnl', 0), reverse=True)

        total_time = time.time() - start_time
        print(f"\n✅ Parallel backtest complete!")
        print(f"   Total time: {total_time:.2f}s")
        print(f"   Results: {len(results_sorted)}/{len(combinations)}")

        return results_sorted, total_time


def estimate_speedup(num_combinations):
    """Estimate speedup based on number of cores"""
    num_cores = mp.cpu_count()
    # Theoretical speedup with overhead factor
    theoretical_speedup = num_cores - 1
    # Realistic speedup (80-90% efficiency)
    realistic_speedup = theoretical_speedup * 0.85

    return {
        'cores_available': num_cores,
        'theoretical_speedup': theoretical_speedup,
        'realistic_speedup': realistic_speedup,
        'estimated_time_sequential': '10s per 100 combos',
        'estimated_time_parallel': f'{10 / realistic_speedup:.1f}s per 100 combos'
    }


if __name__ == '__main__':
    print("Parallel Backtest Engine")
    print(f"CPU cores available: {mp.cpu_count()}")
    print(f"Workers that will be used: {max(1, mp.cpu_count() - 1)}")
