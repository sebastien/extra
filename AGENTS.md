# Agent Guidelines for Extra HTTP Framework

## Build/Test/Lint Commands
- **Build**: `make compile` (compiles with mypyc)
- **Lint**: `make lint` or `make check-flakes` 
- **Type check**: `make check-strict` (runs mypy --strict on all files)
- **Security audit**: `make check-bandit`
- **Full check**: `make check` (runs bandit, flake8, mypy)
- **CI pipeline**: `make ci` (check + test)
- **Single test**: `python tests/unit-parser-http.py` (no test framework, direct execution)

## Code Style Guidelines
- **Indentation**: Use tabs (configured in .pylintrc)
- **Imports**: Relative imports within package (e.g., `from .model import Service`)
- **Type hints**: Full type annotations required, use `typing` module generics
- **Naming**: snake_case for functions/variables, PascalCase for classes
- **Error handling**: Use custom exception classes, log with `utils.logging`
- **Line length**: Flexible (flake8 ignores E501)
- **Comments**: Use `# NOQA` for intentional lint suppressions
- **Docstrings**: Brief docstrings for public methods
- **File endings**: Always end files with `# EOF` comment

## Architecture Notes
- HTTP framework with async/await support
- Service-based architecture with routing decorators
- Uses dataclasses with `slots=True` for performance
- Custom HTTP parser and response handling