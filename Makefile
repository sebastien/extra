SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
MAKEFLAGS += --warn-undefined-variables
MAKEFLAGS += --no-builtin-rules

PYTHON=python
PATH_SOURCES_PY=src/py
PYTHON_MODULES=$(patsubst src/py/%,%,$(wildcard src/py/*))
SOURCES_BIN:=$(wildcard bin/*)
SOURCES_PY:=$(wildcard $(PATH_SOURCES_PY)/*.py $(PATH_SOURCES_PY)/*/*.py $(PATH_SOURCES_PY)/*/*/*.py $(PATH_SOURCES_PY)/*/*/*/*.py)
MODULES_PY:=$(filter-out %/__main__,$(filter-out %/__init__,$(SOURCES_PY:$(PATH_SOURCES_PY)/%.py=%)))

PATH_LOCAL_PY=$(firstword $(shell python -c "import sys,pathlib;sys.stdout.write(' '.join([_ for _ in sys.path if _.startswith(str(pathlib.Path.home()))] ))"))
PATH_LOCAL_BIN=$(HOME)/.local/bin


audit: require-py-bandit
	bandit -r $(PATH_SOURCES_PY)

# NOTE: The compilation seems to create many small modules instead of a big single one
compile:
	@
	echo "Compiling $(MODULES_PY): $(SOURCES_PY)"
	# NOTE: Output is going to be like 'extra/__init__.cpython-310-x86_64-linux-gnu.so'

	mkdir -p "build"
	$(foreach M,$(MODULES_PY),mkdir -p build/$M;)
	env -C build MYPYPATH=$(realpath .)/src/py mypyc -p extra

check: lint
	@

lint:
	@flake8 --ignore=E1,E202,E203,E231,E227,E252,E302,E401,E501,E741,F821,W $(SOURCES_PY)

format:
	@black $(SOURCES_PY)

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


try-uninstall:
	@for file in $(SOURCES_BIN); do
		unlink $(PATH_LOCAL_BIN)/$$(basename $$file)
	done
	if [ -s "$(PATH_LOCAL_PY)" ]; then
		for module in $(PYTHON_MODULES); do
			unlink "$(PATH_LOCAL_PY)"/$$module
		done
	fi

require-py-%:
	@if [ -z "$$(which '$*' 2> /dev/null)" ]; then $(PYTHON) -mpip install --user --upgrade '$*'; fi

data/csic_2010-normalTrafficTraining.txt:
	curl -o "$@" 'https://gitlab.fing.edu.uy/gsi/web-application-attacks-datasets/-/raw/master/csic_2010/normalTrafficTest.txt?inline=false'

data/csic_2010-anomalousTrafficTraining.txt:
	curl -o "$@" 'https://gitlab.fing.edu.uy/gsi/web-application-attacks-datasets/-/raw/master/csic_2010/anomalousTrafficTest.txt?inline=false'

print-%:
	$(info $*=$($*))

.PHONY: audit
.ONESHELL:
# EOF
#
