"""Tests for data processing and combination generation"""
import pytest
from unattended_bruteforce import UnattendedBruteForceEngine


class TestCombinationGeneration:
    """Tests for combination generation with precision handling"""

    def test_numeric_combination_generation(self):
        """Test numeric parameter combination generation"""
        specs = [
            {
                'parameter_name': 'length',
                'param_from': '1',
                'param_to': '3',
                'param_step': '1'
            },
            {
                'parameter_name': 'mult',
                'param_from': '0.1',
                'param_to': '0.3',
                'param_step': '0.1'
            }
        ]

        engine = UnattendedBruteForceEngine()
        combinations = engine.generate_combinations(specs)

        # Should have 3 * 3 = 9 combinations
        assert len(combinations) == 9

        # Check specific combinations exist
        combo_list = [tuple(sorted(c.items())) for c in combinations]
        assert (('length', 1.0), ('mult', 0.1)) in combo_list
        assert (('length', 3.0), ('mult', 0.3)) in combo_list

    def test_float_precision_handling(self):
        """Test that float precision is handled correctly"""
        specs = [
            {
                'parameter_name': 'mult',
                'param_from': '0.1',
                'param_to': '1.0',
                'param_step': '0.1'
            }
        ]

        engine = UnattendedBruteForceEngine()
        combinations = engine.generate_combinations(specs)

        # Should have 10 combinations (0.1, 0.2, ..., 1.0)
        assert len(combinations) == 10

        # Check all values are properly rounded
        for combo in combinations:
            mult_val = combo['mult']
            assert isinstance(mult_val, float)
            # Round to 10 decimals as per implementation
            assert round(mult_val, 10) == mult_val

    def test_boolean_parameter_handling(self):
        """Test handling of boolean/non-numeric parameters"""
        specs = [
            {
                'parameter_name': 'enablePyramiding',
                'param_from': 'True',
                'param_to': 'True',
                'param_step': '1'
            },
            {
                'parameter_name': 'length',
                'param_from': '1',
                'param_to': '2',
                'param_step': '1'
            }
        ]

        engine = UnattendedBruteForceEngine()
        combinations = engine.generate_combinations(specs)

        # Should have 1 * 2 = 2 combinations (enablePyramiding has only 1 value)
        assert len(combinations) == 2

        # Check that enablePyramiding is 'True' (string)
        for combo in combinations:
            assert combo['enablePyramiding'] == 'True'

    def test_large_range_combination_count(self):
        """Test combination count for large parameter ranges"""
        specs = [
            {
                'parameter_name': 'length',
                'param_from': '1',
                'param_to': '50',
                'param_step': '1'
            },
            {
                'parameter_name': 'mult',
                'param_from': '0.1',
                'param_to': '5',
                'param_step': '0.1'
            },
            {
                'parameter_name': 'ema9Len',
                'param_from': '1',
                'param_to': '10',
                'param_step': '1'
            }
        ]

        engine = UnattendedBruteForceEngine()
        combinations = engine.generate_combinations(specs)

        # 50 * 50 * 10 = 25,000 combinations
        assert len(combinations) == 25000


class TestCSVValidation:
    """Tests for CSV validation logic"""

    def test_combination_accuracy(self):
        """Test that combination generation is accurate"""
        engine = UnattendedBruteForceEngine()

        specs = [
            {'parameter_name': 'length', 'param_from': '1', 'param_to': '5', 'param_step': '1'},
            {'parameter_name': 'mult', 'param_from': '0.1', 'param_to': '0.5', 'param_step': '0.1'}
        ]

        combos = engine.generate_combinations(specs)
        # 5 * 5 = 25 combinations
        assert len(combos) == 25

    def test_float_rounding(self):
        """Test that floats are rounded consistently"""
        engine = UnattendedBruteForceEngine()

        specs = [
            {'parameter_name': 'mult', 'param_from': '0.1', 'param_to': '0.3', 'param_step': '0.1'}
        ]

        combos = engine.generate_combinations(specs)
        assert len(combos) == 3

        for combo in combos:
            assert round(combo['mult'], 10) == combo['mult']

    def test_mixed_parameter_types(self):
        """Test mixing different parameter types"""
        engine = UnattendedBruteForceEngine()

        specs = [
            {'parameter_name': 'length', 'param_from': '1', 'param_to': '3', 'param_step': '1'},
            {'parameter_name': 'enablePyramiding', 'param_from': 'True', 'param_to': 'True', 'param_step': '1'}
        ]

        combos = engine.generate_combinations(specs)
        # 3 * 1 = 3 combinations
        assert len(combos) == 3

        for combo in combos:
            assert combo['enablePyramiding'] == 'True'
