SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
MAKEFLAGS += --warn-undefined-variables
MAKEFLAGS += --no-builtin-rules
PYTHON=python
SOURCES_PY:=$(wildcard fextra/*.py)
MODULES_PY:=$(filter-out %/__main__,$(filter-out %/__init__,$(SOURCES_PY:$(PATH_SOURCES_PY)/%.py=%)))

# NOTE: The compilation seems to create many small modules instead of a big single one
compile:
	# NOTE: Output is going to be like 'extra/__init__.cpython-310-x86_64-linux-gnu.so'
	mkdir -p build
	$(foreach M,$(MODULES_PY),mkdir -p build/$M;)
	env -C build MYPYPATH=$(realpath .) mypyc -p fextra

print-%:
	$(info $*=$($*))

.PHONY: audit
.ONESHELL:
# EOF
#
