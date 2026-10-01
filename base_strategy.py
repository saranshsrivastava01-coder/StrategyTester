from abc import ABC, abstractmethod
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any
import json
import re


class BaseStrategy(ABC):
    def __init__(self, df: pd.DataFrame, params: Dict[str, Any] = None):
        self.df = df.copy()
        self.params = params or {}
        self.results = {}
        self.trades = []

    @abstractmethod
    def calculate_indicators(self):
        pass

    @abstractmethod
    def generate_signals(self):
        pass

    @abstractmethod
    def run_backtest(self):
        pass

    def get_results(self):
        return self.results


class StrategyParameterDetector:
    @staticmethod
    def detect_parameters(code: str) -> Dict[str, Dict[str, Any]]:
        parameters = {}

        comment_params = StrategyParameterDetector._extract_from_comments(code)
        parameters.update(comment_params)

        return parameters

    @staticmethod
    def _extract_from_comments(code: str) -> Dict[str, Dict[str, Any]]:
        parameters = {}
        lines = code.split('\n')

        for line in lines:
            if 'PARAM:' in line:
                match = re.search(r'PARAM:\s*(\w+)\s*=\s*([\d.]+|true|false)', line)
                if match:
                    param_name = match.group(1)
                    param_value = match.group(2)

                    if param_value.lower() in ['true', 'false']:
                        param_type = 'bool'
                        default_value = param_value.lower() == 'true'
                    else:
                        param_type = 'float' if '.' in param_value else 'int'
                        default_value = float(param_value) if '.' in param_value else int(param_value)

                    parameters[param_name] = {
                        'type': param_type,
                        'default': default_value,
                        'min': None,
                        'max': None
                    }

        return parameters
