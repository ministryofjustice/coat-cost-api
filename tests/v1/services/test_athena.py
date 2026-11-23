from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import settings
from app.schemas.daily import DailyCostQueryParams
from app.services.athena import AthenaService
from app.services.query_builder import build_daily_cost_query


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
