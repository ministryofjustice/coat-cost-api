# Tests

Test suite for `coat-cost-api`

> Runs from the project root (`testpaths` is configured in `pyproject.toml`, so no need to `cd` into `tests/`)

## Running tests locally
```
uv run pytest
```
Runs the whole suite with no output beyond pass/fail.

To also see a coverage report:
```
uv run pytest --cov=app
```
## Structure

Tests mirror the `app/` folder structure. Each source file gets a matching `test_*.py` file, one level deep under `v1/`.


```
tests/
├── __init__.py
├── conftest.py # currently empty. should be populated during integration test 
└── v1
    ├── __init__.py
    ├── api
    │   ├── __init__.py
    │   └── test_daily.py # integration tests pending
    ├── schemas
    │   ├── __init__.py
    │   └── test_daily.py
    └── services
        ├── __init__.py
        ├── test_athena.py
        └── query_builder
            ├── __init__.py
            ├── test_daily.py
            └── test_escape_literal.py
```