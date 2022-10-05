PYTHON=python
PATH_SOURCES_PY=src/py
SOURCES_PY:=$(wildcard $(PATH_SOURCES_PY)/*.py $(PATH_SOURCES_PY)/*/*.py $(PATH_SOURCES_PY)/*/*/*.py $(PATH_SOURCES_PY)/*/*/*/*.py)

audit: require-py-bandit
	bandit -r $(PATH_SOURCES_PY)

compile:
	mypyc $(SOURCES_PY)

lint:
	pylint $(SOURCES_PY)

format:
	black $(SOURCES_PY)

require-py-%:
	@if [ -z "$$(which '$*' 2> /dev/null)" ]; then $(PYTHON) -mpip install --user --upgrade '$*'; fi

.PHONY: audit
# EOF
