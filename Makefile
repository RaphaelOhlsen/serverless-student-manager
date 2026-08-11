PYTHON ?= python3.13
VENV ?= .venv
VENV_BIN := $(VENV)/bin
NPM ?= npm
TERRAFORM ?= terraform
TFLINT ?= tflint
TERRAFORM_DIR := infra/bootstrap

PYTHON_DIRS := backend tools

.PHONY: setup format format-check lint typecheck test coverage security check \
	terraform-init terraform-format terraform-format-check terraform-validate \
	terraform-test tflint-init terraform-lint terraform-check

setup:
	@$(PYTHON) -c 'import sys; assert sys.version_info[:2] == (3, 13), "Python 3.13 is required"'
	$(PYTHON) -m venv $(VENV)
	$(VENV_BIN)/python -m pip install --upgrade pip
	$(VENV_BIN)/python -m pip install -r requirements-dev.txt
	$(NPM) ci

format:
	$(VENV_BIN)/ruff format $(PYTHON_DIRS)
	$(VENV_BIN)/ruff check --fix $(PYTHON_DIRS)
	$(NPM) run format
	$(MAKE) terraform-format

format-check:
	$(VENV_BIN)/ruff format --check $(PYTHON_DIRS)
	$(NPM) run format:check
	$(MAKE) terraform-format-check

lint:
	$(VENV_BIN)/ruff check $(PYTHON_DIRS)
	$(NPM) run lint
	$(MAKE) terraform-lint

typecheck:
	@if find $(PYTHON_DIRS) -type f -name '*.py' -print -quit | grep -q .; then \
		$(VENV_BIN)/mypy $(PYTHON_DIRS); \
	else \
		echo "NOT APPLICABLE: no Python source files"; \
	fi
	@if find frontend -type f -name 'tsconfig*.json' -print -quit | grep -q .; then \
		$(NPM) exec tsc -- --noEmit; \
	else \
		echo "NOT APPLICABLE: no TypeScript configuration"; \
	fi

test:
	@if find $(PYTHON_DIRS) -type f \( -name 'test_*.py' -o -name '*_test.py' \) -print -quit | grep -q .; then \
		$(VENV_BIN)/pytest; \
	else \
		echo "NOT APPLICABLE: no Python tests"; \
	fi
	@if find frontend -type f \( -name '*.test.ts' -o -name '*.test.tsx' -o -name '*.spec.ts' -o -name '*.spec.tsx' \) -print -quit | grep -q .; then \
		$(NPM) exec vitest -- run; \
	else \
		echo "NOT APPLICABLE: no frontend tests"; \
	fi
	$(MAKE) terraform-test

coverage:
	@if find $(PYTHON_DIRS) -type f \( -name 'test_*.py' -o -name '*_test.py' \) -print -quit | grep -q .; then \
		$(VENV_BIN)/pytest --cov --cov-report=term-missing --cov-fail-under=80; \
	else \
		echo "NOT APPLICABLE: no Python tests for coverage"; \
	fi
	@if find frontend -type f \( -name '*.test.ts' -o -name '*.test.tsx' -o -name '*.spec.ts' -o -name '*.spec.tsx' \) -print -quit | grep -q .; then \
		echo "NOT APPLICABLE: frontend coverage configuration belongs to the frontend task"; \
	else \
		echo "NOT APPLICABLE: no frontend tests for coverage"; \
	fi

security:
	$(VENV_BIN)/pip-audit --requirement requirements-dev.txt
	$(NPM) audit --audit-level=high

terraform-init:
	$(TERRAFORM) -chdir=$(TERRAFORM_DIR) init -backend=false

terraform-format:
	$(TERRAFORM) -chdir=$(TERRAFORM_DIR) fmt -recursive

terraform-format-check:
	$(TERRAFORM) -chdir=$(TERRAFORM_DIR) fmt -check -recursive

terraform-validate:
	$(TERRAFORM) -chdir=$(TERRAFORM_DIR) validate

terraform-test:
	$(TERRAFORM) -chdir=$(TERRAFORM_DIR) test

tflint-init:
	$(TFLINT) --chdir=$(TERRAFORM_DIR) --config=.tflint.hcl --init

terraform-lint:
	$(TFLINT) --chdir=$(TERRAFORM_DIR) --config=.tflint.hcl

terraform-check: terraform-format-check terraform-validate terraform-test terraform-lint

check: format-check lint typecheck test coverage security terraform-validate
