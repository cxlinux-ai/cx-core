# Cortex Test Suite

This directory contains all test files and the main test runner for the Cortex project.

## Prerequisites

**[WARNING] API Key Required**: Tests require a valid API key with available quota:
- Set `OPENAI_API_KEY` environment variable, OR
- Set `ANTHROPIC_API_KEY` environment variable
- Ensure your API key has available credits/quota

The test suite performs a pre-flight check and will **skip all tests** if:
- No API key is found
- API key is invalid or expired
- API key has no quota/credits available

## Running Tests

### Using the CLI command:
```bash
# Set API key first
export OPENAI_API_KEY='your-key-here'  # Linux/Mac
set OPENAI_API_KEY=your-key-here       # Windows CMD
$env:OPENAI_API_KEY='your-key-here'    # Windows PowerShell

# Then run tests
cortex --test
```

### Direct execution:
```bash
python tests/run_all_tests.py
```

## API Key Validation

Before running any tests, the suite validates:
1. **API key exists** - Checks for OPENAI_API_KEY or ANTHROPIC_API_KEY
2. **API key is valid** - Makes a minimal test API call
3. **API key has quota** - Verifies credits/quota are available

If validation fails, all tests are skipped with a clear error message.

## Test Philosophy

**Real API Testing**: Tests use actual API calls (not mocks) to ensure:
- The LLM integration works correctly
- Command interpretation produces valid results
- Error handling works with real API responses
- The system behaves correctly in production scenarios

This approach ensures the AI-powered features actually work, not just that the code structure is correct.

## Test Structure

The test runner executes all test files in the following order:

1. `test_cli` - CLI interface tests
2. `test_coordinator_step` - Installation step tests
3. `test_coordinator` - Installation coordinator tests
4. `test_docker_install` - Docker installation tests
5. `test_interpreter` - Command interpreter tests
6. `test_hwprofiler` - Hardware profiler tests
7. `test_sandbox_executor` - Sandbox executor tests (Unix only)
8. `test_security_features` - Security feature tests (Unix only)

## Output Format

Each test suite shows count of tests executed:
```
test_cli --- [PASSED] (22 tests)
test_coordinator --- [PASSED] (16 tests)
```

When tests fail, specific failures are shown:
```
test_cli --- [FAILED] (22 tests, 1 failures, 0 errors)
  FAIL: test_install_no_api_key - AssertionError: Expected 1, got 0
```

## Test Files

All test files are located in the `tests/` directory:
- `tests/test_cli.py` - CLI interface tests
- `tests/test_coordinator.py` - Coordinator and installation step tests
- `tests/test_interpreter.py` - Command interpreter tests
- `tests/test_hwprofiler.py` - Hardware profiler tests
- `tests/test_sandbox_executor.py` - Sandbox executor and security tests (Unix only)
- `tests/run_all_tests.py` - Main test runner

## Platform Support

Some tests are platform-specific:
- Windows: Runs 6 test suites (excludes sandbox executor tests)
- Unix/Linux: Runs all 8 test suites
