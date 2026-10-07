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

    def test_validate_numeric_parameter_order(self):
        """Test that param_from < param_to is enforced"""
        csv_content = '''test_sequence_id,python_file_path,main_ohlc_path,additional_ohlc_path,parameter_name,param_from,param_to,param_step
TEST_001,/Users/saransh/StrategyTester_v1/uploads/version_11.py,/Users/saransh/StrategyTester_v1/uploads/OANDA_XAUUSD_23min.csv,,length,10,1,1
'''
        engine = UnattendedBruteForceEngine()
        result = engine.validate_csv(csv_content)

        assert result['valid'] == False
        assert len(result['errors']) > 0
        assert 'param_from must be less than param_to' in result['errors'][0]

    def test_validate_positive_step(self):
        """Test that param_step must be positive"""
        csv_content = '''test_sequence_id,python_file_path,main_ohlc_path,additional_ohlc_path,parameter_name,param_from,param_to,param_step
TEST_001,/Users/saransh/StrategyTester_v1/uploads/version_11.py,/Users/saransh/StrategyTester_v1/uploads/OANDA_XAUUSD_23min.csv,,length,1,10,-1
'''
        engine = UnattendedBruteForceEngine()
        result = engine.validate_csv(csv_content)

        assert result['valid'] == False
        assert any('param_step must be positive' in err for err in result['errors'])

    def test_validate_file_path_existence(self):
        """Test that file paths must exist"""
        csv_content = '''test_sequence_id,python_file_path,main_ohlc_path,additional_ohlc_path,parameter_name,param_from,param_to,param_step
TEST_001,/nonexistent/file.py,/Users/saransh/StrategyTester_v1/uploads/OANDA_XAUUSD_23min.csv,,length,1,10,1
'''
        engine = UnattendedBruteForceEngine()
        result = engine.validate_csv(csv_content)

        assert result['valid'] == False
        assert any('Python file not found' in err for err in result['errors'])

    def test_validate_combination_count_calculation(self):
        """Test accurate combination count calculation"""
        csv_content = '''test_sequence_id,python_file_path,main_ohlc_path,additional_ohlc_path,parameter_name,param_from,param_to,param_step
TEST_001,/Users/saransh/StrategyTester_v1/uploads/version_11.py,/Users/saransh/StrategyTester_v1/uploads/OANDA_XAUUSD_23min.csv,,length,1,5,1
TEST_001,/Users/saransh/StrategyTester_v1/uploads/version_11.py,/Users/saransh/StrategyTester_v1/uploads/OANDA_XAUUSD_23min.csv,,mult,0.1,0.5,0.1
'''
        engine = UnattendedBruteForceEngine()
        result = engine.validate_csv(csv_content)

        if result['valid']:
            # 5 * 5 = 25 combinations
            assert result['tests'][0]['combinations'] == 25
