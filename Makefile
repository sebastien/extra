PYTHON=python
PATH_SOURCES_PY=src/py

audit: require-py-bandit
	bandit -r $(PATH_SOURCES_PY)

require-py-%:
	@if [ -z "$$(which '$*' 2> /dev/null)" ]; then $(PYTHON) -mpip install --user --upgrade '$*'; fi

.PHONY: audit
