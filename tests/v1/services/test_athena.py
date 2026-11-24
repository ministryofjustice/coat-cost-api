from datetime import date, datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import settings
from app.schemas.daily import DailyCostQueryParams
from app.services.athena import AthenaService
from app.services.query_builder import build_daily_cost_query

# Faking the assume creds
FAKE_ASSUME_ROLE_RESPONSE = {
    "Credentials": {
        "AccessKeyId": "AKIAFAKE",
        "SecretAccessKey": "fake-secret",
        "SessionToken": "fake-token",
        "Expiration": datetime.now(timezone.utc) + timedelta(hours=1),
    },
    "AssumedRoleUser": {"AssumedRoleId": "AROAFAKE:coat-cost-api"},
}

@pytest.mark.asyncio
async def test_start_query_returns_query_execution_id():
    """start_query returns the QueryExecutionId from the client's response"""
    service = AthenaService()
    client = AsyncMock()
    client.start_query_execution.return_value = {
        "QueryExecutionId": "random-test-id-54321"
    }

    result = await service.start_query(
        client, "SELECT 1", [], "s3://test-bucket/results/"
    )

    assert result == "random-test-id-54321"


@pytest.mark.asyncio
async def test_start_query_calls_client_with_correct_arguments():
    """Start_query passes query, execution_params, database, workgroup and output_location to the client"""
    service = AthenaService()
    client = AsyncMock()
    client.start_query_execution.return_value = {"QueryExecutionId": "abc-123"}

    await service.start_query(
        client, "SELECT 1", ["param1"], "s3://test-bucket/results/"
    )

    client.start_query_execution.assert_called_once_with(
        ExecutionParameters=["param1"],
        QueryString="SELECT 1",
        QueryExecutionContext={"Database": service.database},
        ResultConfiguration={"OutputLocation": "s3://test-bucket/results/"},
        WorkGroup=service.workgroup,
    )


@pytest.mark.asyncio
async def test_wait_for_query_returns_when_succeeded():
    """wait_for_query returns normally when the query state is SUCCEEDED"""
    service = AthenaService()
    client = AsyncMock()
    client.get_query_execution.return_value = {
        "QueryExecution": {"Status": {"State": "SUCCEEDED"}}
    }

    await service.wait_for_query(client, "query-id-123")

    client.get_query_execution.assert_called_once_with(QueryExecutionId="query-id-123")


@pytest.mark.asyncio
async def test_wait_for_query_returns_runtime_error_when_fails():
    """wait_for_query raises runtime error when the query state is failed"""
    service = AthenaService()
    client = AsyncMock()
    client.get_query_execution.return_value = {
        "QueryExecution": {"Status": {"State": "FAILED"}}
    }

    with pytest.raises(RuntimeError):
        await service.wait_for_query(client, "query-id-123")


@pytest.mark.asyncio
async def test_wait_for_query_raises_runtime_error_when_cancelled():
    """wait_for_query raises runtime error when the query state is cancelled"""
    service = AthenaService()
    client = AsyncMock()
    client.get_query_execution.return_value = {
        "QueryExecution": {"Status": {"State": "CANCELLED"}}
    }

    with pytest.raises(RuntimeError):
        await service.wait_for_query(client, "query-id-123")


@pytest.mark.asyncio
async def test_wait_for_query_polls_until_succeeded():
    """wait_for_query polls repeatedly until the query state is succeeded"""
    service = AthenaService()
    client = AsyncMock()
    client.get_query_execution.side_effect = [
        {"QueryExecution": {"Status": {"State": "RUNNING"}}},
        {"QueryExecution": {"Status": {"State": "SUCCEEDED"}}},
    ]

    await service.wait_for_query(client, "query-id-123")

    assert client.get_query_execution.call_count == 2


@pytest.mark.asyncio
async def test_run_query_executes_start_wait_and_get_results():
    """
    run query function calls start_query,
    wait_for_query and get_results in order and returns get_results output
    """
    service = AthenaService()

    fake_client = AsyncMock()
    client_context_manager = AsyncMock()
    client_context_manager.__aenter__.return_value = fake_client
    fake_session = MagicMock()
    fake_session.client.return_value = client_context_manager
    service._get_session = AsyncMock(return_value=(fake_session, "s3://test-output/"))

    service.start_query = AsyncMock(return_value="query-id-123")
    service.wait_for_query = AsyncMock(return_value=None)
    service.get_results = AsyncMock(return_value=[{"account_name": "LAA"}])

    result = await service.run_query("SELECT 1", ["param1"])

    service.start_query.assert_called_once_with(
        fake_client, "SELECT 1", ["param1"], "s3://test-output/"
    )
    service.wait_for_query.assert_called_once_with(fake_client, "query-id-123")
    service.get_results.assert_called_once_with(fake_client, "query-id-123")
    fake_session.client.assert_called_once_with(
        "athena", region_name=settings.athena_client_region
    )
    assert result == [{"account_name": "LAA"}]


