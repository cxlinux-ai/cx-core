import sys
import os
import unittest
import time
import platform
import io
from contextlib import redirect_stdout, redirect_stderr

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'cortex'))
sys.path.insert(0, os.path.join(project_root, 'LLM'))
sys.path.insert(0, os.path.join(project_root, 'src'))

tests_dir = os.path.dirname(__file__)
sys.path.insert(0, tests_dir)

from test_cli import TestCortexCLI
from test_coordinator import TestInstallationStep, TestInstallationCoordinator, TestInstallDocker
from test_interpreter import TestCommandInterpreter
from test_hwprofiler import TestHardwareProfiler

is_windows = platform.system() == 'Windows'

if not is_windows:
    from test_sandbox_executor import TestSandboxExecutor, TestSecurityFeatures


def check_api_key():
    """
    Pre-flight check: Verify API key is available and has quota.
    Returns (has_key, error_message)
    """
    openai_key = os.environ.get('OPENAI_API_KEY')
    anthropic_key = os.environ.get('ANTHROPIC_API_KEY')
    
    if not openai_key and not anthropic_key:
        return False, "No API key found. Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable."
    
    # Try to verify the key has quota by making a minimal test call
    try:
        if openai_key:
            import openai
            client = openai.OpenAI(api_key=openai_key)
            # Make a minimal test call with gpt-3.5-turbo (more widely available)
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "test"}],
                max_tokens=5
            )
            return True, None
        elif anthropic_key:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            # Make a minimal test call
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=5,
                messages=[{"role": "user", "content": "test"}]
            )
            return True, None
    except Exception as e:
        error_str = str(e).lower()
        if 'quota' in error_str or 'insufficient' in error_str or 'exceeded' in error_str:
            return False, f"API key exists but has no quota. Add credits to your API provider account.\nError: {str(e)}"
        elif 'authentication' in error_str or 'invalid' in error_str or 'unauthorized' in error_str:
            return False, f"API key is invalid or expired. Please check your API key.\nError: {str(e)}"
        else:
            return False, f"API key validation failed: {str(e)}"
    
    return True, None


def run_test_suite(test_class, test_name):
    suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
    
    output_buffer = io.StringIO()
    error_buffer = io.StringIO()
    
    with redirect_stdout(output_buffer), redirect_stderr(error_buffer):
        runner = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0)
        result = runner.run(suite)
    
    status = "[PASSED]" if result.wasSuccessful() else "[FAILED]"
    tests_run = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    
    if result.wasSuccessful():
        print(f"{test_name} --- {status} ({tests_run} tests)")
    else:
        print(f"{test_name} --- {status} ({tests_run} tests, {failures} failures, {errors} errors)")
        for failure in result.failures:
            test_desc = str(failure[0]).split()[0]
            error_msg = failure[1].strip().split('\n')[-1] if failure[1].strip() else "Unknown error"
            print(f"  FAIL: {test_desc} - {error_msg}")
        for error in result.errors:
            test_desc = str(error[0]).split()[0]
            error_msg = error[1].strip().split('\n')[-1] if error[1].strip() else "Unknown error"
            print(f"  ERROR: {test_desc} - {error_msg}")
    
    return result.wasSuccessful()


def main():
    print("=" * 60)
    print("CORTEX TEST SUITE")
    print("=" * 60)
    print()
    
    # Pre-flight API key check
    print("[INFO] Checking API credentials...")
    has_key, error_msg = check_api_key()
    
    if not has_key:
        print("[FAILED] API KEY CHECK FAILED")
        print()
        print(f"[WARNING] {error_msg}")
        print()
        print("=" * 60)
        print("ALL TESTS SKIPPED")
        print("=" * 60)
        print()
        print("-- Required Action:")
        print("  • Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable")
        print("  • Ensure your API key has available credits/quota")
        print()
        print("-- How to set API key:")
        print("  Linux/Mac:  export OPENAI_API_KEY='your-key-here'")
        print("  Windows:    set OPENAI_API_KEY=your-key-here")
        print("  PowerShell: $env:OPENAI_API_KEY='your-key-here'")
        print()
        print("-- Get API keys:")
        print("  OpenAI:    https://platform.openai.com/api-keys")
        print("  Anthropic: https://console.anthropic.com/settings/keys")
        print()
        return 1
    
    print("[SUCCESS] API key validated successfully")
    print()
    
    start_time = time.time()
    
    test_suites = [
        (TestCortexCLI, "test_cli"),
        (TestInstallationStep, "test_coordinator_step"),
        (TestInstallationCoordinator, "test_coordinator"),
        (TestInstallDocker, "test_docker_install"),
        (TestCommandInterpreter, "test_interpreter"),
        (TestHardwareProfiler, "test_hwprofiler"),
    ]
    
    if not is_windows:
        test_suites.extend([
            (TestSandboxExecutor, "test_sandbox_executor"),
            (TestSecurityFeatures, "test_security_features"),
        ])
    
    results = []
    for test_class, test_name in test_suites:
        success = run_test_suite(test_class, test_name)
        results.append(success)
    
    elapsed_time = time.time() - start_time
    
    print()
    print("=" * 60)
    total_tests = len(results)
    passed_tests = sum(results)
    failed_tests = total_tests - passed_tests
    
    print(f"Total: {total_tests} | Passed: {passed_tests} | Failed: {failed_tests}")
    print(f"Time: {elapsed_time:.2f}s")
    print("=" * 60)
    
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
