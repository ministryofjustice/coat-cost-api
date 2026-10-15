import pytest
from fastapi.testclient import TestClient

from app.main import app

DAILY_URL = "/api/v1/cloud-cost/daily"
VALID_DAILY_PARAMS = {
    "start_usage_date": "2025-09-01",
    "end_usage_date": "2025-09-02",
    "region": "eu-west-2",
}


@pytest.fixture
def client() -> TestClient:
    """The real COAT app. Only used for requests that get rejected (or /health),
    so these tests never reach Athena"""
    return TestClient(app)


def test_health_does_not_require_auth(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_daily_rejects_request_without_credentials(client: TestClient) -> None:
    response = client.get(DAILY_URL, params=VALID_DAILY_PARAMS)
    assert response.status_code == 401


def test_daily_returns_401_not_422_for_invalid_params_without_credentials(
    client: TestClient,
) -> None:
    # no categorical params, so this would be a 422 if auth didn't run first
    invalid_params = {
        "start_usage_date": "2025-09-01",
        "end_usage_date": "2025-09-02",
    }
    response = client.get(DAILY_URL, params=invalid_params)
    assert response.status_code == 401
