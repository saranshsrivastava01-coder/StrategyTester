import re
from typing import Dict, List, Tuple, Any
import json


class PineScriptParser:
    @staticmethod
    def extract_parameters(pine_code: str) -> Dict[str, Dict[str, Any]]:
        """Extract parameters from Pine Script input() calls"""
        parameters = {}

        pattern = r'(\w+)\s*=\s*input(?:\.(int|float|bool|string))?\s*\(\s*([^,\)]+)(?:[^)]*title\s*=\s*["\']([^"\']*)["\'])?[^)]*(?:minval\s*=\s*([^\s,\)]+))?[^)]*(?:maxval\s*=\s*([^\s,\)]+))?[^)]*\)'

        matches = re.finditer(pattern, pine_code)

        for match in matches:
            var_name = match.group(1).strip()
            input_type = match.group(2) or 'default'
            default_val = match.group(3).strip()
            title = match.group(4)
            min_val = match.group(5)
            max_val = match.group(6)

            label = title if title else var_name

            param_type = 'float'
            if input_type == 'int':
                param_type = 'int'
                try:
                    default_value = int(default_val)
                except:
                    default_value = 0
            elif input_type == 'bool':
                param_type = 'bool'
                default_value = default_val.lower() in ['true', '1']
            elif input_type == 'string':
                param_type = 'string'
                default_value = default_val.strip('"\'')
            else:
                if default_val.lower() in ['true', 'false']:
                    param_type = 'bool'
                    default_value = default_val.lower() == 'true'
                elif '.' in default_val:
                    param_type = 'float'
                    try:
                        default_value = float(default_val)
                    except:
                        default_value = 0.0
                else:
                    param_type = 'int'
                    try:
                        default_value = int(default_val)
                    except:
                        default_value = 0

            parameters[var_name] = {
                'type': param_type,
                'default': default_value,
                'min': float(min_val) if min_val else None,
                'max': float(max_val) if max_val else None,
                'label': label,
                'original_name': var_name
            }

        return parameters

    @staticmethod
    def convert_to_python(pine_code: str, parameters: Dict[str, Dict[str, Any]]) -> str:
        """Convert Pine Script to Python strategy class"""

        python_code = '''import pandas as pd
import numpy as np
from base_strategy import BaseStrategy
from utils import calculate_ema, calculate_sma, calculate_atr, calculate_rsi

class UploadedStrategy(BaseStrategy):
    def __init__(self, df, params=None):
        super().__init__(df, params)
        self.indicators = {}

    def calculate_indicators(self):
        """Calculate technical indicators from Pine Script"""
'''

        python_code += '\n        # Access parameters via self.params\n'
        for param_name, param_info in parameters.items():
            param_type = param_info['type']
            default = param_info['default']
            python_code += f'        self.params.setdefault("{param_name}", {default})\n'

        python_code += '''
        self.df['signal'] = 0
        self.df['position'] = 0

    def generate_signals(self):
        """Generate trading signals"""
        pass

    def run_backtest(self):
        """Run the backtest"""
        pass
'''

        return python_code


class PineScriptValidator:
    @staticmethod
    def is_valid_pine_script(code: str) -> Tuple[bool, str]:
        """Validate if code looks like Pine Script"""

        pine_keywords = ['strategy', 'study', 'input', 'plot', 'close', 'open', 'high', 'low', 'volume']

        has_pine_syntax = any(keyword in code.lower() for keyword in pine_keywords)

        if not has_pine_syntax:
            return False, "No Pine Script syntax detected (missing strategy/study/input/plot)"

        return True, "Valid Pine Script"
