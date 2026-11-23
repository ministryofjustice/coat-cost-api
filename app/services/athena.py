import asyncio
from datetime import datetime, timedelta, timezone
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
        self._ap_session: Any = None
        self._ap_expiration: datetime | None = None
        self._ap_output_location: str | None = None
        self._refresh_lock = asyncio.Lock()

    async def _assume_role(self) -> dict[str, Any]:
        async with self.session.client("sts", region_name=settings.aws_region) as sts:
            response: dict[str, Any] = await sts.assume_role(
                RoleArn=settings.athena_role_arn,
                RoleSessionName=settings.athena_role_session_name,
            )
            return response

    def _credentials_expiring(self) -> bool:
        now = datetime.now(timezone.utc)
        buffer_time = timedelta(minutes=5)

        if self._ap_expiration is None:
            return True
        return (self._ap_expiration - now) < buffer_time

    async def _get_session(self) -> tuple[Any, str]:
        # No AP role configured: use the app's own AWS credentials
        # (IRSA on CP, SSO profile locally) and COAT's output location
        if not settings.athena_role_arn:
            return self.session, self.output_location
        if not settings.athena_output_base:
            raise RuntimeError(
                "ATHENA_OUTPUT_BASE must be set when ATHENA_ROLE_ARN is set"
            )

        # AP role configured: assume it, and refresh the credentials
        # under the lock when they're missing or about to expire
        async with self._refresh_lock:
            if self._credentials_expiring():
                response = await self._assume_role()
                creds = response["Credentials"]

                self._ap_session = aioboto3.Session(
                    aws_access_key_id=creds["AccessKeyId"],
                    aws_secret_access_key=creds["SecretAccessKey"],
                    aws_session_token=creds["SessionToken"],
                )
                self._ap_expiration = creds["Expiration"]
                user_id = response["AssumedRoleUser"]["AssumedRoleId"]
                self._ap_output_location = f"{settings.athena_output_base}{user_id}/"

            if self._ap_output_location is None:
                raise RuntimeError(
                    "AP output location was not set after refreshing credentials"
                )
            return self._ap_session, self._ap_output_location

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
