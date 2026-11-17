import asyncio
from functools import lru_cache
from typing import Any

import aioboto3  # type: ignore[import-untyped]

from app.core.config import settings
from app.schemas.daily import DailyCostQueryParams
from app.services.query_builder import build_daily_cost_query


class AthenaService:
    def __init__(self) -> None:
        self.session = aioboto3.Session()
        self.region_name = settings.aws_region
        self.database = settings.athena_database
        self.workgroup = settings.athena_workgroup
        self.output_location = settings.athena_output_location

    async def start_query(
        self, client: Any, query: str, execution_params: list[str]
    ) -> str:
        response = await client.start_query_execution(
            ExecutionParameters=execution_params,
            QueryString=query,
            QueryExecutionContext={"Database": self.database},
            ResultConfiguration={"OutputLocation": self.output_location},
            WorkGroup=self.workgroup,
        )
        return str(response["QueryExecutionId"])

    async def wait_for_query(self, client: Any, query_execution_id: str) -> None:
        while True:
            response = await client.get_query_execution(
                QueryExecutionId=query_execution_id
            )
            state = response["QueryExecution"]["Status"]["State"]

            if state == "SUCCEEDED":
                return

            if state in ("FAILED", "CANCELLED"):
                reason = response["QueryExecution"]["Status"].get(
                    "StateChangeReason", ""
                )
                raise RuntimeError(f"Athena query {state}: {reason}")

            await asyncio.sleep(2)

    async def get_results(
        self, client: Any, query_execution_id: str
    ) -> list[dict[str, Any]]:
        paginator = client.get_paginator("get_query_results")
        pages = paginator.paginate(QueryExecutionId=query_execution_id)

        columns: list[str] = []
        rows: list[dict[str, Any]] = []

        async for page in pages:
            if not columns:
                columns = [
                    col["Name"]
                    for col in page["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]
                ]

            for row in page["ResultSet"]["Rows"]:
                values = [field.get("VarCharValue", "") for field in row["Data"]]
                rows.append(dict(zip(columns, values)))

        return rows[1:]  # first row is the header row

    async def run_query(
        self, query: str, execution_params: list[str]
    ) -> list[dict[str, Any]]:
        async with self.session.client(
            "athena", region_name=self.region_name
        ) as client:
            query_execution_id = await self.start_query(client, query, execution_params)
            await self.wait_for_query(client, query_execution_id)
            return await self.get_results(client, query_execution_id)

    async def get_daily_cost(
        self, params: DailyCostQueryParams
    ) -> list[dict[str, Any]]:
        query, execution_params = build_daily_cost_query(params)
        return await self.run_query(query, execution_params)


# Caching AthenaService to share across requests
@lru_cache
def get_athena_service() -> AthenaService:
    return AthenaService()
