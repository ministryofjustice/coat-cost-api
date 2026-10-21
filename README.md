# COAT COST API - POC

Proof of Concept API for retrieving cloud cost data.

## Prerequisites (for dev)

- [uv](https://docs.astral.sh/uv/) for dependency management
- Docker, to run this in a container
- AWS SSO access to the `modernisation-platform-developer` profile, with
  permissions to query Athena in `coat-development`

## Running locally

### Option 1: plain uv

Make sure you have an active AWS SSO session first:

```bash
aws sso login --profile modernisation-platform-developer
export AWS_PROFILE=modernisation-platform-developer
```

Then install dependencies and run the app:

```bash
uv sync
uv run fastapi dev app/main.py
```

The API will be available at `http://localhost:8000`. Swagger/API docs are at
`http://localhost:8000/docs`.

### Option 2: Docker, via Makefile

```bash
make run
```

This builds the image and starts the container, mounting your `~/.aws`
folder into the container so it can use your existing SSO session. The API
will be available at `http://localhost:8000`.

Other Makefile targets:

```bash
make build   # build the image only
make stop    # stop the running container
make shell   # open a shell inside the running container
make health  # curl the /health endpoint
```
---

## curl commands to test /daily endpoints: 

### Health check - no AWS dependency
```
curl "http://localhost:8000/health"
```

### Single dimension filter - returns real data
```
curl "http://localhost:8000/api/v1/cloud-cost/daily?start_usage_date=2025-12-01&end_usage_date=2025-12-10&business_unit=HMPPS"
```

### Multiple dimensions at once
```
curl "http://localhost:8000/api/v1/cloud-cost/daily?start_usage_date=2025-12-01&end_usage_date=2025-12-10&business_unit=LAA&region=eu-west-2"
```

### Missing required categorical param - expect a clean 422
```
curl "http://localhost:8000/api/v1/cloud-cost/daily?start_usage_date=2025-12-01&end_usage_date=2025-12-10"
```

### Missing required date params entirely - expect a 422
```
curl "http://localhost:8000/api/v1/cloud-cost/daily?business_unit=HMPPS"
```

### Returns an empty result - handled gracefully
```
curl "http://localhost:8000/api/v1/cloud-cost/daily?start_usage_date=2025-12-01&end_usage_date=2025-12-10&business_unit=NOT_A_REAL_UNIT"
```

#### Concurrency check
```
time (
  curl -s -o /dev/null -w "req1: %{http_code} in %{time_total}s\n" "http://localhost:8000/api/v1/cloud-cost/daily?start_usage_date=2025-01-01&end_usage_date=2025-12-24&business_unit=HMPPS" &
  curl -s -o /dev/null -w "req2: %{http_code} in %{time_total}s\n" "http://localhost:8000/api/v1/cloud-cost/daily?start_usage_date=2025-01-01&end_usage_date=2025-12-24&business_unit=LAA" &
  wait
)
```


## Linting & type checking

This repo uses `ruff` for linting/import sorting and `mypy` for static type
checking, both configured in `pyproject.toml`.

```bash
uv run ruff check .    # lint
uv run ruff format .   # auto-format
uv run mypy            # type check
```

## Project structure

```
app/
├── main.py                — creates the app, registers global exception
│                             handlers, defines /health
├── api/v1/
│   ├── router.py           — collects all v1 endpoint routers
│   └── endpoints/
│       └── daily.py        — GET /api/v1/cloud-cost/daily
├── core/
│   └── config.py           — env-driven settings (region, database, etc.)
├── schemas/
│   └── daily.py             — Pydantic request/response shapes for /daily
└── services/
│    └── athena.py            — AthenaService, query builder, aioboto3 calls
│                             handlers, defines /health
├── tests                   - Full test suite (mirrors /app structure)
│   ├── README.md
│   ├── __init__.py
│   ├── conftest.py
│   └── v1/ 
└── docs/                      # Design approach documentation 
```

## Documentation

- [API Authentication approach](docs/api-authentication.md)
