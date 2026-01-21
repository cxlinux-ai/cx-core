# Cortex Linux - Developer Makefile
# Usage: make [target]

.PHONY: dev test lint format check clean help deb deb-deps deb-install deb-clean

PYTHON ?= python3

help:
	@echo "Cortex Linux - Development Commands"
	@echo ""
	@echo "  make dev         Install development dependencies"
	@echo "  make test        Run test suite"
	@echo "  make lint        Run linters (ruff, black check)"
	@echo "  make format      Auto-format code"
	@echo "  make check       Run all checks (format + lint + test)"
	@echo "  make clean       Remove build artifacts"
	@echo ""
	@echo "Debian Packaging:"
	@echo "  make deb-deps    Install .deb build dependencies"
	@echo "  make deb         Build .deb package"
	@echo "  make deb-install Build and install .deb package"
	@echo "  make deb-clean   Clean debian build artifacts"
	@echo ""

dev:
	$(PYTHON) -m pip install -U pip
	$(PYTHON) -m pip install -e ".[dev]"
	@echo "✅ Dev environment ready"

test:
	$(PYTHON) -m pytest tests/ -v
	@echo "✅ Tests passed"

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m black --check .
	@echo "✅ Linting passed"

format:
	$(PYTHON) -m black .
	$(PYTHON) -m ruff check --fix .
	@echo "✅ Code formatted"

check: format lint test
	@echo "✅ All checks passed"

clean:
	rm -rf build/ dist/ *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "Cleaned"

# Debian packaging targets
deb-deps:
	./scripts/build-deb.sh --install-deps

deb:
	./scripts/build-deb.sh --no-sign

deb-install: deb
	sudo dpkg -i dist/*.deb || sudo apt-get install -f -y
	@echo "Package installed"

deb-clean:
	./scripts/build-deb.sh --clean
