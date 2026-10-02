"""
Cython-Optimized Parallel Backtest Engine
Uses compiled Cython module for 10-20x speedup
"""

import pandas as pd
import time
from typing import Dict, List, Any, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp

try:
    from cython_backtest import execute_backtest_compiled
    CYTHON_AVAILABLE = True
except ImportError:
    CYTHON_AVAILABLE = False
    print("⚠️  Cython module not available, falling back to Python")


def _run_backtest_cython_worker(args):
    """Worker function for parallel Cython execution"""
    python_code, ohlc_df, params, parameter_metadata = args

    try:
        if CYTHON_AVAILABLE:
            # Use compiled Cython version
            result = execute_backtest_compiled(python_code, ohlc_df, params, parameter_metadata)
        else:
            # Fallback to pure Python
            from parallel_backtest import _run_single_backtest
            result = _run_single_backtest(args)

        return result
    except Exception as e:
        print(f"❌ Cython backtest error: {str(e)[:100]}")
        return None


class CythonBacktestEngine:
    """
    Parallel backtest engine using Cython-compiled hot path
    Expected speedup: 10-20x over pure Python
    """

    def __init__(self, num_workers=None):
        """
        Args:
            num_workers: Number of worker processes
        """
        if num_workers is None:
            num_workers = max(1, mp.cpu_count() - 1)

        self.num_workers = num_workers
        self.cython_available = CYTHON_AVAILABLE

        print(f"⚡ Cython Backtest Engine:")
        print(f"   Workers: {num_workers}")
        print(f"   Cython compiled: {'✅ Yes' if CYTHON_AVAILABLE else '❌ No (fallback to Python)'}")
        if CYTHON_AVAILABLE:
            print(f"   Expected speedup: 10-20x")

    def run_backtests(self, python_code: str, ohlc_df: pd.DataFrame,
                     parameter_list: List[Dict], parameter_metadata: Dict = None,
                     progress_callback=None) -> Tuple[List[Dict], float]:
        """
        Run backtests using Cython-compiled execution
        """

        start_time = time.time()
        results = []
        completed = 0
        total = len(parameter_list)

        print(f"\n🚀 Running {total} backtests (Cython accelerated)")
        if self.cython_available:
            print(f"   Mode: ⚡ Compiled Cython (10-20x speedup expected)")
        else:
            print(f"   Mode: 🐍 Pure Python (Cython not available)")

        # Create worker arguments
        worker_args = [
            (python_code, ohlc_df, params, parameter_metadata)
            for params in parameter_list
        ]

        # Process in parallel
        with ProcessPoolExecutor(max_workers=self.num_workers) as executor:
            futures = {executor.submit(_run_backtest_cython_worker, args): i
                      for i, args in enumerate(worker_args)}

            for future in as_completed(futures):
                try:
                    result = future.result(timeout=300)
                    if result:
                        results.append(result)
                    completed += 1

                    if progress_callback:
                        progress_callback(completed, total)

                    # Progress indicator
                    if completed % max(1, total // 10) == 0:
                        pct = (completed / total) * 100
                        elapsed = time.time() - start_time
                        rate = completed / elapsed if elapsed > 0 else 0
                        print(f"   Progress: {completed}/{total} ({pct:.0f}%) | {rate:.2f} c/s")

                except Exception as e:
                    print(f"   ❌ Worker error: {str(e)[:100]}")
                    completed += 1

        total_time = time.time() - start_time
        throughput = total / total_time if total_time > 0 else 0

        # Sort by PnL
        results_sorted = sorted(results, key=lambda x: x.get('total_pnl', 0), reverse=True)

        print(f"\n✅ Complete: {len(results_sorted)}/{total} in {total_time:.2f}s ({throughput:.2f} combos/sec)")

        return results_sorted, throughput
