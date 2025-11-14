# Testing Strategy

Cortex relies on a mix of fast unit tests and Docker-backed integration tests to
validate the full installation workflow. This guide explains how to run the
suites locally and in CI.

## Test Suites

| Suite | Location | Purpose | Invocation |
|-------|----------|---------|------------|
| Unit | `test/*.py` | Validate individual modules (CLI, coordinator, interpreter). | `python test/run_all_tests.py` |
| Integration | `test/integration/*.py` | Exercise end-to-end scenarios inside disposable Docker containers. | `python -m unittest test.integration.test_end_to_end` |

## Running Tests Locally

1. **Prepare the environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install --upgrade pip
   pip install -r LLM/requirements.txt
   pip install -r src/requirements.txt
   pip install -e .
   ```

2. **Unit tests**
   ```bash
   python test/run_all_tests.py
   ```
   Use the fake provider to avoid external API calls when necessary:
   ```bash
   CORTEX_PROVIDER=fake python test/run_all_tests.py
   ```

3. **Integration tests** (requires Docker)
   ```bash
   python -m unittest test.integration.test_end_to_end
   ```
   Customise the Docker image with `CORTEX_INTEGRATION_IMAGE` if you need a
   different base image:
   ```bash
   CORTEX_INTEGRATION_IMAGE=python:3.12-slim python -m unittest test.integration.test_end_to_end
   ```

## Continuous Integration Recommendations

- Run unit tests on every pull request.
- Schedule integration tests nightly or on demand using a GitHub Actions job
  with the `docker` service enabled.
- Fail the workflow if docstring coverage (tracked by CodeRabbit) drops below
  80%.
- Publish the HTML report from `python -m coverage html` when running coverage
  builds to assist reviewers.

## Troubleshooting

- **Docker not available** – Integration tests are skipped automatically when
  the Docker CLI is missing. Install Docker Desktop (macOS/Windows) or the
  `docker` package (Linux) to enable them.
- **Missing API keys** – Set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or
  `KIMI_API_KEY` as appropriate. For offline development use
  `CORTEX_PROVIDER=fake` plus optional `CORTEX_FAKE_COMMANDS`.
- **Docstring coverage failures** – Add module/class/function docstrings. The
  CodeRabbit gate requires 80% coverage.

By following this guide, contributors can quickly validate their changes and
ship reliable improvements to Cortex.
