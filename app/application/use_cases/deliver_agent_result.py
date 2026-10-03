from app.application.dto.request import RunAgentRequest
from app.application.use_cases.run_lead_intelligence import RunLeadIntelligence
from app.core.exceptions import (
    CompanySearchInputError, ProviderError, ProviderResponseError, ProviderTimeoutError,
)
from app.domain.ports.result_callback import ResultCallbackPort


async def deliver_agent_result(
    request: RunAgentRequest,
    use_case: RunLeadIntelligence,
    callback_client: ResultCallbackPort,
) -> None:
    """Run research after acknowledgement, then deliver a safe terminal result."""
    try:
        result = await use_case.execute(request)
        payload = result.model_dump(mode="json") | {"status": "completed"}
    except Exception as exception:
        if isinstance(exception, CompanySearchInputError):
            code = "invalid_icp"
        elif isinstance(exception, (ProviderTimeoutError, TimeoutError)):
            code = "timeout"
        elif isinstance(exception, ProviderResponseError):
            code = "invalid_response"
        elif isinstance(exception, ProviderError):
            code = "service_unavailable"
        else:
            code = "research_failed"
        payload = {"run_id": request.run_id, "status": "failed", "error_code": code}
    if request.callback is not None:
        await callback_client.send(str(request.callback.url), request.callback.token.get_secret_value(), payload)
