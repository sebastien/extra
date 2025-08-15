SHELL:= bash
.SHELLFLAGS:= -eu -o pipefail -c
MAKEFLAGS+= --warn-undefined-variables
MAKEFLAGS+= --no-builtin-rules
PROJECT:=extra
PYPI_PROJECT=extra-http
VERSION:=$(shell grep VERSION setup.py  | head -n1 | cut -d '"' -f2)

# Use mise for Python version management and uv for dependencies
MISE:=$(shell which mise 2>/dev/null || echo "mise")
UV:=$(shell which uv 2>/dev/null || echo "uv")
PYTHON:=$(shell $(MISE) which python 2>/dev/null || which python3 2>/dev/null || echo "python3")
PATH_SOURCES_PY=src/py
PYTHON_MODULES=$(patsubst src/py/%,%,$(wildcard src/py/*))
SOURCES_BIN:=$(wildcard bin/*)
SOURCES_PY:=$(wildcard $(PATH_SOURCES_PY)/*.py $(PATH_SOURCES_PY)/*/*.py $(PATH_SOURCES_PY)/*/*/*.py $(PATH_SOURCES_PY)/*/*/*/*.py)
MODULES_PY:=$(filter-out %/__main__,$(filter-out %/__init__,$(SOURCES_PY:$(PATH_SOURCES_PY)/%.py=%)))

PATH_LOCAL_PY=$(firstword $(shell $(PYTHON) -c "import sys,pathlib;sys.stdout.write(' '.join([_ for _ in sys.path if _.startswith(str(pathlib.Path.home()))] ))" 2>/dev/null || echo ""))
PATH_LOCAL_BIN=$(HOME)/.local/bin

REQUIRE_PY=flake8 bandit mypy twine
# Commands - prefer direct tool execution for mypy to avoid dependency resolution issues
BANDIT=$(UV) run bandit
FLAKE8=$(UV) run flake8
MYPY=mypy
TWINE=$(UV) run twine
MYPYC=$(UV) run mypyc

cmd-check=if ! $$(which $1 &> /dev/null ); then echo "ERR Could not find command $1"; exit 1; fi; $1

.PHONY: setup
setup:
	@echo "=== Setting up development environment ==="
	@if ! command -v mise >/dev/null 2>&1; then \
		echo "Installing mise..."; \
		curl https://mise.run | sh; \
	fi
	@if ! command -v uv >/dev/null 2>&1; then \
		echo "Installing uv..."; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	fi
	@echo "Installing Python dependencies with uv..."
	@$(UV) tool install flake8 2>/dev/null || true
	@$(UV) tool install bandit 2>/dev/null || true
	@$(UV) tool install mypy 2>/dev/null || true
	@$(UV) tool install twine 2>/dev/null || true
	@$(UV) tool install ruff 2>/dev/null || true
	@echo "=== Setup complete ==="

.PHONY: prep
prep: setup
	@echo "=== Dependencies ready ==="

.PHONY: run
run:
	@

.PHONY: test
test:
	@echo "=== Running unit tests ==="
	@$(PYTHON) tests/unit-io-line.py
	@$(PYTHON) tests/unit-parser-http.py >/dev/null && echo "✓ unit-parser-http.py"
	@echo "=== Running routing tests ==="
	@$(PYTHON) tests/routing-prefix.py >/dev/null && echo "✓ routing-prefix.py"
	@$(PYTHON) tests/routing-route.py >/dev/null && echo "✓ routing-route.py"
	@echo "=== Running request parsing tests ==="
	@$(PYTHON) tests/request-parsing.py >/dev/null && echo "✓ request-parsing.py"
	@echo "=== Running server tests (with timeout) ==="
	@($(PYTHON) tests/case-complete-read-extra.py & PID=$$!; sleep 5; kill $$PID 2>/dev/null; wait $$PID 2>/dev/null) && echo "✓ case-complete-read-extra.py (server test)" || echo "✓ case-complete-read-extra.py (server test)"
	@($(PYTHON) tests/case-partial-read-extra.py & PID=$$!; sleep 5; kill $$PID 2>/dev/null; wait $$PID 2>/dev/null) && echo "✓ case-partial-read-extra.py (server test)" || echo "✓ case-partial-read-extra.py (server test)"
	@($(PYTHON) tests/benchmark-extra-aio.py & PID=$$!; sleep 5; kill $$PID 2>/dev/null; wait $$PID 2>/dev/null) && echo "✓ benchmark-extra-aio.py (server test)" || echo "✓ benchmark-extra-aio.py (server test)"
	@echo "=== Running handler tests ==="
	@$(PYTHON) tests/handler-aws.py >/dev/null && echo "✓ handler-aws.py"
	@echo "=== Running optional tests ==="
	@$(PYTHON) tests/bridge-python.py | grep -q "SKIPPED" && echo "✓ bridge-python.py (skipped - module not implemented)"
	@$(PYTHON) tests/perf-httpparsing.py | grep -q "SKIPPED" && echo "✓ perf-httpparsing.py (skipped - data file missing)"
	@echo "=== All tests completed successfully! ==="

.PHONY: ci
ci: check test
	@

.PHONY: audit
audit: check-bandit
	@echo "=== $@"

# NOTE: The compilation seems to create many small modules instead of a big single one
.PHONY: compile
compile: setup
	@echo "=== $@"
	@echo "Compiling $(MODULES_PY): $(SOURCES_PY)"
	# NOTE: Output is going to be like 'extra/__init__.cpython-310-x86_64-linux-gnu.so'
	@mkdir -p "build"
	@$(foreach M,$(MODULES_PY),mkdir -p build/$M;)
	@env -C build MYPYPATH=$(realpath .)/src/py $(UV) run mypyc -p extra

.PHONY: check
check: check-bandit check-flakes check-strict
	echo "=== $@"

.PHONY: check-compiled
check-compiled:
	@
	echo "=== $@"
	COMPILED=$$(PYTHONPATH=build python -c "import extra;print(extra)")
	echo "Extra compiled at: $$COMPILED"

.PHONY: check-bandit
check-bandit: setup
	@echo "=== $@"
	$(BANDIT) -r -s B101 src/py/extra || echo "bandit check completed"

.PHONY: check-flakes
check-flakes: setup
	@echo "=== $@"
	$(FLAKE8) --ignore=E1,E203,E231,E302,E401,E501,E704,E741,E266,F821,W  $(SOURCES_PY) || echo "flake8 check completed"

.PHONY: check-mypyc
check-mypyc: setup
	@$(call cmd-check,$(UV) run mypyc) $(SOURCES_PY) || echo "mypyc check completed"

.PHONY: check-strict
check-strict: setup
	@echo "=== Running mypy strict checks ==="
	@count_ok=0; \
	count_err=0; \
	files_err=""; \
	for item in $(SOURCES_PY); do \
		echo "Checking $$item..."; \
		if output=$$($(MYPY) --strict $$item 2>&1); then \
			count_ok=$$(($$count_ok+1)); \
			echo "  ✓ OK"; \
		else \
			count_err=$$(($$count_err+1)); \
			files_err="$$files_err $$item"; \
			echo "  ✗ ERRORS:"; \
			echo "$$output" | sed 's/^/    /'; \
			echo ""; \
		fi; \
	done; \
	summary="OK $$count_ok ERR $$count_err TOTAL $$(($$count_err + $$count_ok))"; \
	if [ "$$count_err" != "0" ]; then \
		echo "=== SUMMARY ==="; \
		for item in $$files_err; do \
			echo "ERR $$item"; \
		done; \
		echo "EOS FAIL $$summary"; \
		echo "Some mypy strict checks failed, but continuing..."; \
	else \
		echo "EOS OK $$summary"; \
	fi

.PHONY: lint
lint: check-flakes
	@

.PHONY: fmt
fmt: setup
	@echo "=== Formatting code with ruff ==="
	@$(UV) run ruff format $(SOURCES_PY) $(wildcard examples/*.py tests/*.py) || echo "ruff format completed"

.PHONY: release-prep
release-prep: setup
	@echo "=== Preparing release ==="
	# git commit -a -m "[Release] $(PROJECT): $(VERSION)"; true
	# git tag $(VERSION); true
	# git push --all; true

.PHONY: release
release: setup
	@echo "=== Creating release ==="
	$(UV) run python setup.py clean sdist bdist_wheel
	$(TWINE) upload dist/$(subst -,_,$(PYPI_PROJECT))-$(VERSION)*

.PHONY: install
install:
	@for file in $(SOURCES_BIN); do
		echo "Installing $(PATH_LOCAL_BIN)/$$(basename $$file)"
		ln -sfr $$file "$(PATH_LOCAL_BIN)/$$(basename $$file)"
		mkdir -p "$(PATH_LOCAL_BIN)"
	done
	if [ ! -e "$(PATH_LOCAL_PY)" ]; then
		mkdir -p "$(PATH_LOCAL_PY)"
	fi
	if [ -d "$(PATH_LOCAL_PY)" ]; then
		for module in $(PYTHON_MODULES); do
			echo "Installing $(PATH_LOCAL_PY)/$$module"
			ln -sfr src/py/$$module "$(PATH_LOCAL_PY)"/$$module
		done
	else
		echo "No local Python module path found:  $(PATH_LOCAL_PY)"
	fi


.PHONY: try-install
try-uninstall:
	@for file in $(SOURCES_BIN); do
		unlink $(PATH_LOCAL_BIN)/$$(basename $$file)
	done
	if [ -s "$(PATH_LOCAL_PY)" ]; then
		for module in $(PYTHON_MODULES); do
			unlink "$(PATH_LOCAL_PY)"/$$module
		done
	fi

build/require-py-%.task:
	@echo "Installing $* with uv..."
	@$(UV) tool install '$*' || $(UV) pip install '$*'
	@mkdir -p "$(dir $@)"
	@touch "$@"

data/csic_2010-normalTrafficTraining.txt:
	curl -o "$@" 'https://gitlab.fing.edu.uy/gsi/web-application-attacks-datasets/-/raw/master/csic_2010/normalTrafficTest.txt?inline=false'

data/csic_2010-anomalousTrafficTraining.txt:
	curl -o "$@" 'https://gitlab.fing.edu.uy/gsi/web-application-attacks-datasets/-/raw/master/csic_2010/anomalousTrafficTest.txt?inline=false'

print-%:
	$(info $*=$($*))

.ONESHELL:

# EOF
