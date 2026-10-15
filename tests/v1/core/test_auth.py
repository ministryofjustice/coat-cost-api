# tests for the API key check. Rewrite these when auth moves to JWT

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.auth import require_api_key
from app.core.config import settings

VALID_KEY = settings.api_key.get_secret_value()


@pytest.fixture
def client() -> TestClient:
    """A throwaway app with one protected route, so the auth logic
    can be tested on it's own without touching Athena/AWS"""
    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(require_api_key)])
    async def protected() -> dict[str, bool]:
        return {"ok": True}
    
    return TestClient(app)


def test_require_api_key_rejects_missing_header(client: TestClient) -> None:
    response = client.get("/protected")
    assert response.status_code == 401


def test_require_api_key_rejects_wrong_key(client: TestClient) -> None:
    response = client.get(
        "/protected", headers={"Authorization": "Bearer not-the-right-key"}
    )
    assert response.status_code == 401


def test_require_api_key_accepts_valid_key(client: TestClient) -> None:
    response = client.get(
        "/protected", headers={"Authorization": f"Bearer {VALID_KEY}"}
    )
    assert response.status_code == 200


def test_require_api_key_rejects_non_bearer_scheme(client: TestClient) -> None:
    response = client.get(
        "/protected", headers={"Authorization": f"Basic {VALID_KEY}"}
    )
    assert response.status_code == 401


def test_require_api_key_401_includes_www_authenticate_header(
    client: TestClient,
) -> None:
    response = client.get("/protected")
    assert response.headers["www-authenticate"] == "Bearer"