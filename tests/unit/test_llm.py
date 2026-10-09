import asyncio
import inspect
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)

from app.api.dependencies import get_openai_client
from app.core.config import Settings
from app.core.exceptions import (
    LLMResponseValidationError,
    ProviderAuthenticationError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from app.domain.models.client_context import ClientContext
from app.domain.models.company import Company
from app.domain.models.company_research import ResearchEvidence
from app.domain.models.prospect_analysis import ProspectAnalysis
from app.domain.ports.llm import LLMPort
from app.infrastructure.llm.openai_llm import OpenAILLM


@pytest.fixture
def inputs():
    return (
        Company(name="Example", industry="Software", employee_count=100),
        ClientContext(
            product="Recruitment Software",
            target_industries=["Software"],
            location="Egypt",
            company_size={"min": 50, "max": 300},
        ),
        [
            ResearchEvidence(
                text="The company lists 18 open positions.",
                source_url="https://example.com/jobs",
            )
        ],
    )


@pytest.fixture
def analysis_data():
    return {
        "icp_fit": "high",
        "product_relevance": "high",
        "why_now": "The company is actively hiring.",
        "buying_signals": [
            {"type": "hiring_growth", "evidence_index": 0, "strength": "high"}
        ],
        "evidence_quality": "high",
    }


def completion(
    arguments: str,
    finish_reason: str = "tool_calls",
    name: str = "submit_prospect_analysis",
):
    tool_call = SimpleNamespace(
        function=SimpleNamespace(
            name=name,
            arguments=arguments,
        )
    )
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(tool_calls=[tool_call]),
            )
        ]
    )


def provider(result=None, error=None):
    create = AsyncMock(return_value=result, side_effect=error)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    return OpenAILLM(client, "gpt-4o-mini"), create


def test_settings_and_client_use_openai_sdk(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    settings = Settings(_env_file=None)
    client = get_openai_client(settings)

    assert settings.openai_model == "gpt-test"
    assert "test-secret" not in repr(settings)
    assert str(client.base_url) == "https://api.openai.com/v1/"


def test_valid_structured_response(inputs, analysis_data):
    llm, create = provider(
        completion(json.dumps(analysis_data), finish_reason="stop")
    )
    result = asyncio.run(llm.analyze_company(*inputs))
    evidence = inputs[2][0]

    assert result == ProspectAnalysis(
        icp_fit="high",
        product_relevance="high",
        why_now="The company is actively hiring.",
        evidence_quality="high",
        buying_signals=[
            {
                "type": "hiring_growth",
                "evidence": evidence.text,
                "source_url": evidence.source_url,
                "strength": "high",
            }
        ],
    )
    parameters = create.call_args.kwargs
    assert parameters["model"] == "gpt-4o-mini"
    assert parameters["tool_choice"]["function"]["name"] == "submit_prospect_analysis"
    function = parameters["tools"][0]["function"]
    assert function["strict"] is True
    assert "score" not in function["parameters"]["properties"]


def test_tool_call_selects_bounded_known_companies(inputs):
    companies = [
        Company(name="One"),
        Company(name="Two"),
        Company(name="Three"),
    ]
    llm, create = provider(
        completion(
            json.dumps({"company_names": ["Two", "One"]}),
            name="research_companies",
        )
    )

    selected = asyncio.run(
        llm.select_companies_for_research(companies, inputs[1], limit=2)
    )

    assert selected == ["Two", "One"]
    parameters = create.call_args.kwargs
    assert parameters["tool_choice"]["function"]["name"] == "research_companies"
    names_schema = parameters["tools"][0]["function"]["parameters"]["properties"][
        "company_names"
    ]
    assert names_schema["maxItems"] == 2
    assert names_schema["items"]["enum"] == ["One", "Two", "Three"]


@pytest.mark.parametrize("content", ["not JSON", "{}", "[]", "null"])
def test_invalid_response(content, inputs):
    llm, _ = provider(completion(content))
    with pytest.raises(LLMResponseValidationError):
        asyncio.run(llm.analyze_company(*inputs))


def test_incomplete_response(inputs, analysis_data):
    llm, _ = provider(completion(json.dumps(analysis_data), finish_reason="length"))
    with pytest.raises(LLMResponseValidationError):
        asyncio.run(llm.analyze_company(*inputs))


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            AuthenticationError(
                "bad key",
                response=httpx.Response(
                    401, request=httpx.Request("POST", "https://example.test")
                ),
                body={},
            ),
            ProviderAuthenticationError,
        ),
        (
            RateLimitError(
                "limited",
                response=httpx.Response(
                    429, request=httpx.Request("POST", "https://example.test")
                ),
                body={},
            ),
            ProviderRateLimitError,
        ),
        (
            APITimeoutError(request=httpx.Request("POST", "https://example.test")),
            ProviderTimeoutError,
        ),
        (
            APIConnectionError(
                request=httpx.Request("POST", "https://example.test")
            ),
            ProviderError,
        ),
    ],
)
def test_provider_errors_are_mapped(error, expected, inputs):
    llm, _ = provider(error=error)
    with pytest.raises(expected):
        asyncio.run(llm.analyze_company(*inputs))


def test_llm_port_contract():
    assert issubclass(OpenAILLM, LLMPort)
    assert not inspect.isabstract(OpenAILLM)
    assert inspect.iscoroutinefunction(OpenAILLM.analyze_company)
    assert inspect.signature(OpenAILLM.analyze_company) == inspect.signature(
        LLMPort.analyze_company
    )
