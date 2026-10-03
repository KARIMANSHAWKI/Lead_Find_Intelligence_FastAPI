from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.api.dependencies import get_request_settings, get_run_lead_intelligence
from app.application.dto.request import RunAgentRequest
from app.application.dto.response import RunAgentResponse
from app.application.use_cases.run_lead_intelligence import RunLeadIntelligence
from app.application.use_cases.deliver_agent_result import deliver_agent_result
from app.core.config import Settings
from app.infrastructure.result_callback import ResultCallbackClient

router = APIRouter(prefix="/agent", tags=["agent"])


def get_callback_client() -> ResultCallbackClient:
    return ResultCallbackClient()


@router.post(
    "/run",
    response_model=RunAgentResponse,
    responses={202: {"description": "Run accepted; results will be delivered to the callback."}},
    description="Discover and research ICP matches, returning only evidence-supported opportunities.",
)
async def run_agent(
    request: RunAgentRequest,
    use_case: Annotated[RunLeadIntelligence, Depends(get_run_lead_intelligence)],
    settings: Annotated[Settings, Depends(get_request_settings)],
    callback_client: Annotated[ResultCallbackClient, Depends(get_callback_client)],
    background_tasks: BackgroundTasks,
) -> RunAgentResponse | JSONResponse:
    if request.callback is not None:
        expected = str(settings.laravel_callback_base_url).rstrip("/") + f"/api/v1/agent/runs/{request.run_id}/result"
        if str(request.callback.url) != expected:
            raise HTTPException(status_code=422, detail="The callback URL is not an authorized Laravel result endpoint.")
        background_tasks.add_task(deliver_agent_result, request, use_case, callback_client)
        return JSONResponse(status_code=202, content={"run_id": request.run_id, "status": "running"})
    return await use_case.execute(request)