@pytest.mark.asyncio
async def test_get_daily_cost_builds_query_and_calls_run_query():
    """get_daily_cost builds the query via build_daily_cost_query and passes it to run_query"""
    service = AthenaService()
    params = DailyCostQueryParams(
        start_usage_date=date(2025, 12, 1),
        end_usage_date=date(2025, 12, 10),
        account_name="LAA",
    )
    expected_query, expected_execution_params = build_daily_cost_query(params)

    service.run_query = AsyncMock(return_value=[{"account_name": "LAA"}])

    result = await service.get_daily_cost(params)

    service.run_query.assert_called_once_with(expected_query, expected_execution_params)
    assert result == [{"account_name": "LAA"}]


def test_credentials_expiring_returns_true_when_no_expiration_set():
    """No credentials assumed yet, so they need refreshing"""
    service = AthenaService()
    assert service._credentials_expiring() is True


def test_credentials_expiring_returns_false_when_plenty_of_time_left():
    """credentials with an hour left don't need refreshing"""
    service = AthenaService()
    service._ap_expiration = datetime.now(timezone.utc) + timedelta(hours=1)
    assert service._credentials_expiring() is False


def test_credentials_expiring_returns_true_when_inside_buffer():
    """credentials with under 5 minutes left need refreshing"""
    service = AthenaService()
    service._ap_expiration = datetime.now(timezone.utc) + timedelta(minutes=2)
    assert service._credentials_expiring() is True


@pytest.mark.asyncio
async def test_get_session_without_role_returns_default_session(monkeypatch):
    """No role configured: use the default session and COAT's output location, no STS call"""
    monkeypatch.setattr(settings, "athena_role_arn", None)
    service = AthenaService()
    service._assume_role = AsyncMock()

    session, output_location = await service._get_session()

    assert session is service.session
    assert output_location == service.output_location
    service._assume_role.assert_not_called()

@pytest.mark.asyncio
async def test_get_session_raises_when_output_base_missing(monkeypatch):
    """Role set but no ATHENA_OUTPUT_BASE: fail clearly"""
    monkeypatch.setattr(
        settings, "athena_role_arn", "arn:aws:iam::123456789012:role/test-role"
    )
    monkeypatch.setattr(settings, "athena_output_base", None)

    service = AthenaService()

    with pytest.raises(RuntimeError, match="ATHENA_OUTPUT_BASE"):
        await service._get_session()


@pytest.mark.asyncio
async def test_get_session_assumes_role_and_builds_output_location(monkeypatch):
    """Role set, first call: assumes the role once and builds base + UserId + '/'"""
    monkeypatch.setattr(
        settings, "athena_role_arn", "arn:aws:iam::123456789012:role/test-role"
    )
    monkeypatch.setattr(settings, "athena_output_base", "s3://test-query-dump/")

    service = AthenaService()
    service._assume_role = AsyncMock(return_value=FAKE_ASSUME_ROLE_RESPONSE)

    session, output_location = await service._get_session()

    service._assume_role.assert_called_once()
    assert session is not service.session
    assert output_location == "s3://test-query-dump/AROAFAKE:coat-cost-api/"
    assert service._ap_expiration == FAKE_ASSUME_ROLE_RESPONSE["Credentials"]["Expiration"]

@pytest.mark.asyncio
async def test_get_session_reuses_cached_credentials(monkeypatch):
    """Second call with fresh credentials doesn't assume the role again"""
    monkeypatch.setattr(
        settings, "athena_role_arn", "arn:aws:iam::123456789012:role/test-role"
    )
    monkeypatch.setattr(settings, "athena_output_base", "s3://test-query-dump/")

    service = AthenaService()
    service._assume_role = AsyncMock(return_value=FAKE_ASSUME_ROLE_RESPONSE)

    session1, output1 = await service._get_session()
    session2, output2 = await service._get_session()

    service._assume_role.assert_called_once()
    assert session1 is session2
    assert output1 == output2 == "s3://test-query-dump/AROAFAKE:coat-cost-api/"


@pytest.mark.asyncio
async def test_get_session_refreshes_expiring_credentials(monkeypatch):
    """Second call when credentials are inside the 5-minute buffer re-assumes the role"""
    monkeypatch.setattr(
        settings, "athena_role_arn", "arn:aws:iam::123456789012:role/test-role"
    )
    monkeypatch.setattr(settings, "athena_output_base", "s3://test-query-dump/")

    service = AthenaService()
    service._assume_role = AsyncMock(return_value=FAKE_ASSUME_ROLE_RESPONSE)

    await service._get_session()
    service._ap_expiration = datetime.now(timezone.utc) + timedelta(minutes=1)
    await service._get_session()

    assert service._assume_role.call_count == 2