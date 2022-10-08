PYTHON=python
PATH_SOURCES_PY=src/py
SOURCES_PY:=$(wildcard $(PATH_SOURCES_PY)/*.py $(PATH_SOURCES_PY)/*/*.py $(PATH_SOURCES_PY)/*/*/*.py $(PATH_SOURCES_PY)/*/*/*/*.py)
MODULES_PY:=$(filter-out %/__main__,$(filter-out %/__init__,$(SOURCES_PY:$(PATH_SOURCES_PY)/%.py=%)))

audit: require-py-bandit
	bandit -r $(PATH_SOURCES_PY)

# NOTE: The compilation seems to create many small modules instead of a big single one
compile:
	# NOTE: Output is going to be like 'extra/__init__.cpython-310-x86_64-linux-gnu.so'
	$(foreach M,$(MODULES_PY),mkdir -p build/$M;)
	env -C build MYPYPATH=$(realpath .)/src/py mypyc -p extra

lint:
	pylint $(SOURCES_PY)

format:
	black $(SOURCES_PY)

require-py-%:
	@if [ -z "$$(which '$*' 2> /dev/null)" ]; then $(PYTHON) -mpip install --user --upgrade '$*'; fi

print-%:
	$(info $*=$($*))

.PHONY: audit
# EOF
