import logging

from app.agents.lead_intelligence_agent import LeadIntelligenceAgent
from app.application.dto.request import RunAgentRequest
from app.application.dto.response import ProspectResult, RunAgentResponse

logger = logging.getLogger(__name__)


class RunLeadIntelligence:
    def __init__(self, agent: LeadIntelligenceAgent) -> None:
        self._agent = agent

    async def execute(self, request: RunAgentRequest) -> RunAgentResponse:
        logger.info("use_case_started", extra={"run_id": request.run_id})
        prospects = await self._agent.run(request.client, request.run_id)
        logger.info(
            "use_case_completed",
            extra={"run_id": request.run_id, "prospect_count": len(prospects)},
        )
        return RunAgentResponse(
            run_id=request.run_id,
            prospects=[
                ProspectResult.model_validate(prospect.model_dump())
                for prospect in prospects
            ],
        )
