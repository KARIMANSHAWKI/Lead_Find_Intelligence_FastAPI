from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    CompanySearchInputError,
    ProviderConfigurationError,
    ProviderError,
    ProviderRateLimitError,
    LLMResponseValidationError,
)


async def configuration_error(request: Request, error: ProviderConfigurationError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "Agent provider configuration is missing or invalid."})


async def provider_error(request: Request, error: ProviderError) -> JSONResponse:
    if isinstance(error, LLMResponseValidationError):
        return JSONResponse(status_code=502, content={"detail": "The LLM returned invalid or unsupported evidence. No unverified prospects were returned."})
    if isinstance(error, ProviderRateLimitError):
        return JSONResponse(
            status_code=503,
            content={"detail": "Agent provider rate limit reached. Wait for the provider quota to reset before retrying."},
        )
    return JSONResponse(status_code=502, content={"detail": "Agent provider request failed. Try again later."})


async def search_input_error(request: Request, error: CompanySearchInputError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": "ICP search filters are unsupported or invalid."})
