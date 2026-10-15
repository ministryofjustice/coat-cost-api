from fastapi import APIRouter, Depends

from app.api.v1.endpoints import daily
from app.core.auth import require_api_key

router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_api_key)],
    responses={401: {"description": "Invalid or missing API key"}},
)

router.include_router(daily.router)
