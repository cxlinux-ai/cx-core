# Contribution Guide

Thank you for your interest in contributing to **Cortex**. This document explains the
project workflow, coding standards, and review expectations so that every pull
request is straightforward to review and merge.

## Getting Started

1. **Fork and clone the repository.**
2. **Create a feature branch** from `main` using a descriptive name, for example
   `issue-40-kimi-k2`.
3. **Install dependencies** in a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install --upgrade pip
   pip install -r LLM/requirements.txt
   pip install -r src/requirements.txt
   pip install -e .
   ```
4. **Run the full test suite** (`python test/run_all_tests.py`) to ensure your
   environment is healthy before you start coding.

## Coding Standards

- **Type hints and docstrings** are required for all public functions, classes,
  and modules. CodeRabbit enforces an 80% docstring coverage threshold.
- **Formatting** follows `black` (line length 100) and `isort` ordering. Please run:
  ```bash
  black .
  isort .
  ```
- **Linting** uses `ruff`. Address warnings locally before opening a pull request.
- **Logging and messages** must use the structured status labels (`[INFO]`, `[PLAN]`,
  `[EXEC]`, `[SUCCESS]`, `[ERROR]`, etc.) to provide a consistent CLI experience.
- **Secrets** such as API keys must never be hard-coded or committed.
- **Dependency changes** must update both `LLM/requirements.txt` and any related
  documentation (`README.md`, `test.md`).

## Tests

- Unit tests live under `test/` and should be added or updated alongside code
  changes.
- Integration tests live under `test/integration/` and are designed to run inside
  Docker. Use the helper utilities in `test/integration/docker_utils.py` to keep
  the tests concise and reliable.
- Ensure that every new feature or regression fix includes corresponding test
  coverage. Submissions without meaningful tests will be sent back for revision.
- Before requesting review, run:
  ```bash
  python test/run_all_tests.py
  ```
  Optionally, include `CORTEX_PROVIDER=fake` to avoid contacting external APIs.

## Pull Request Checklist

- Provide a **clear title** that references the issue being addressed.
- Include a **summary** of the change, **testing notes**, and **risk assessment**.
- Confirm that **CI passes** and that **docstring coverage** meets the required threshold.
- Link the pull request to the relevant GitHub issue (`Fixes #<issue-number>`).
- Be responsive to review feedback and keep discussions on-topic.

We appreciate your time and effort—welcome aboard!
