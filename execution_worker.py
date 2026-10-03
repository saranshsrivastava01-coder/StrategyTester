"""Background execution worker for unattended brute force"""

import threading
import os
import signal
from unattended_bruteforce import UnattendedBruteForceEngine


def run_execution(csv_content, progress_callback, make_callback_func, unattended_progress):
    """Run execution in background thread"""
    try:
        # Store thread ID for later termination
        unattended_progress['execution_thread_id'] = threading.current_thread().ident

        engine = UnattendedBruteForceEngine(progress_callback=progress_callback)
        parse_result = engine.parse_csv(csv_content)

        if not parse_result['valid']:
            print(f"CSV validation error: {parse_result['error']}")
            unattended_progress['is_running'] = False
            return

        tests = parse_result['tests']
        execution_results = {}

        # Calculate total combinations
        total_combinations = 0
        for specs_list in tests.values():
            combos = engine.generate_combinations(specs_list)
            total_combinations += len(combos)

        # Initialize progress tracking
        unattended_progress['is_running'] = True
        unattended_progress['total_combinations'] = total_combinations
        unattended_progress['combinations_completed'] = 0
        unattended_progress['current_test'] = ''
        unattended_progress['tests_completed'] = 0
        unattended_progress['total_tests'] = len(tests)
        unattended_progress['should_stop'] = False

        # Execute each test sequence
        completed_before = 0
        for test_id, specs in tests.items():
            # Check if stop was requested
            if unattended_progress['should_stop']:
                print(f"\n⏹️ Execution stopped by user")
                break

            print(f"\n🚀 Executing test: {test_id}")

            # Get combinations count for this test
            test_specs = engine.generate_combinations(specs)
            combinations_in_test = len(test_specs)

            # Create progress callback for this test
            engine_callback = make_callback_func(test_id, combinations_in_test, completed_before)

            result = engine.execute_test(test_id, specs, total_combinations, completed_before, engine_callback)

            if result['success']:
                # Save results CSV
                results_path = engine.save_results(test_id, result['results'])
                # Save statistics TXT
                stats_path = engine.save_statistics(test_id, result['stats'], result['results'])

                execution_results[test_id] = {
                    'success': True,
                    'results_count': len(result['results']),
                    'duration': result['stats']['duration_seconds'],
                    'results_file': os.path.basename(results_path),
                    'stats_file': os.path.basename(stats_path),
                    'results_path': results_path,
                    'stats_path': stats_path
                }

                print(f"✅ Test {test_id} completed: {len(result['results'])} results in {result['stats']['duration_seconds']:.2f}s")
                completed_before += combinations_in_test
            else:
                execution_results[test_id] = {
                    'success': False,
                    'error': result['error']
                }
                print(f"❌ Test {test_id} failed: {result['error']}")
                completed_before += combinations_in_test

        # Mark execution as complete
        unattended_progress['is_running'] = False
        unattended_progress['execution_results'] = execution_results
        unattended_progress['output_directory'] = engine.output_dir

    except Exception as e:
        print(f"Execution error: {str(e)}")
        unattended_progress['is_running'] = False
