import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any
from itertools import product
import importlib.util
import sys


class StrategyOptimizer:
    def __init__(self, strategy_class, df: pd.DataFrame):
        self.strategy_class = strategy_class
        self.df = df.copy()
        self.results = []

    def test_parameters(self, param_ranges: Dict[str, List[Any]]) -> pd.DataFrame:
        """Test multiple parameter combinations"""

        param_names = list(param_ranges.keys())
        param_values = list(param_ranges.values())

        combinations = list(product(*param_values))

        for combo in combinations:
            params = dict(zip(param_names, combo))

            try:
                strategy = self.strategy_class(self.df.copy(), params)
                strategy.calculate_indicators()
                strategy.generate_signals()
                strategy.run_backtest()
                results = strategy.get_results()

                results['params'] = str(params)
                for key, value in params.items():
                    results[f'param_{key}'] = value

                self.results.append(results)
            except Exception as e:
                continue

        return pd.DataFrame(self.results)

    @staticmethod
    def load_strategy_from_code(code: str, strategy_name: str = "UploadedStrategy"):
        """Load strategy class from code string"""

        spec = importlib.util.spec_from_loader("strategy_module", loader=None)
        module = importlib.util.module_from_spec(spec)

        exec(code, module.__dict__)

        return getattr(module, strategy_name)
