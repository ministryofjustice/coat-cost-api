from fastapi import APIRouter, Depends

from app.schemas.daily import DailyCostQueryParams, DailyCostResponse, DailyCostRow
from app.services.athena import AthenaService, get_athena_service

router = APIRouter()


@router.get(
    "/cloud-cost/daily",
    response_model=DailyCostResponse,
    response_model_exclude_none=True,
)
async def get_daily_cost(
    params: DailyCostQueryParams = Depends(),
    athena_service: AthenaService = Depends(get_athena_service),
) -> DailyCostResponse:
    raw_rows = await athena_service.get_daily_cost(params)
    rows = [DailyCostRow(**row) for row in raw_rows]

    return DailyCostResponse(
        account_name=params.account_name,
        results=rows,
    )
